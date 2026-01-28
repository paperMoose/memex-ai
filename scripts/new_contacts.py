#!/usr/bin/env python3
"""
new_contacts.py

Find contacts recently added to macOS Contacts app and generate follow-up messages.

Usage:
    # Contacts added today with event name
    python3 scripts/new_contacts.py --event "Tech Conference"

    # Contacts added in last 3 days
    python3 scripts/new_contacts.py --days 3 --event "Networking Week"

    # Just show the list (no event name in drafts)
    python3 scripts/new_contacts.py --days 1
"""

from __future__ import annotations

import argparse
import glob
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# macOS Core Data epoch (2001-01-01 00:00:00 UTC)
CORE_DATA_EPOCH = datetime(2001, 1, 1)


def get_contacts_databases() -> List[str]:
    """Find all AddressBook database files."""
    addressbook_root = os.path.expanduser("~/Library/Application Support/AddressBook")
    main_db = os.path.join(addressbook_root, "AddressBook-v22.abcddb")
    source_pattern = os.path.join(addressbook_root, "Sources/*/AddressBook-v22.abcddb")
    
    dbs = []
    if os.path.exists(main_db):
        dbs.append(main_db)
    dbs.extend(glob.glob(source_pattern))
    
    return dbs


def core_data_to_datetime(timestamp: float) -> datetime:
    """Convert Core Data timestamp to datetime."""
    return CORE_DATA_EPOCH + timedelta(seconds=timestamp)


def get_recent_contacts(days: int = 1) -> List[Dict]:
    """
    Query macOS Contacts database for contacts added in the last N days.
    Returns list of contacts with name, phone, and creation date.
    """
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_timestamp = (cutoff - CORE_DATA_EPOCH).total_seconds()
    
    contacts = []
    seen_phones = set()
    
    for db_path in get_contacts_databases():
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            
            # Query contacts with their phone numbers
            sql = """
                SELECT 
                    r.Z_PK as contact_id,
                    r.ZFIRSTNAME as first_name,
                    r.ZLASTNAME as last_name,
                    r.ZORGANIZATION as organization,
                    r.ZCREATIONDATE as creation_date,
                    p.ZFULLNUMBER as phone
                FROM ZABCDRECORD r
                LEFT JOIN ZABCDPHONENUMBER p ON p.ZOWNER = r.Z_PK
                WHERE r.ZCREATIONDATE >= ?
                ORDER BY r.ZCREATIONDATE DESC
            """
            
            for row in conn.execute(sql, [cutoff_timestamp]):
                phone = (row["phone"] or "").strip()
                
                # Skip if no phone or already seen
                if not phone:
                    continue
                if phone in seen_phones:
                    continue
                seen_phones.add(phone)
                
                # Build name
                first = (row["first_name"] or "").strip()
                last = (row["last_name"] or "").strip()
                org = (row["organization"] or "").strip()
                
                name = f"{first} {last}".strip()
                if not name:
                    name = org or "Unknown"
                
                # Parse creation date
                creation_ts = row["creation_date"]
                added_dt = core_data_to_datetime(creation_ts)
                
                contacts.append({
                    "name": name,
                    "first_name": first,
                    "phone": phone,
                    "added": added_dt,
                    "added_str": added_dt.strftime("%Y-%m-%d %H:%M"),
                })
            
            conn.close()
            
        except Exception as e:
            sys.stderr.write(f"Warning: Could not read {db_path}: {e}\n")
            continue
    
    # Sort by added date (newest first)
    contacts.sort(key=lambda c: c["added"], reverse=True)
    
    return contacts


def generate_draft_message(name: str, event_name: Optional[str]) -> str:
    """Generate a draft follow-up message."""
    # Use first name only
    first_name = name.split()[0] if name and name != "Unknown" else "there"
    
    if event_name:
        return f"Hey {first_name}, great meeting you at {event_name} — want to grab coffee next week?"
    else:
        return f"Hey {first_name}, great meeting you — want to grab coffee next week?"


def format_output(contacts: List[Dict], days: int, event_name: Optional[str]) -> str:
    """Format contacts as markdown output."""
    lines = []
    
    day_label = "Day" if days == 1 else "Days"
    lines.append(f"# New Contacts (Last {days} {day_label})")
    lines.append("")
    
    if not contacts:
        lines.append("*No new contacts found.*")
        return "\n".join(lines)
    
    lines.append("## Ready to Message")
    lines.append("")
    
    for c in contacts:
        lines.append(f"### {c['name']}")
        lines.append(f"- **Phone:** {c['phone']}")
        lines.append(f"- **Added:** {c['added_str']}")
        lines.append(f"- **Draft:** {generate_draft_message(c['name'], event_name)}")
        lines.append("")
    
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find contacts recently added to macOS Contacts"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to look back (default: 1)",
    )
    parser.add_argument(
        "--event",
        help="Event name for draft messages (e.g., 'Tech Conference')",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: stdout)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    
    contacts = get_recent_contacts(days=args.days)
    output = format_output(contacts, args.days, args.event)
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"✓ Saved to {args.output}")
    else:
        print(output)
    
    # Summary to stderr
    sys.stderr.write(f"\nFound {len(contacts)} contact(s) added in the last {args.days} day(s)\n")


if __name__ == "__main__":
    main()
