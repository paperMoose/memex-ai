#!/usr/bin/env python3
"""
Fast email search using Mail's SQLite database directly.
Much faster than JXA for large mailboxes.

Features:
- Direct SQLite access for fast metadata search
- JXA integration for body content extraction
- Filter by sender, subject, date range, read status
- Blocklist support for filtering unwanted senders
- Multiple output formats: table, JSON, count
"""

import argparse
import sqlite3
import os
import json
import re
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, date, timezone
from email.utils import parseaddr
from typing import List, Optional, Tuple
import sys


def find_mail_db():
    """Find the Mail database file."""
    envelope_db = Path.home() / "Library/Mail/V10/MailData/Envelope Index"
    
    if not envelope_db.exists():
        # Try V9, V8, etc.
        mail_dir = Path.home() / "Library/Mail"
        for version_dir in sorted(mail_dir.glob("V*"), reverse=True):
            test_db = version_dir / "MailData/Envelope Index"
            if test_db.exists():
                return test_db
        return None
    
    return envelope_db


def parse_emlx_body(emlx_path):
    """Parse body content from .emlx file.
    
    .emlx format:
    - First line: byte count (ignored)
    - Rest: Standard RFC 822 email format
    """
    try:
        with open(emlx_path, 'rb') as f:
            # Skip first line (byte count)
            f.readline()
            
            # Read rest as email
            email_data = f.read()
            
            # Parse email
            from email import message_from_bytes
            from email.policy import default
            msg = message_from_bytes(email_data, policy=default)
            
            # Extract plain text body
            body_parts = []
            
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == 'text/plain':
                        try:
                            body_parts.append(part.get_content())
                        except:
                            pass
            else:
                if msg.get_content_type() == 'text/plain':
                    try:
                        body_parts.append(msg.get_content())
                    except:
                        pass
            
            return '\n\n'.join(body_parts) if body_parts else None
            
    except Exception as e:
        return None


def find_emlx_file(mail_dir, mailbox_url, message_rowid):
    """Find the .emlx file for a message.
    
    Messages are stored in nested shard directories:
    {account_id}/{mailbox_path}/Data/{shard1}/{shard2}/{shard3}/Messages/{ROWID}.emlx
    
    The sharding is based on ROWID digits.
    """
    # Parse mailbox URL to get account and mailbox path
    # Format: imap://ACCOUNT_ID/MAILBOX_PATH
    if not mailbox_url or not mailbox_url.startswith('imap://'):
        return None
    
    try:
        # Extract account ID and mailbox path
        parts = mailbox_url.replace('imap://', '').split('/', 1)
        if len(parts) < 2:
            return None
        
        account_id = parts[0]
        mailbox_path = parts[1].replace('%5B', '[').replace('%5D', ']').replace('%20', ' ')
        
        # Build base path
        account_dir = mail_dir / account_id
        if not account_dir.exists():
            return None
        
        # Find the mailbox directory
        # For Gmail: [Gmail].mbox/All Mail.mbox
        mailbox_parts = mailbox_path.split('/')
        mailbox_dir = account_dir
        for part in mailbox_parts:
            mailbox_dir = mailbox_dir / f"{part}.mbox"
        
        if not mailbox_dir.exists():
            return None
        
        # Find the Data directory (there's usually a UUID subdirectory)
        data_dirs = list(mailbox_dir.glob('*/Data'))
        if not data_dirs:
            return None
        
        data_dir = data_dirs[0]
        
        # Search for the file (try both .emlx and .partial.emlx)
        # The sharding pattern is complex and varies, so we search
        # This is still fast since we're only searching one mailbox's Data directory
        for emlx_file in data_dir.rglob(f'{message_rowid}.emlx'):
            return emlx_file
        
        # Try partial downloads
        for emlx_file in data_dir.rglob(f'{message_rowid}.partial.emlx'):
            return emlx_file
        
        return None
        
    except Exception as e:
        return None


def get_message_body(mail_dir, mailbox_url, message_rowid):
    """Get message body from .emlx file on disk."""
    emlx_path = find_emlx_file(mail_dir, mailbox_url, message_rowid)
    if not emlx_path:
        return None
    
    return parse_emlx_body(emlx_path)


def load_blocklist(path: Optional[str]) -> List[str]:
    """Load blocklist from file."""
    if not path:
        return []
    try:
        entries = [ln.strip().lower() for ln in open(path, "r", encoding="utf-8").read().splitlines()]
        return [e for e in entries if e and not e.startswith("#")]
    except FileNotFoundError:
        print(f"Blocklist file not found: {path}", file=sys.stderr)
        return []


def is_blocked(sender_email: str, blocklist: List[str]) -> bool:
    """Check if sender is in blocklist."""
    if not sender_email:
        return False
    for item in blocklist:
        if item.startswith("@"):
            # Domain match
            if sender_email.endswith(item):
                return True
        elif "@" in item:
            if sender_email == item:
                return True
        else:
            # Substring match fallback
            if item in sender_email:
                return True
    return False


