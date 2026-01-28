#!/usr/bin/env python3
"""
imessage_recent_threads.py

Fetch the N most recent iMessage conversation threads with their complete history.

Safety:
- Read-only access to Messages database
- Copies DB to temp location before querying
- Requires Full Disk Access for terminal app

Usage examples:
  # Get 30 most recent conversations to stdout
  python3 scripts/imessage_recent_threads.py --threads 30

  # Save to directory (one file per thread)
  python3 scripts/imessage_recent_threads.py --threads 30 --output-dir /tmp/recent_convos

  # Save to single file with separators
  python3 scripts/imessage_recent_threads.py --threads 30 --output /tmp/recent_convos.md

  # Include more context per thread (default shows last 100 messages per thread)
  python3 scripts/imessage_recent_threads.py --threads 30 --messages-per-thread 500
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple


APPLE_EPOCH_UNIX = 978307200  # seconds from 1970-01-01 to 2001-01-01


def extract_text_from_attributed_body(blob: bytes) -> str:
    """
    Extract plain text from attributedBody blob.
    On newer macOS, messages are stored as NSAttributedString in binary plist format.
    """
    if not blob:
        return ""
    
    try:
        # Method 1: Try to find readable ASCII text sequences
        import re
        # Extract sequences of printable ASCII characters (5+ chars long)
        text_parts = re.findall(b'[\x20-\x7e]{5,}', blob)
        
        # Filter out common NSAttributedString metadata keywords
        metadata_keywords = {
            b'streamtyped', b'NSAttributedString', b'NSObject', b'NSString',
            b'NSDictionary', b'NSNumber', b'NSValue', b'__kIMMessage',
            b'AttributeName', b'NSColor', b'NSFont', b'NSParagraphStyle'
        }
        
        candidates = []
        for part in text_parts:
            try:
                decoded = part.decode('utf-8')
                # Skip if it's a metadata keyword
                if any(keyword.decode('utf-8') in decoded for keyword in metadata_keywords):
                    continue
                # Skip if it looks like a key (starts with __ or all uppercase)
                if decoded.startswith('__') or (decoded.isupper() and len(decoded) > 3):
                    continue
                # This looks like actual message content
                if len(decoded) >= 3:  # At least 3 chars
                    candidates.append(decoded)
            except:
                continue
        
        # Return the longest candidate (likely the actual message)
        if candidates:
            return max(candidates, key=len).strip()
        
        # Method 2: Try to decode as NSAttributedString plist
        try:
            import biplist
            plist = biplist.readPlistFromString(blob)
            if isinstance(plist, dict) and "NSString" in plist:
                return plist["NSString"]
        except:
            pass
        
        # Method 3: Look for text after NSString marker
        try:
            decoded = blob.decode('utf-8', errors='ignore')
            if 'NSString' in decoded:
                parts = decoded.split('\x00')
                for part in parts:
                    if part and len(part) > 2:
                        # Filter out binary junk
                        cleaned = ''.join(c for c in part if 32 <= ord(c) < 127 or c in '\n\t')
                        if len(cleaned) > 5 and not cleaned.startswith('NS'):
                            return cleaned.strip()
        except:
            pass
            
    except Exception:
        pass
    
    return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export N most recent iMessage conversation threads (read-only)"
    )
    parser.add_argument(
        "--db",
        default=os.path.expanduser("~/Library/Messages/chat.db"),
        help="Path to Messages chat.db",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=30,
        help="Number of recent conversation threads to fetch (default: 30)",
    )
    parser.add_argument(
        "--messages-per-thread",
        type=int,
        default=0,
        help="Max messages per thread (0 = all messages, default: 0)",
    )
    parser.add_argument(
        "--output",
        help="Output to single file (markdown format with thread separators)",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory (creates one file per thread)",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "jsonl"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output to stderr",
    )
    return parser.parse_args()


def load_contacts_mapping() -> Dict[str, str]:
    """Load phone/email to contact name mapping from macOS Contacts."""
    handle_to_name: Dict[str, str] = {}
    
    addressbook_root = os.path.expanduser("~/Library/Application Support/AddressBook")
    main_db = os.path.join(addressbook_root, "AddressBook-v22.abcddb")
    source_pattern = os.path.join(addressbook_root, "Sources/*/AddressBook-v22.abcddb")
    all_dbs = [main_db] + glob.glob(source_pattern)
    
    for db_path in all_dbs:
        if not os.path.exists(db_path):
            continue
            
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            
            # Get phone numbers
            phone_sql = """
                SELECT 
                    p.ZFULLNUMBER as handle,
                    COALESCE(
                        TRIM(COALESCE(r.ZFIRSTNAME, '') || ' ' || COALESCE(r.ZLASTNAME, '')),
                        r.ZORGANIZATION,
                        'Unknown'
                    ) as name
                FROM ZABCDPHONENUMBER p
                JOIN ZABCDRECORD r ON p.ZOWNER = r.Z_PK
                WHERE p.ZFULLNUMBER IS NOT NULL AND p.ZFULLNUMBER != ''
            """
            
            for row in conn.execute(phone_sql):
                phone = row["handle"].strip()
                name = row["name"].strip()
                if phone and name and name != "Unknown":
                    handle_to_name[phone] = name
                    if phone.startswith("+"):
                        handle_to_name[phone[1:]] = name
                    normalized = phone.replace("+", "").replace("(", "").replace(")", "").replace(" ", "").replace("-", "")
                    handle_to_name[normalized] = name
            
            # Get email addresses
            email_sql = """
                SELECT 
                    e.ZADDRESS as handle,
                    COALESCE(
                        TRIM(COALESCE(r.ZFIRSTNAME, '') || ' ' || COALESCE(r.ZLASTNAME, '')),
                        r.ZORGANIZATION,
                        'Unknown'
                    ) as name
                FROM ZABCDEMAILADDRESS e
                JOIN ZABCDRECORD r ON e.ZOWNER = r.Z_PK
                WHERE e.ZADDRESS IS NOT NULL AND e.ZADDRESS != ''
            """
            
            for row in conn.execute(email_sql):
                email = row["handle"].strip().lower()
                name = row["name"].strip()
                if email and name and name != "Unknown":
                    handle_to_name[email] = name
            
            conn.close()
            
        except Exception:
            continue
    
    return handle_to_name


def ensure_copy_readonly(db_path: str) -> str:
    """Copy Messages DB to temp location for safe read-only access."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Messages database not found: {db_path}")
    
    tmp_dir = tempfile.mkdtemp(prefix="imsg_recent_threads_")
    dst = os.path.join(tmp_dir, "chat.copy.db")
    shutil.copy2(db_path, dst)
    
    # Copy WAL/SHM files if they exist
    for suffix in ("-wal", "-shm"):
        src = db_path + suffix
        if os.path.exists(src):
            try:
                shutil.copy2(src, dst + suffix)
            except Exception:
                pass
    
    return dst


