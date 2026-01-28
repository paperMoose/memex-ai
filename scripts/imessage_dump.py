#!/usr/bin/env python3
"""
imessage_dump.py

Read-only exporter for iMessage conversations filtered by contact(s).

Safety:
- Never writes to the live Messages DB. Copies to a temp file, or opens in read-only URI mode.
- Requires Full Disk Access (FDA) for your terminal app to read ~/Library/Messages/chat.db.

Usage examples:
  # Print entire conversation history with a contact to stdout
  python3 scripts/imessage_dump.py --contacts "john smith" --since 2001-01-01

  # Save as markdown
  python3 scripts/imessage_dump.py --contacts "john smith" \
    --since 2018-01-01 --output "/tmp/john_smith_imessage.md"

  # Narrow by multiple handles/tokens (email/phone/name substrings, case-insensitive)
  python3 scripts/imessage_dump.py --contacts "+14155551234,john@example.com,smith" --since yesterday

  # Include empty messages (reactions, images, etc.) - excluded by default
  python3 scripts/imessage_dump.py --contacts "john smith" --since today --include-empty

  # Get the last N messages from a conversation (ignores --since, most recent first)
  python3 scripts/imessage_dump.py --contacts "jane doe" --last 20
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import plistlib
import shutil
import sqlite3
import sys
import tempfile
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


APPLE_EPOCH_UNIX = 978307200  # seconds from 1970-01-01 to 2001-01-01


def extract_text_from_attributed_body(attributed_body: bytes) -> str:
    """Extract plain text from NSAttributedString binary plist format."""
    if not attributed_body:
        return ""
    try:
        data = attributed_body

        # Method 1: Look for NSString marker and extract text after it
        ns_string_marker = b"NSString"
        idx = data.find(ns_string_marker)
        if idx != -1:
            search_start = idx + len(ns_string_marker)
            remaining = data[search_start:]

            # Collect candidate strings
            text_candidates = []
            i = 0
            while i < len(remaining):
                if i + 1 < len(remaining):
                    potential_len = remaining[i]
                    if 1 <= potential_len <= 250 and i + 1 + potential_len <= len(remaining):
                        try:
                            candidate = remaining[i+1:i+1+potential_len].decode('utf-8')
                            if candidate and all(c.isprintable() or c in '\n\r\t' for c in candidate):
                                text_candidates.append(candidate)
                        except:
                            pass
                i += 1

            if text_candidates:
                # Filter out metadata/internal strings
                filtered = [t for t in text_candidates
                           if len(t) > 1
                           and not t.startswith('NS')
                           and not t.startswith('__k')
                           and not t.startswith('at_')
                           and 'MessagePart' not in t
                           and 'Attribute' not in t
                           and 'DataDetected' not in t]
                if filtered:
                    return max(filtered, key=len)

        return ""
    except Exception:
        return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export full iMessage conversations (read-only)")
    parser.add_argument(
        "--db",
        default=os.path.expanduser("~/Library/Messages/chat.db"),
        help="Path to Messages chat.db",
    )
    parser.add_argument(
        "--since",
        default="2001-01-01",
        help="'all'|'today'|'yesterday'|YYYY-MM-DD|YYYY-MM-DD HH:MM (default: 2001-01-01)",
    )
    parser.add_argument(
        "--contacts",
        required=True,
        help="Comma-separated contact/handle substrings to match (case-insensitive)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional hard cap for number of messages (0 = no limit)",
    )
    parser.add_argument(
        "--output",
        help="If set, write to this path; otherwise print to stdout",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "jsonl", "csv"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Include messages with no text (reactions, images, etc.)",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=0,
        help="Get the last N messages (ignores --since, returns most recent messages in chronological order)",
    )
    return parser.parse_args()


def load_contacts_mapping() -> Dict[str, str]:
    """Load phone/email to contact name mapping from macOS Contacts (AddressBook)."""
    handle_to_name: Dict[str, str] = {}
    
    # Find all AddressBook databases (main + sources for different accounts)
    addressbook_root = os.path.expanduser("~/Library/Application Support/AddressBook")
    
    # Check main database
    main_db = os.path.join(addressbook_root, "AddressBook-v22.abcddb")
    
    # Also check all source databases (iCloud, Google, etc.)
    source_pattern = os.path.join(addressbook_root, "Sources/*/AddressBook-v22.abcddb")
    all_dbs = [main_db] + glob.glob(source_pattern)
    
    for db_path in all_dbs:
        if not os.path.exists(db_path):
            continue
            
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            
            # Get phone numbers with contact names
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
                # Normalize phone number (store with and without +)
                phone = row["handle"].strip()
                name = row["name"].strip()
                if phone and name and name != "Unknown":
                    handle_to_name[phone] = name
                    # Also store without + prefix
                    if phone.startswith("+"):
                        handle_to_name[phone[1:]] = name
                    # Also store formatted version
                    normalized = phone.replace("+", "").replace("(", "").replace(")", "").replace(" ", "").replace("-", "")
                    handle_to_name[normalized] = name
            
            # Get email addresses with contact names  
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
            
        except Exception as e:
            # Silently skip databases that can't be read
            continue
    
    return handle_to_name


def ensure_copy_readonly(db_path: str) -> str:
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)
    tmp_dir = tempfile.mkdtemp(prefix="imsg_db_dump_")
    dst = os.path.join(tmp_dir, "chat.copy.db")
    shutil.copy2(db_path, dst)
    # best-effort WAL/SHM for consistency
    for suffix in ("-wal", "-shm"):
        src = db_path + suffix
        if os.path.exists(src):
            try:
                shutil.copy2(src, dst + suffix)
            except Exception:
                pass
    return dst


def parse_since_expr(expr: str) -> dt.datetime:
    now = dt.datetime.now()
    s = expr.strip().lower()
    if s in ("all", "*"):
        return dt.datetime(2001, 1, 1, 0, 0, 0)
    if s == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if s == "yesterday":
        y = now - dt.timedelta(days=1)
        return y.replace(hour=0, minute=0, second=0, microsecond=0)
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dtv = dt.datetime.strptime(expr, fmt)
            if fmt == "%Y-%m-%d":
                dtv = dtv.replace(hour=0, minute=0)
            return dtv
        except ValueError:
            continue
    raise ValueError("--since must be all|today|yesterday|YYYY-MM-DD[ HH:MM]")


def sqlite_since_value(dtv: dt.datetime) -> str:
    return dtv.strftime("%Y-%m-%d %H:%M:%S")


def open_ro_connection(copy_db_path: str) -> sqlite3.Connection:
    uri = f"file:{copy_db_path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def build_contact_where_clause(filters: Sequence[str]) -> Tuple[str, List[str]]:
    clauses: List[str] = []
    params: List[str] = []
    for f in filters:
        if not f:
            continue
        like = f"%{f.lower()}%"
        clauses.append(
            "(LOWER(COALESCE(h.id, '')) LIKE ? OR "
            "LOWER(COALESCE(h.uncanonicalized_id, '')) LIKE ? OR "
            "LOWER(COALESCE(c.display_name, '')) LIKE ? OR "
            "LOWER(COALESCE(c.chat_identifier, '')) LIKE ?)"
        )
        params.extend([like, like, like, like])
    return (" OR ".join(clauses) if clauses else "1=1"), params


def fetch_messages(
    conn: sqlite3.Connection,
    since_iso: str,
    contact_filters: Sequence[str],
    limit: int = 0,
    include_empty: bool = False,
) -> Iterable[Tuple[int, str, int, str, str, str]]:
    """Yield (message_id, sent_iso, is_from_me, sender_handle, chat_name, text) sorted ASC."""
    conn.row_factory = sqlite3.Row
    base_sql = (
        """
        SELECT
            m.ROWID AS message_id,
            datetime(m.date/1000000000 + ?, 'unixepoch') AS sent_ts,
            m.is_from_me AS is_from_me,
            COALESCE(h.id, h.uncanonicalized_id, 'me') AS sender,
            COALESCE(c.display_name, c.chat_identifier, 'unknown') AS chat_name,
            m.text AS text,
            m.attributedBody AS attributed_body
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        LEFT JOIN chat c ON cmj.chat_id = c.ROWID
        WHERE datetime(m.date/1000000000 + ?, 'unixepoch') >= ?
        """
    )
    where_contacts, where_params = build_contact_where_clause(contact_filters)
    sql = base_sql + f" AND ({where_contacts})"

    # Filter out empty messages (reactions, images, etc.) unless --include-empty is set
    if not include_empty:
        sql += " AND (m.text IS NOT NULL AND m.text != '' OR m.attributedBody IS NOT NULL)"

    sql += " ORDER BY m.date ASC"
    if limit and limit > 0:
        sql += " LIMIT ?"

    params: List[object] = [APPLE_EPOCH_UNIX, APPLE_EPOCH_UNIX, since_iso]
    params.extend(where_params)
    if limit and limit > 0:
        params.append(limit)

    cur = conn.execute(sql, params)
    for row in cur:
        # Try text field first, then attributedBody
        text = row["text"] or ""
        if not text and row["attributed_body"]:
            text = extract_text_from_attributed_body(row["attributed_body"])

        # Skip if still no text and not including empty
        if not text and not include_empty:
            continue

        yield (
            int(row["message_id"]),
            str(row["sent_ts"]),
            int(row["is_from_me"] or 0),
            str(row["sender"]),
            str(row["chat_name"]),
            text,
        )


def fetch_last_messages(
    conn: sqlite3.Connection,
    contact_filters: Sequence[str],
    last_n: int,
    include_empty: bool = False,
) -> List[Tuple[int, str, int, str, str, str]]:
    """Fetch the last N messages from a conversation, returned in chronological order."""
    conn.row_factory = sqlite3.Row
    base_sql = """
        SELECT
            m.ROWID AS message_id,
            datetime(m.date/1000000000 + ?, 'unixepoch') AS sent_ts,
            m.is_from_me AS is_from_me,
            COALESCE(h.id, h.uncanonicalized_id, 'me') AS sender,
            COALESCE(c.display_name, c.chat_identifier, 'unknown') AS chat_name,
            m.text AS text,
            m.attributedBody AS attributed_body
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        LEFT JOIN chat c ON cmj.chat_id = c.ROWID
        WHERE 1=1
    """
    where_contacts, where_params = build_contact_where_clause(contact_filters)
    sql = base_sql + f" AND ({where_contacts})"

    # Filter out empty messages unless --include-empty is set
    if not include_empty:
        sql += " AND (m.text IS NOT NULL AND m.text != '' OR m.attributedBody IS NOT NULL)"

    # Order by most recent first, then limit (fetch more to account for filtering)
    sql += " ORDER BY m.date DESC LIMIT ?"

    params: List[object] = [APPLE_EPOCH_UNIX]
    params.extend(where_params)
    # Fetch extra to account for messages that might be filtered out
    params.append(last_n * 3)

    cur = conn.execute(sql, params)
    rows = []
    for row in cur:
        # Try text field first, then attributedBody
        text = row["text"] or ""
        if not text and row["attributed_body"]:
            text = extract_text_from_attributed_body(row["attributed_body"])

        # Skip if still no text and not including empty
        if not text and not include_empty:
            continue

        rows.append((
            int(row["message_id"]),
            str(row["sent_ts"]),
            int(row["is_from_me"] or 0),
            str(row["sender"]),
            str(row["chat_name"]),
            text,
        ))

        # Stop once we have enough
        if len(rows) >= last_n:
            break

    # Reverse to get chronological order (oldest first)
    return list(reversed(rows))


def write_markdown(
    messages: Iterable[Tuple[int, str, int, str, str, str]],
    contacts_label: str,
    since_iso: Optional[str],
    out_path: Optional[str],
    last_n: int = 0,
) -> None:
    lines: List[str] = []
    if last_n > 0:
        header = f"# iMessage Export — {contacts_label}\nExported: {dt.datetime.now():%Y-%m-%d %H:%M}\nLast {last_n} messages\n"
    else:
        header = f"# iMessage Export — {contacts_label}\nExported: {dt.datetime.now():%Y-%m-%d %H:%M}\nSince: {since_iso}\n"
    lines.append(header)
    for msg_id, sent_ts, is_from_me, sender, chat_name, text in messages:
        who = "Me" if is_from_me else sender
        entry = f"- [{sent_ts}] {who}: {text}"
        lines.append(entry)
    content = "\n".join(lines) + "\n"
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {len(lines)-1} messages to {out_path}")
    else:
        sys.stdout.write(content)


def write_jsonl(
    messages: Iterable[Tuple[int, str, int, str, str, str]],
    out_path: Optional[str],
) -> None:
    import json

    def _emit(fp):
        count = 0
        for msg_id, sent_ts, is_from_me, sender, chat_name, text in messages:
            obj = {
                "message_id": msg_id,
                "sent_ts": sent_ts,
                "is_from_me": bool(is_from_me),
                "sender": sender,
                "chat_name": chat_name,
                "text": text,
            }
            fp.write(json.dumps(obj, ensure_ascii=False) + "\n")
            count += 1
        return count

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            n = _emit(f)
        print(f"Wrote {n} messages to {out_path}")
    else:
        n = _emit(sys.stdout)
        if sys.stdout.isatty():
            print(f"\n{n} messages")


def write_csv(
    messages: Iterable[Tuple[int, str, int, str, str, str]],
    out_path: Optional[str],
) -> None:
    import csv

    fieldnames = ["message_id", "sent_ts", "is_from_me", "sender", "chat_name", "text"]
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for msg_id, sent_ts, is_from_me, sender, chat_name, text in messages:
                writer.writerow({
                    "message_id": msg_id,
                    "sent_ts": sent_ts,
                    "is_from_me": bool(is_from_me),
                    "sender": sender,
                    "chat_name": chat_name,
                    "text": text,
                })
        print(f"Wrote CSV to {out_path}")
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        for msg_id, sent_ts, is_from_me, sender, chat_name, text in messages:
            writer.writerow({
                "message_id": msg_id,
                "sent_ts": sent_ts,
                "is_from_me": bool(is_from_me),
                "sender": sender,
                "chat_name": chat_name,
                "text": text,
            })


def main() -> None:
    args = parse_args()

    since_dt = parse_since_expr(args.since)
    since_iso = sqlite_since_value(since_dt)

    contact_filters = [c.strip().lower() for c in args.contacts.split(",") if c.strip()]
    if not contact_filters:
        print("--contacts produced no filters after parsing; provide at least one token", file=sys.stderr)
        sys.exit(2)

    # Load contacts mapping from AddressBook
    try:
        contacts_map = load_contacts_mapping()
        sys.stderr.write(f"Loaded {len(contacts_map)} contact handles from AddressBook\n")
        
        # Expand filters: if a filter matches a contact name, also search by their handles
        expanded_filters = list(contact_filters)
        for filter_term in contact_filters:
            for handle, name in contacts_map.items():
                if filter_term in name.lower():
                    # Add the actual phone/email handle to filters
                    handle_lower = handle.lower()
                    if handle_lower not in expanded_filters:
                        expanded_filters.append(handle_lower)
                        sys.stderr.write(f"  Matched '{name}' -> adding handle: {handle}\n")
        
        contact_filters = expanded_filters
        
    except Exception as e:
        sys.stderr.write(f"Warning: Could not load contacts mapping: {e}\n")
        sys.stderr.write("Continuing with original filters only...\n")

    copy_path = ensure_copy_readonly(args.db)
    try:
        conn = open_ro_connection(copy_path)
    except sqlite3.Error as e:
        sys.stderr.write(f"SQLite error: {e}\n")
        sys.stderr.write("Tip: Grant Full Disk Access to your terminal under System Settings > Privacy & Security.\n")
        sys.exit(2)

    # Use --last mode if specified, otherwise use --since mode
    last_n = max(0, int(args.last or 0))
    if last_n > 0:
        rows = fetch_last_messages(
            conn, contact_filters,
            last_n=last_n,
            include_empty=args.include_empty,
        )
    else:
        rows = list(fetch_messages(
            conn, since_iso, contact_filters,
            limit=max(0, int(args.limit or 0)),
            include_empty=args.include_empty,
        ))

    if args.format == "markdown":
        write_markdown(rows, ", ".join(contact_filters), since_iso, args.output, last_n=last_n)
    elif args.format == "jsonl":
        write_jsonl(rows, args.output)
    else:
        write_csv(rows, args.output)


if __name__ == "__main__":
    main()