def get_account_emails(db_path):
    """Get list of account owner email addresses."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    # Look for common account email patterns
    cursor = conn.execute("""
        SELECT DISTINCT addresses.address
        FROM messages
        LEFT JOIN addresses ON messages.sender = addresses.ROWID
        WHERE addresses.address NOT LIKE '%@noreply%'
        AND addresses.address NOT LIKE '%@notification%'
        AND addresses.address NOT LIKE '%no-reply%'
        GROUP BY addresses.address
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    emails = [row[0] for row in cursor if row[0]]
    conn.close()
    return emails

def search_emails(db_path, from_search=None, subject_search=None, to_search=None, 
                  body_search=None, since_date=None, until_date=None, 
                  unread_only=False, sent_only=False, limit=100, include_body=False, body_limit=None,
                  blocklist=None, include_blocked=False):
    """Search emails in Mail database."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    
    # If sent_only, auto-detect account emails
    account_emails = []
    if sent_only:
        account_emails = get_account_emails(db_path)
    
    # Get mail directory for body extraction
    mail_dir = Path.home() / "Library/Mail"
    # Detect version (sort by version number, not alphabetically)
    version_dirs = [(int(d.name[1:]), d) for d in mail_dir.glob("V*") if d.is_dir() and d.name[1:].isdigit()]
    if version_dirs:
        version_dirs.sort(reverse=True)
        mail_dir = version_dirs[0][1]
    
    query = """
        SELECT 
            messages.ROWID as id,
            addresses.address as sender_email,
            addresses.comment as sender_name,
            subjects.subject,
            messages.date_received,
            messages.date_sent,
            messages.read,
            messages.flagged,
            messages.remote_id,
            mailboxes.url as mailbox_url
        FROM messages
        LEFT JOIN addresses ON messages.sender = addresses.ROWID
        LEFT JOIN subjects ON messages.subject = subjects.ROWID
        LEFT JOIN mailboxes ON messages.mailbox = mailboxes.ROWID
        WHERE 1=1
    """
    
    params = []
    
    if from_search:
        query += " AND (addresses.address LIKE ? OR addresses.comment LIKE ?)"
        params.extend([f"%{from_search}%", f"%{from_search}%"])
    
    if subject_search:
        query += " AND subjects.subject LIKE ?"
        params.append(f"%{subject_search}%")
    
    if to_search:
        # Note: Searching recipients requires joining with message_data table
        # which is more complex. For now, we'll skip this.
        pass
    
    if since_date:
        # Convert to Apple timestamp (seconds since 2001-01-01)
        unix_ts = int(since_date.timestamp())
        apple_ts = unix_ts - 978307200
        query += " AND messages.date_received >= ?"
        params.append(apple_ts)
    
    if until_date:
        unix_ts = int(until_date.timestamp())
        apple_ts = unix_ts - 978307200
        query += " AND messages.date_received <= ?"
        params.append(apple_ts)
    
    if unread_only:
        query += " AND messages.read = 0"
    
    if sent_only and account_emails:
        # Filter by sender being one of your account emails
        # For Gmail, sent messages are in All Mail but identifiable by sender
        placeholders = " OR ".join(["addresses.address LIKE ?" for _ in account_emails])
        query += f" AND ({placeholders})"
        params.extend([f"%{email}%" for email in account_emails])
    
    query += " ORDER BY messages.date_received DESC LIMIT ?"
    params.append(limit)
    
    cursor = conn.execute(query, params)
    results = []
    
    blocklist = blocklist or []
    
    for row in cursor:
        # Mail.app V10+ stores dates as Unix timestamps directly
        # (older versions used Core Data timestamps which needed +978307200 offset)
        if row['date_received']:
            timestamp = row['date_received']
            date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
            date_obj = datetime.fromtimestamp(timestamp)
        else:
            date_str = ""
            date_obj = None
        
        sender_email = (row['sender_email'] or "").lower()
        sender = row['sender_name'] or row['sender_email'] or ""
        if row['sender_name'] and row['sender_email']:
            sender = f"{row['sender_name']} <{row['sender_email']}>"
        
        # Check blocklist
        blocked = is_blocked(sender_email, blocklist)
        if blocked and not include_blocked:
            continue
        
        result = {
            'id': row['id'],
            'date': date_str,
            'date_obj': date_obj,
            'from': sender,
            'email': sender_email,
            'subject': row['subject'] or "",
            'read': 'yes' if row['read'] else 'no',
            'flagged': 'yes' if row['flagged'] else 'no',
            'blocked': 'yes' if blocked else 'no'
        }
        
        if include_body:
            body = get_message_body(mail_dir, row['mailbox_url'], row['id'])
            if body and body_limit:
                body = body[:body_limit]
            result['body'] = body
        
        results.append(result)
    
    conn.close()
    return results


def format_table(results, columns=['date', 'from', 'subject']):
    """Format results as a table."""
    if not results:
        print("No emails found.")
        return
    
    # Build header
    header = [col.capitalize() for col in columns]
    
    # Build rows
    rows = []
    for r in results:
        row = []
        for col in columns:
            if col == 'date':
                value = r.get('date', '')
            elif col in ('from', 'sender'):
                value = r.get('from', '')
            elif col == 'email':
                value = r.get('email', '')
            elif col == 'subject':
                value = r.get('subject', '')
            elif col == 'body':
                value = r.get('body', '')
                # Normalize whitespace for table display
                if value:
                    value = re.sub(r'\s+', ' ', value).strip()
            elif col == 'read':
                value = r.get('read', '')
            elif col == 'flagged':
                value = r.get('flagged', '')
            elif col == 'blocked':
                value = r.get('blocked', '')
            else:
                value = r.get(col, '')
            
            if isinstance(value, str):
                value = re.sub(r'\s+', ' ', value).strip()
            row.append(str(value))
        rows.append(row)
    
    # Calculate column widths
    widths = [len(h) for h in header]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = min(max(widths[i], len(cell)), 120)
    
    # Format rows
    def fmt_row(vals):
        return "  ".join(v[:widths[i]].ljust(widths[i]) for i, v in enumerate(vals))
    
    # Print table
    print(fmt_row(header))
    print(fmt_row(["-" * w for w in widths]))
    for row in rows:
        print(fmt_row(row))


def parse_date_arg(date_str):
    """Parse date argument in various formats."""
    if not date_str:
        return None
    
    # Try common formats
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Try relative dates
    date_str_lower = date_str.lower()
    if date_str_lower == "today":
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_str_lower == "yesterday":
        from datetime import timedelta
        return (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_str_lower == "week":
        from datetime import timedelta
        return datetime.now() - timedelta(days=7)
    elif date_str_lower == "month":
        from datetime import timedelta
        return datetime.now() - timedelta(days=30)
    
    raise ValueError(f"Could not parse date: {date_str}")


def main():
    parser = argparse.ArgumentParser(description="Fast search of Apple Mail database")
    
    # Search filters
    filters = parser.add_argument_group("filters")
    filters.add_argument("--from", dest="from_search", help="Search sender (name or email)")
    filters.add_argument("--subject", dest="subject_search", help="Search subject")
    filters.add_argument("--to", dest="to_search", help="Search recipient (not yet implemented)")
    filters.add_argument("--body-search", dest="body_search", help="Search body text (not yet implemented)")
    filters.add_argument("--since", dest="since_date", help="Show emails since date (YYYY-MM-DD, today, yesterday, week, month)")
    filters.add_argument("--until", dest="until_date", help="Show emails until date (YYYY-MM-DD)")
    filters.add_argument("--unread", action="store_true", help="Show only unread emails")
    filters.add_argument("--sent", action="store_true", help="Show only sent emails")
    filters.add_argument("--today", action="store_true", help="Show only today's emails")
    filters.add_argument("--blocked-senders", type=str, help="Path to newline-separated blocked senders/domains")
    filters.add_argument("--include-blocked", action="store_true", help="Include blocked senders in output, mark with blocked=yes")
    
    # Output options
    output = parser.add_argument_group("output")
    output.add_argument("--limit", type=int, default=100, help="Max results (default 100)")
    output.add_argument("--body", action="store_true", help="Include message body (uses JXA, may be slow)")
    output.add_argument("--body-limit", type=int, help="Limit body text length")
    output.add_argument("--json", action="store_true", help="Output JSON")
    output.add_argument("--count", action="store_true", help="Only print count")
    output.add_argument("--columns", type=str, default="date,from,subject", 
                       help="Comma-separated columns for table output (date,from,email,subject,read,flagged,blocked,body)")
    
    args = parser.parse_args()
    
    db_path = find_mail_db()
    if not db_path:
        print("Error: Could not find Mail database", file=sys.stderr)
        return 1
    
    # Parse date arguments
    since_date = None
    until_date = None
    
    try:
        if args.today:
            since_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        elif args.since_date:
            since_date = parse_date_arg(args.since_date)
        
        if args.until_date:
            until_date = parse_date_arg(args.until_date)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    # Load blocklist
    blocklist = load_blocklist(args.blocked_senders)
    
    results = search_emails(
        db_path,
        from_search=args.from_search,
        subject_search=args.subject_search,
        to_search=args.to_search,
        body_search=args.body_search,
        since_date=since_date,
        until_date=until_date,
        unread_only=args.unread,
        sent_only=args.sent,
        limit=args.limit,
        include_body=args.body,
        body_limit=args.body_limit,
        blocklist=blocklist,
        include_blocked=args.include_blocked
    )
    
    if args.count:
        print(len(results))
        return 0
    
    if args.json:
        # Remove date_obj from JSON output (not serializable)
        for r in results:
            r.pop('date_obj', None)
        print(json.dumps(results, indent=2))
    else:
        columns = [c.strip().lower() for c in args.columns.split(",") if c.strip()]
        format_table(results, columns)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