def open_ro_connection(copy_db_path: str) -> sqlite3.Connection:
    """Open read-only connection to copied Messages database."""
    uri = f"file:{copy_db_path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def get_recent_chat_ids(
    conn: sqlite3.Connection,
    limit: int,
    contacts_map: Optional[Dict[str, str]] = None,
    verbose: bool = False
) -> List[Tuple[int, str, str, str, str]]:
    """
    Get N most recent chat IDs based on latest message timestamp.
    Returns list of (chat_id, chat_identifier, display_name, first_message_time, last_message_time).
    """
    conn.row_factory = sqlite3.Row
    
    sql = """
        SELECT 
            c.ROWID as chat_id,
            COALESCE(c.chat_identifier, 'unknown') as chat_identifier,
            COALESCE(c.display_name, c.chat_identifier, 'unknown') as display_name,
            datetime(MIN(m.date)/1000000000 + ?, 'unixepoch') as first_message_time,
            datetime(MAX(m.date)/1000000000 + ?, 'unixepoch') as last_message_time
        FROM chat c
        JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
        JOIN message m ON m.ROWID = cmj.message_id
        GROUP BY c.ROWID
        ORDER BY MAX(m.date) DESC
        LIMIT ?
    """
    
    cur = conn.execute(sql, [APPLE_EPOCH_UNIX, APPLE_EPOCH_UNIX, limit])
    results = []
    
    for row in cur:
        chat_id = int(row["chat_id"])
        chat_identifier = str(row["chat_identifier"])
        display_name = str(row["display_name"])
        first_msg_time = str(row["first_message_time"])
        last_msg_time = str(row["last_message_time"])

        # If the chat has no display name (common for some 1:1 threads),
        # map the identifier (phone/email) to a real name via Contacts.
        if contacts_map:
            dn = (display_name or "").strip()
            ci = (chat_identifier or "").strip()
            if (not dn) or dn == "unknown" or dn == ci:
                mapped = contacts_map.get(ci)
                if not mapped and ci.startswith("+"):
                    mapped = contacts_map.get(ci[1:])
                if not mapped:
                    normalized = ci.replace("+", "").replace("(", "").replace(")", "").replace(" ", "").replace("-", "")
                    mapped = contacts_map.get(normalized)
                if mapped:
                    display_name = mapped

        results.append((chat_id, chat_identifier, display_name, first_msg_time, last_msg_time))
        
        if verbose:
            sys.stderr.write(f"Found thread: {display_name} (first: {first_msg_time}, last: {last_msg_time})\n")
    
    return results


def get_new_contacts_by_date(
    conn: sqlite3.Connection,
    target_date: str,
    contacts_map: Optional[Dict[str, str]] = None,
    verbose: bool = False
) -> List[Tuple[int, str, str, str, str]]:
    """
    Get all chat threads where the FIRST message was on the target date.
    This identifies contacts you met/exchanged numbers with on that day.
    
    Args:
        target_date: Date string in YYYY-MM-DD format
        
    Returns list of (chat_id, chat_identifier, display_name, first_message_time, last_message_time).
    """
    conn.row_factory = sqlite3.Row
    
    sql = """
        SELECT 
            c.ROWID as chat_id,
            COALESCE(c.chat_identifier, 'unknown') as chat_identifier,
            COALESCE(c.display_name, c.chat_identifier, 'unknown') as display_name,
            datetime(MIN(m.date)/1000000000 + ?, 'unixepoch') as first_message_time,
            datetime(MAX(m.date)/1000000000 + ?, 'unixepoch') as last_message_time
        FROM chat c
        JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
        JOIN message m ON m.ROWID = cmj.message_id
        GROUP BY c.ROWID
        HAVING date(MIN(m.date)/1000000000 + ?, 'unixepoch') = ?
        ORDER BY MIN(m.date) ASC
    """
    
    cur = conn.execute(sql, [APPLE_EPOCH_UNIX, APPLE_EPOCH_UNIX, APPLE_EPOCH_UNIX, target_date])
    results = []
    
    for row in cur:
        chat_id = int(row["chat_id"])
        chat_identifier = str(row["chat_identifier"])
        display_name = str(row["display_name"])
        first_msg_time = str(row["first_message_time"])
        last_msg_time = str(row["last_message_time"])

        # Map identifier to contact name if available
        if contacts_map:
            dn = (display_name or "").strip()
            ci = (chat_identifier or "").strip()
            if (not dn) or dn == "unknown" or dn == ci:
                mapped = contacts_map.get(ci)
                if not mapped and ci.startswith("+"):
                    mapped = contacts_map.get(ci[1:])
                if not mapped:
                    normalized = ci.replace("+", "").replace("(", "").replace(")", "").replace(" ", "").replace("-", "")
                    mapped = contacts_map.get(normalized)
                if mapped:
                    display_name = mapped

        results.append((chat_id, chat_identifier, display_name, first_msg_time, last_msg_time))
        
        if verbose:
            sys.stderr.write(f"New contact on {target_date}: {display_name} ({chat_identifier})\n")
    
    return results


def get_thread_messages(
    conn: sqlite3.Connection,
    chat_id: int,
    contacts_map: Dict[str, str],
    limit: int = 0
) -> List[Tuple[str, str, str]]:
    """
    Get all messages for a specific chat thread.
    Returns list of (timestamp, sender_name, text).
    """
    conn.row_factory = sqlite3.Row
    
    sql = """
        SELECT
            datetime(m.date/1000000000 + ?, 'unixepoch') AS sent_ts,
            m.is_from_me AS is_from_me,
            COALESCE(h.id, h.uncanonicalized_id, '') AS sender_handle,
            COALESCE(m.text, '') AS text,
            m.attributedBody AS attributedBody,
            COALESCE(m.cache_has_attachments, 0) AS cache_has_attachments
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        WHERE cmj.chat_id = ?
        ORDER BY m.date ASC
    """
    
    if limit > 0:
        # Get last N messages if limit specified
        sql = sql.replace("ORDER BY m.date ASC", "ORDER BY m.date DESC LIMIT ?")
    
    params = [APPLE_EPOCH_UNIX, chat_id]
    if limit > 0:
        params.append(limit)
    
    cur = conn.execute(sql, params)
    messages = []
    
    for row in cur:
        sent_ts = str(row["sent_ts"])
        is_from_me = bool(row["is_from_me"])
        sender_handle = str(row["sender_handle"])
        text = str(row["text"])
        has_attachments = int(row["cache_has_attachments"] or 0)
        
        # If text is empty, try to extract from attributedBody
        if not text and row["attributedBody"]:
            text = extract_text_from_attributed_body(row["attributedBody"])

        # Handle attachment-only messages (photos, etc.). These often have empty text
        # or just an object-replacement glyph in attributedBody.
        if (not text or text.strip() in {"", "￼"}) and has_attachments:
            text = "[Attachment]"
        
        # Determine sender name
        if is_from_me:
            sender_name = "Me"
        elif sender_handle:
            # Try to map handle to contact name
            sender_name = contacts_map.get(sender_handle, sender_handle)
            # Also try normalized versions
            if sender_name == sender_handle and sender_handle.startswith("+"):
                sender_name = contacts_map.get(sender_handle[1:], sender_handle)
        else:
            sender_name = "Unknown"
        
        messages.append((sent_ts, sender_name, text))
    
    # If we limited and reversed, reverse back to chronological
    if limit > 0:
        messages.reverse()
    
    return messages


def format_thread_markdown(
    chat_name: str,
    chat_identifier: str,
    first_message_time: str,
    last_message_time: str,
    messages: List[Tuple[str, str, str]],
    thread_num: int = 1
) -> str:
    """Format a single thread as markdown."""
    lines = []
    lines.append(f"# Thread {thread_num}: {chat_name}")
    lines.append(f"**Identifier:** {chat_identifier}")
    lines.append(f"**First Message:** {first_message_time}")
    lines.append(f"**Last Message:** {last_message_time}")
    lines.append(f"**Message Count:** {len(messages)}")
    lines.append("")
    lines.append("## Messages")
    lines.append("")
    
    for sent_ts, sender_name, text in messages:
        lines.append(f"**{sender_name}** [{sent_ts}]")
        lines.append(f"> {text}")
        lines.append("")
    
    return "\n".join(lines)


def format_thread_jsonl(
    chat_id: int,
    chat_name: str,
    chat_identifier: str,
    first_message_time: str,
    last_message_time: str,
    messages: List[Tuple[str, str, str]]
) -> str:
    """Format a single thread as JSONL (one JSON object per message)."""
    import json
    
    lines = []
    for sent_ts, sender_name, text in messages:
        obj = {
            "chat_id": chat_id,
            "chat_name": chat_name,
            "chat_identifier": chat_identifier,
            "first_thread_message": first_message_time,
            "last_thread_message": last_message_time,
            "sent_ts": sent_ts,
            "sender": sender_name,
            "text": text,
        }
        lines.append(json.dumps(obj, ensure_ascii=False))
    
    return "\n".join(lines)


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    # Replace problematic characters
    name = name.replace("/", "_").replace("\\", "_")
    name = name.replace(":", "_").replace("*", "_")
    name = name.replace("?", "_").replace('"', "_")
    name = name.replace("<", "_").replace(">", "_")
    name = name.replace("|", "_")
    # Limit length
    if len(name) > 100:
        name = name[:100]
    return name


def main() -> None:
    args = parse_args()
    
    if args.output and args.output_dir:
        sys.stderr.write("Error: Cannot specify both --output and --output-dir\n")
        sys.exit(1)
    
    # Load contacts mapping
    if args.verbose:
        sys.stderr.write("Loading contacts from AddressBook...\n")
    
    contacts_map = load_contacts_mapping()
    if args.verbose:
        sys.stderr.write(f"Loaded {len(contacts_map)} contact handles\n")
    
    # Copy and open database
    if args.verbose:
        sys.stderr.write(f"Copying Messages database from {args.db}...\n")
    
    copy_path = ensure_copy_readonly(args.db)
    
    try:
        conn = open_ro_connection(copy_path)
    except sqlite3.Error as e:
        sys.stderr.write(f"SQLite error: {e}\n")
        sys.stderr.write("Tip: Grant Full Disk Access to your terminal under System Settings > Privacy & Security.\n")
        sys.exit(2)
    
    # Get recent chat IDs
    if args.verbose:
        sys.stderr.write(f"\nFetching {args.threads} most recent conversation threads...\n")
    
    recent_chats = get_recent_chat_ids(conn, args.threads, contacts_map=contacts_map, verbose=args.verbose)
    
    if not recent_chats:
        sys.stderr.write("No conversation threads found.\n")
        sys.exit(0)
    
    # Process each thread
    if args.verbose:
        sys.stderr.write(f"\nProcessing {len(recent_chats)} threads...\n")
    
    if args.output_dir:
        # Create output directory
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, (chat_id, chat_identifier, display_name, first_msg_time, last_msg_time) in enumerate(recent_chats, 1):
            if args.verbose:
                sys.stderr.write(f"  [{idx}/{len(recent_chats)}] {display_name}...\n")
            
            messages = get_thread_messages(
                conn, 
                chat_id, 
                contacts_map,
                limit=args.messages_per_thread
            )
            
            if args.format == "markdown":
                content = format_thread_markdown(
                    display_name,
                    chat_identifier,
                    first_msg_time,
                    last_msg_time,
                    messages,
                    thread_num=idx
                )
                filename = f"{idx:03d}_{sanitize_filename(display_name)}.md"
            else:  # jsonl
                content = format_thread_jsonl(
                    chat_id,
                    display_name,
                    chat_identifier,
                    first_msg_time,
                    last_msg_time,
                    messages
                )
                filename = f"{idx:03d}_{sanitize_filename(display_name)}.jsonl"
            
            output_path = output_dir / filename
            output_path.write_text(content, encoding="utf-8")
            
            if args.verbose:
                sys.stderr.write(f"    Wrote {len(messages)} messages to {output_path}\n")
        
        print(f"\n✓ Exported {len(recent_chats)} threads to {args.output_dir}")
        
    else:
        # Single output file or stdout
        all_content = []
        
        if args.format == "markdown":
            all_content.append(f"# iMessage Recent Threads Export")
            all_content.append(f"**Exported:** {dt.datetime.now():%Y-%m-%d %H:%M}")
            all_content.append(f"**Thread Count:** {len(recent_chats)}")
            all_content.append("")
            all_content.append("---")
            all_content.append("")
        
        for idx, (chat_id, chat_identifier, display_name, first_msg_time, last_msg_time) in enumerate(recent_chats, 1):
            if args.verbose:
                sys.stderr.write(f"  [{idx}/{len(recent_chats)}] {display_name}...\n")
            
            messages = get_thread_messages(
                conn,
                chat_id,
                contacts_map,
                limit=args.messages_per_thread
            )
            
            if args.format == "markdown":
                thread_content = format_thread_markdown(
                    display_name,
                    chat_identifier,
                    first_msg_time,
                    last_msg_time,
                    messages,
                    thread_num=idx
                )
                all_content.append(thread_content)
                all_content.append("")
                all_content.append("---")
                all_content.append("")
            else:  # jsonl
                thread_content = format_thread_jsonl(
                    chat_id,
                    display_name,
                    chat_identifier,
                    first_msg_time,
                    last_msg_time,
                    messages
                )
                all_content.append(thread_content)
        
        final_content = "\n".join(all_content)
        
        if args.output:
            Path(args.output).write_text(final_content, encoding="utf-8")
            print(f"\n✓ Exported {len(recent_chats)} threads to {args.output}")
        else:
            sys.stdout.write(final_content)
            if sys.stdout.isatty():
                sys.stderr.write(f"\n{len(recent_chats)} threads\n")
    
    conn.close()


if __name__ == "__main__":
    main()

