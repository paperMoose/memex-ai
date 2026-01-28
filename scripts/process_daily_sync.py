#!/usr/bin/env python3
"""
process_daily_sync.py

Processes raw communication exports (Slack, iMessage, Email) and creates
comprehensive contact directories for each data stream.

Usage:
    python3 scripts/process_daily_sync.py <sync_dir>

Arguments:
    sync_dir - Directory containing raw exports (slack.md, imessages.md, etc.)

Outputs:
    <sync_dir>/SLACK_CONTACTS.md
    <sync_dir>/IMESSAGE_CONTACTS.md
    <sync_dir>/EMAIL_CONTACTS.md
"""

import argparse
import glob
import os
import re
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from datetime import timedelta
from typing import Dict


# Domains/patterns to filter out from email contacts (newsletters, marketing, transactional)
EMAIL_EXCLUDE_PATTERNS = [
    # Newsletter/marketing domains
    '@newsletter.', '@email.', '@mail.', '@e.', '@news.',
    '@offers.', '@promo.', '@marketing.', '@notifications.',
    '@alerts.', '@updates.', '@digest.', '@info.',
    # Transactional domains
    'noreply@', 'no-reply@', 'donotreply@',
    '@noreply.', '@no-reply.',
    # Common marketing senders
    '@substack.com', '@beehiiv.com', '@mailchimp.com',
    '@sendgrid.net', '@amazonaws.com', '@mailgun.org',
    '@constantcontact.com', '@hubspot.com',
    # Social/notification platforms
    '@linkedin.com', '@slack.com', '@github.com',
    '@twitter.com', '@facebook.com', '@instagram.com',
    '@reddit.com', '@discord.com',
    # Payment/receipt platforms
    '@paypal.com', '@stripe.com', '@venmo.com',
    '@square.com', '@shopify.com',
    # Known marketing senders by domain pattern
    'adamandeve', 'bodybuilding.com', 'nordstrom',
    'cookunity', 'ubereats', 'doordash',
    'producthunt', 'parkmobile', 'experian',
    'rocketmoney', 'capitalone', 'schwab',
    'savethechildren', 'hims.com', 'nytimes',
    # Generic patterns
    '@notification', '@mailer.', '@bulk.',
]

# Subject patterns that indicate marketing/transactional emails
SUBJECT_EXCLUDE_PATTERNS = [
    'unsubscribe', 'verification code', 'password reset',
    'your order', 'your receipt', 'payment received',
    'budget update', 'price alert', 'just scheduled',
]

IMESSAGE_SYSTEM_MARKERS = [
    # Verification / passcodes
    'verification code', 'one-time passcode', "we'll never ask you for it",
    # Delivery / receipts
    'track your order', 'estimated delivery window', 'your order',
    # Event blasts / mass notifs
    'reply at http', 'reply at https', 'view at:', 'sent a text blast',
    # Support / transactional
    'support@', 'noreply', 'no-reply',
    # Known placeholders from iMessage exports
    'x$versiony$archivert$topx$objects', 'nsattributedstring', 'streamtyped@nsattributedstring',
]

IMESSAGE_EXCLUDE_NAMES = {
    # Personal/family labels that shouldn't trigger "new people" CRM creation
    'dad', 'mom', 'mum', 'mother', 'father', 'grandma', 'grandpa',
}


def load_contacts_map() -> Dict[str, str]:
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


def resolve_phone_to_name(identifier: str, contacts_map: Dict[str, str]) -> str:
    """Try to resolve a phone number to a contact name."""
    if not identifier or not identifier.startswith('+'):
        return ""
    
    # Try exact match
    if identifier in contacts_map:
        return contacts_map[identifier]
    
    # Try without +
    if identifier[1:] in contacts_map:
        return contacts_map[identifier[1:]]
    
    # Try normalized
    normalized = identifier.replace("+", "").replace("(", "").replace(")", "").replace(" ", "").replace("-", "")
    if normalized in contacts_map:
        return contacts_map[normalized]
    
    return ""


def is_phone_number(name: str) -> bool:
    """Check if a name is actually just a phone number (starts with + and is all digits)."""
    if not name:
        return False
    cleaned = name.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
    return cleaned.isdigit() and len(cleaned) >= 7


def slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')


def normalize_phone(raw: str) -> str:
    """Normalize phone-ish strings to +E164-ish digits for matching."""
    if not raw:
        return ''
    raw = raw.strip()
    plus = '+' if raw.startswith('+') else ''
    digits = re.sub(r'\D+', '', raw)
    return (plus + digits) if digits else ''

def normalize_email(raw: str) -> str:
    if not raw:
        return ''
    return raw.strip().lower()


def extract_emails(text: str):
    if not text:
        return []
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list({normalize_email(e) for e in re.findall(email_pattern, text)})


def extract_phones(text: str):
    """Extract phone-like +E164 strings from arbitrary text."""
    if not text:
        return []
    # +<country><number> with some formatting allowed
    phones = []
    for m in re.findall(r'\+\d[\d()\s.\-]{7,}\d', text):
        p = normalize_phone(m)
        if p:
            phones.append(p)
    return list(set(phones))


def parse_last_updated_date(text: str):
    """Parse a YYYY-MM-DD Last Updated date from a people file (best effort)."""
    if not text:
        return None

    # Common structured field: - **Last Updated:** YYYY-MM-DD
    m = re.search(r'^\s*-\s*\*\*Last Updated:\*\*\s*(\d{4}-\d{2}-\d{2})\s*$', text, flags=re.MULTILINE)
    if m:
        return parse_dt_maybe(m.group(1))

    # Common footer section:
    # ## Last Updated
    # 2025-12-10
    m = re.search(r'^\s*##\s+Last Updated\s*$', text, flags=re.MULTILINE)
    if m:
        after_lines = text[m.end():].splitlines()
        for line in after_lines[:10]:
            dm = re.search(r'(\d{4}-\d{2}-\d{2})', line)
            if dm:
                return parse_dt_maybe(dm.group(1))

    return None


def parse_people_file(md_path: Path):
    """Parse a /people/*.md file into a minimal indexable record."""
    try:
        text = md_path.read_text()
    except Exception:
        return {
            'path': md_path,
            'slug': md_path.stem.lower(),
            'names': set(),
            'emails': set(),
            'phones': set(),
            'last_updated': None,
        }

    names = set()

    # Title: "# Name"
    m = re.search(r'^\s*#\s+(.+?)\s*$', text, flags=re.MULTILINE)
    if m:
        title = m.group(1).strip()
        if title:
            names.add(title)

    # Explicit contact field: - **Name:** ...
    for m in re.finditer(r'^\s*-\s*\*\*Name:\*\*\s*(.+?)\s*$', text, flags=re.MULTILINE):
        val = m.group(1).strip()
        if val:
            names.add(val)

    # Alias extraction: aka "X" / aka 'X'
    for n in list(names):
        for am in re.finditer(r'aka\s+[\"“](.+?)[\"”]', n, flags=re.IGNORECASE):
            alias = am.group(1).strip()
            if alias:
                names.add(alias)

    emails = set(extract_emails(text))
    phones = set(extract_phones(text))

    last_updated = parse_last_updated_date(text)

    return {
        'path': md_path,
        'slug': md_path.stem.lower(),
        'names': names,
        'emails': emails,
        'phones': phones,
        'last_updated': last_updated,
    }


def load_people_index(repo_root: Path):
    """Load basic lookup sets for existing people: slugs + names/aliases + emails + phone numbers."""
    people_dir = repo_root / "people"
    slugs = set()
    names = set()
    emails = set()
    phones = set()

    if not people_dir.exists():
        return slugs, names, emails, phones

    for md in people_dir.glob("*.md"):
        rec = parse_people_file(md)
        slugs.add(rec['slug'])
        for n in rec['names']:
            names.add(slugify(n))
        for e in rec['emails']:
            emails.add(e)
        for p in rec['phones']:
            phones.add(p)

    return slugs, names, emails, phones


def parse_dt_maybe(s: str):
    if not s:
        return None
    s = s.strip()
    # NOTE: slice by expected timestamp length (not len(fmt)).
    candidates = [
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%d %H:%M", 16),
        ("%Y-%m-%d", 10),
    ]
    for fmt, n in candidates:
        try:
            return datetime.strptime(s[:n], fmt)
        except Exception:
            pass
    return None


def is_likely_system_imessage_contact(contact) -> bool:
    """Heuristic filter to remove obvious automated/system threads."""
    name = (contact.get('name') or '').strip()
    identifier = (contact.get('identifier') or '').strip()

    if re.fullmatch(r'\d{4,6}', name or identifier):
        return True

    if name.lower() in {"unknown", "identifier"}:
        return True

    previews = ' '.join((m.get('preview') or '') for m in (contact.get('recent') or [])).lower()
    if any(marker in previews for marker in IMESSAGE_SYSTEM_MARKERS):
        return True

    if (name.startswith('+') or identifier.startswith('+')) and any(marker in previews for marker in IMESSAGE_SYSTEM_MARKERS):
        return True

    return False


def generate_new_people_candidates_report(imessage_contacts, output_path: Path, repo_root: Path):
    """Generate a 'new people' candidate list by diffing iMessage contacts against /people/."""
    existing_slugs, existing_names, existing_emails, existing_phones = load_people_index(repo_root)
    
    # Load contacts map for phone-to-name resolution
    contacts_map = load_contacts_map()

    named_candidates = []
    unknown_number_candidates = []
    seen_unknown_numbers = set()

    for c in imessage_contacts:
        name = (c.get('name') or '').strip()
        identifier = (c.get('identifier') or '').strip()

        # If name is a phone number, try to resolve from contacts
        if is_phone_number(name) or not name:
            resolved = resolve_phone_to_name(identifier, contacts_map)
            if resolved:
                name = resolved
                c['resolved_name'] = name

        if name.lower() in IMESSAGE_EXCLUDE_NAMES:
            continue

        if is_likely_system_imessage_contact(c):
            continue

        # If identifier is an email (iMessage via email)
        identifier_email = normalize_email(identifier) if '@' in identifier else ''
        if identifier_email and identifier_email in existing_emails:
            continue

        # Phone match against existing people
        norm_phone = normalize_phone(identifier) if identifier.startswith('+') else normalize_phone(name) if name.startswith('+') else ''
        if norm_phone and norm_phone in existing_phones:
            continue

        # Name/slug match against existing people (includes alias names extracted from files)
        if name and not is_phone_number(name) and '@' not in name:
            s = slugify(name)
            if s in existing_slugs or s in existing_names:
                continue
            parts = [p for p in re.split(r'\s+', name) if p]
            if len(parts) >= 2:
                first_last = slugify(f"{parts[0]} {parts[-1]}")
                if first_last in existing_slugs or first_last in existing_names:
                    continue
        # Email-ish names (rare but possible)
        if '@' in name and normalize_email(name) in existing_emails:
            continue

        if name and not is_phone_number(name) and '@' not in name:
            named_candidates.append(c)
        else:
            # include iMessage-over-email identifiers too
            if '@' in identifier and normalize_email(identifier) not in existing_emails:
                named_candidates.append(c)
            elif identifier.startswith('+') or is_phone_number(name):
                num = normalize_phone(identifier if identifier.startswith('+') else name)
                if num and num not in seen_unknown_numbers:
                    # Try one more time to resolve from contacts
                    resolved = resolve_phone_to_name(identifier, contacts_map)
                    if resolved:
                        c['resolved_name'] = resolved
                        named_candidates.append(c)
                    else:
                        seen_unknown_numbers.add(num)
                        unknown_number_candidates.append(c)

    def sort_key(c):
        return parse_dt_maybe(c.get('last_msg') or '') or datetime.min

    named_candidates.sort(key=sort_key, reverse=True)
    unknown_number_candidates.sort(key=sort_key, reverse=True)

    with open(output_path, 'w') as f:
        f.write("# New People Candidates (from iMessages)\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write("This report is a best-effort diff of iMessage contacts against `people/*.md`.\n\n")

        f.write("## 📊 Summary\n\n")
        f.write(f"- **Named candidates:** {len(named_candidates)}\n")
        f.write(f"- **Unknown-number candidates:** {len(unknown_number_candidates)}\n\n")

        if named_candidates:
            f.write("## ✅ Named candidates (recommended)\n\n")
            for c in named_candidates:
                display_name = c.get('resolved_name') or c.get('name') or c.get('identifier')
                f.write(f"- **{display_name}**\n")
                if c.get('identifier'):
                    f.write(f"  - Phone/ID: {c.get('identifier')}\n")
                f.write(f"  - Last message: {c.get('last_msg')}\n")
                if c.get('recent'):
                    f.write("  - Recent previews:\n")
                    for m in c['recent'][-3:]:
                        f.write(f"    - [{m.get('date')}] {m.get('sender')}: {m.get('preview')}\n")
            f.write("\n")

        if unknown_number_candidates:
            f.write("## 🤷 Unknown-number candidates (manual triage)\n\n")
            f.write("*These phone numbers could not be resolved to a contact name.*\n\n")
            for c in unknown_number_candidates[:50]:
                display = c.get('identifier') or c.get('name')
                f.write(f"- **{display}**\n")
                f.write(f"  - Last message: {c.get('last_msg')}\n")
                if c.get('recent'):
                    f.write("  - Recent previews:\n")
                    for m in c['recent'][-2:]:
                        f.write(f"    - [{m.get('date')}] {m.get('sender')}: {m.get('preview')}\n")
            if len(unknown_number_candidates) > 50:
                f.write(f"\n*...and {len(unknown_number_candidates) - 50} more unknown-number candidates*\n")
            f.write("\n")


def extract_platform_people_candidates_from_received_emails(email_received_path: Path, repo_root: Path):
    """
    Extract potential "new people" from received emails where the *real person* is
    in the From name, but the From email is a platform address (e.g. LinkedIn invitations).
    """
    existing_slugs, existing_names, existing_emails, existing_phones = load_people_index(repo_root)

    candidates = []
    try:
        content = email_received_path.read_text()
    except Exception:
        return candidates

    lines = content.splitlines()
    data_lines = []
    in_data = False
    for line in lines:
        if not line.strip():
            continue
        if re.match(r'^-+\s*-+', line):
            in_data = True
            continue
        if line.startswith('#') or line.startswith('Timeframe:'):
            continue
        if 'Date' in line and 'From' in line and 'Subject' in line:
            continue
        if in_data:
            data_lines.append(line)

    for line in data_lines:
        parts = re.split(r'\s{2,}', line.strip())
        if len(parts) < 3:
            continue

        date = parts[0].strip()
        from_addr = parts[1].strip()
        subject = parts[2].strip() if len(parts) > 2 else ""
        body = parts[3].strip() if len(parts) > 3 else ""

        m = re.search(r'(.*?)\s*<(.+?)>', from_addr)
        if not m:
            continue

        name = m.group(1).strip()
        email = normalize_email(m.group(2).strip())

        # LinkedIn invites are commonly: Person Name <invitations@linkedin.com>
        is_linkedin_invite = ("linkedin.com" in email) and (
            "requested to connect" in subject.lower() or "just messaged you" in subject.lower() or "requested to connect" in body.lower()
        )
        if not is_linkedin_invite:
            continue

        # Filter out if already in /people by name
        if name:
            s = slugify(name)
            if s in existing_slugs or s in existing_names:
                continue

        # Capture a short, helpful snippet (often includes role/company)
        snippet = (body[:200] if body else "")

        candidates.append({
            'name': name,
            'email': email,
            'date': date,
            'subject': subject,
            'snippet': snippet,
        })

    # Sort by most recent date string (YYYY-MM-DD HH:MM)
    candidates.sort(key=lambda c: c.get('date') or '', reverse=True)
    return candidates


def generate_outreach_drafts_report(
    repo_root: Path,
    imessage_contacts,
    email_received_path: Path,
    output_path: Path,
):
    """
    Generate a human-reviewable list of suggested follow-up messages for
    newly-met contacts discovered via iMessage (including attachment-only) and
    LinkedIn invite emails.

    IMPORTANT: This only generates drafts. It does NOT send messages.
    """
    existing_slugs, existing_names, existing_emails, existing_phones = load_people_index(repo_root)
    
    # Load contacts map for phone-to-name resolution
    contacts_map = load_contacts_map()

    # Collect candidates from iMessage contacts that are not yet in /people
    im_candidates = []
    for c in imessage_contacts or []:
        name = (c.get('name') or '').strip()
        identifier = (c.get('identifier') or '').strip()

        # Only target 1:1-ish contacts we can message directly (phone/email identifiers)
        if not (identifier.startswith('+') or '@' in identifier):
            continue

        # If name is a phone number or missing, try to resolve from contacts
        if not name or is_phone_number(name):
            resolved = resolve_phone_to_name(identifier, contacts_map)
            if resolved:
                name = resolved
            else:
                # Skip if we still can't resolve to a real name
                continue

        if name.lower() in IMESSAGE_EXCLUDE_NAMES:
            continue
        if is_likely_system_imessage_contact(c):
            continue

        # Skip if already tracked
        if identifier.startswith('+') and normalize_phone(identifier) in existing_phones:
            continue
        if '@' in identifier and normalize_email(identifier) in existing_emails:
            continue
        if slugify(name) in existing_slugs or slugify(name) in existing_names:
            continue

        # Store the resolved name back
        c['resolved_name'] = name
        im_candidates.append(c)

    # Candidates from LinkedIn/platform emails
    email_candidates = []
    if email_received_path and email_received_path.exists():
        email_candidates = extract_platform_people_candidates_from_received_emails(email_received_path, repo_root)

    with open(output_path, 'w') as f:
        f.write("# Outreach Drafts (New Contacts)\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write("**DRAFTS ONLY.** Review/edit before sending. Nothing is sent automatically.\n\n")
        f.write("Suggested default (edit the bracketed parts):\n")
        f.write('- iMessage: `Hey {first}, great meeting you at [event/place] — want to grab a drink/coffee sometime next week?`\n')
        f.write('- LinkedIn: `Great meeting you at [event/place] — just accepted your connection request. Want to grab a drink/coffee sometime next week?`\n\n')

        if im_candidates:
            f.write("## iMessage drafts\n\n")
            for c in sorted(im_candidates, key=lambda x: x.get('last_msg') or '', reverse=True)[:25]:
                name = c.get('resolved_name') or (c.get('name') or '').strip()
                ident = (c.get('identifier') or '').strip()
                last_msg = c.get('last_msg') or ''
                first = name.split()[0] if name.split() else name
                f.write(f"### {name}\n\n")
                f.write(f"- **To:** `{ident}`\n")
                f.write(f"- **Last seen:** {last_msg}\n")
                f.write("- **Draft:**\n")
                f.write(f"  - Hey {first}, great meeting you at [event/place] — want to grab a drink/coffee sometime next week?\n\n")

        if email_candidates:
            f.write("## LinkedIn invite email drafts\n\n")
            for c in email_candidates[:25]:
                name = c.get('name') or 'Unknown'
                first = name.split()[0] if name.split() else name
                f.write(f"### {name}\n\n")
                f.write(f"- **Source:** `{c.get('email')}`\n")
                f.write(f"- **Date:** {c.get('date')}\n")
                f.write(f"- **Subject:** {c.get('subject')}\n")
                if c.get('snippet'):
                    f.write(f"- **Snippet:** {c.get('snippet')}\n")
                f.write("- **Draft:**\n")
                f.write(f"  - Great meeting you at [event/place], {first} — just accepted your connection request. Want to grab a drink/coffee sometime next week?\n\n")


def should_exclude_email(email, name='', subject=''):
    """Check if an email should be filtered out."""
    email_lower = email.lower()
    name_lower = name.lower() if name else ''
    subject_lower = subject.lower() if subject else ''
    
    # Check email patterns
    for pattern in EMAIL_EXCLUDE_PATTERNS:
        if pattern.lower() in email_lower:
            return True
    
    # Check subject patterns
    for pattern in SUBJECT_EXCLUDE_PATTERNS:
        if pattern.lower() in subject_lower:
            return True
    
    return False


def parse_imessage_export(filepath):
    """Parse iMessage export and extract contact summaries."""
    contacts = []
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Split into threads
    threads = re.split(r'^# Thread \d+: ', content, flags=re.MULTILINE)[1:]
    
    for i, thread in enumerate(threads, 1):
        lines = thread.split('\n')
        messages_part = thread
        if "## Messages" in thread:
            # Only parse the "Messages" section to avoid metadata polluting previews
            messages_part = thread.split("## Messages", 1)[1]

        # Thread title is the first line after "# Thread N: "
        thread_title = (lines[0].strip() if lines else "").strip()
        
        # Extract metadata
        identifier = ""
        last_msg = ""
        msg_count = 0
        contact_name = ""
        
        for line in lines[:10]:
            if '**Identifier:**' in line:
                identifier = line.split('**Identifier:**')[1].strip()
            elif '**Last Message:**' in line:
                last_msg = line.split('**Last Message:**')[1].strip()
            elif '**Message Count:**' in line:
                msg_count = line.split('**Message Count:**')[1].strip()
        
        # Get contact name from messages
        msg_pattern = r'\*\*(.*?)\*\* \[(\d{4}-\d{2}-\d{2})'
        matches = re.findall(msg_pattern, messages_part)
        
        if matches:
            names = [m[0] for m in matches if m[0] != "Me"]
            if names:
                contact_name = names[0]
        # Fall back to thread title (often the real contact display name)
        if not contact_name and thread_title:
            contact_name = thread_title
        
        # Extract last N messages for preview (across all dates)
        recent_pattern = r'\*\*(.*?)\*\* \[(\d{4}-\d{2}-\d{2}(?: [\d:]+)?)\]\n> (.*?)(?=\n\n|\*\*|$)'
        recent_msgs = re.findall(recent_pattern, messages_part, re.DOTALL)

        preview_msgs = []
        for sender, date, text in recent_msgs[-8:]:  # collect a few, then filter
            preview = text[:200].replace('\n', ' ').strip()
            preview_lower = preview.lower()

            # Drop common placeholder / attachment artifacts to keep previews meaningful
            if not preview:
                continue
            if preview_lower in {"nsattributedstring", "streamtyped@nsattributedstring", "nsmutableattributedstring"}:
                continue
            if preview_lower.startswith("x$versiony$archivert$topx$objects"):
                continue
            if preview_lower.startswith(")at_0_"):
                continue

            preview_msgs.append({
                'sender': sender,
                'date': date[:10] if len(date) >= 10 else date,
                'preview': preview[:150]
            })
        
        if contact_name or identifier:
            last_dt = parse_dt_maybe(last_msg)
            is_recent = bool(last_dt and last_dt >= (datetime.now() - timedelta(days=14)))
            contacts.append({
                'thread': i,
                'name': contact_name,
                'identifier': identifier,
                'last_msg': last_msg,
                'count': msg_count,
                'recent': preview_msgs,
                'is_recent': is_recent
            })
    
    return contacts


def parse_slack_export(filepath):
    """Parse Slack export and extract conversation summaries."""
    conversations = []
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Split by channel headers
    # Matches: "## channel-name" or "## DM: Username" followed by "Messages: N"
    channel_pattern = r'## ([^\n]+)\nMessages: (\d+)'
    channels = re.findall(channel_pattern, content)
    
    for channel, msg_count in channels:
        # Extract messages for this channel
        # Use re.escape to handle special chars in channel names
        channel_section_pattern = rf'## {re.escape(channel)}\nMessages: \d+\n+(.*?)(?=\n## [^\n]+\nMessages:|---\n*$|$)'
        section_match = re.search(channel_section_pattern, content, re.DOTALL)
        
        if section_match:
            msgs_text = section_match.group(1)
            
            # Extract recent messages
            msg_pattern = r'\*\*(.*?)\*\* \[([\d-]+ [\d:]+)\]\n> (.*?)(?=\n\n|\*\*|$)'
            messages = re.findall(msg_pattern, msgs_text, re.DOTALL)
            
            # Get last 5 messages
            preview_msgs = []
            for sender, timestamp, text in messages[-5:]:
                preview = text[:150].replace('\n', ' ').strip()
                preview_msgs.append({
                    'sender': sender,
                    'timestamp': timestamp,
                    'preview': preview
                })
            
            conversations.append({
                'channel': channel,
                'message_count': int(msg_count),
                'recent': preview_msgs
            })
    
    return conversations


def parse_email_export(filepath):
    """Parse email export and extract sender summaries."""
    contacts = defaultdict(lambda: {
        'emails': [],
        'count': 0,
        'last_date': None
    })
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    # Skip header lines (title, timeframe, empty, column headers, separator)
    data_lines = []
    in_data = False
    for line in lines:
        # Skip empty lines and separator lines (dashes only)
        if not line.strip():
            continue
        if re.match(r'^-+\s*-+', line):
            in_data = True
            continue
        if line.startswith('#') or line.startswith('Timeframe:'):
            continue
        if 'Date' in line and 'From' in line and 'Subject' in line:
            continue
        if in_data:
            data_lines.append(line)
    
    # Parse data lines using regex to handle space-separated columns
    # Format: "2056-11-26 16:05  Gorillaz <mail@gorillaz.com>   The Mountain..."
    for line in data_lines:
        # Match: date_time  sender<email>  subject  body
        # Use 2+ spaces as column delimiter
        parts = re.split(r'\s{2,}', line.strip())
        
        if len(parts) >= 3:
            date = parts[0].strip()
            from_addr = parts[1].strip()
            subject = parts[2].strip() if len(parts) > 2 else ""
            body_preview = parts[3].strip() if len(parts) > 3 else ""
            
            if from_addr and '@' in from_addr:
                # Extract name and email
                name_match = re.search(r'(.*?)\s*<(.+?)>', from_addr)
                if name_match:
                    name = name_match.group(1).strip()
                    email = name_match.group(2).strip()
                else:
                    name = from_addr
                    email = from_addr
                
                # Filter out newsletters/marketing
                if should_exclude_email(email, name, subject):
                    continue
                
                key = email.lower()
                contacts[key]['count'] += 1
                contacts[key]['name'] = name
                contacts[key]['email'] = email
                
                if not contacts[key]['last_date'] or date > contacts[key]['last_date']:
                    contacts[key]['last_date'] = date
                
                contacts[key]['emails'].append({
                    'date': date,
                    'subject': subject,
                    'preview': body_preview[:100]
                })
    
    return contacts


def generate_recent_people_touchpoints_report(
    repo_root: Path,
    imessage_contacts,
    email_received_contacts,
    email_sent_contacts,
    output_path: Path,
    days: int = 14,
):
    """
    Report: recently updated people (by Last Updated field) + their latest touchpoints
    from iMessages/emails in this sync.
    """
    people_dir = repo_root / "people"
    if not people_dir.exists():
        return

    # Build iMessage lookup maps
    im_by_phone = {}
    im_by_name = {}
    for c in imessage_contacts or []:
        name = (c.get('name') or '').strip()
        identifier = (c.get('identifier') or '').strip()
        if identifier.startswith('+'):
            im_by_phone[normalize_phone(identifier)] = c
        if name and not name.startswith('+') and '@' not in name:
            im_by_name[slugify(name)] = c

    # Build email lookup maps
    recv_by_email = {normalize_email(v.get('email') or k): v for k, v in (email_received_contacts or {}).items() if (v.get('email') or k)}
    sent_by_email = {normalize_email(v.get('email') or k): v for k, v in (email_sent_contacts or {}).items() if (v.get('email') or k)}

    now = datetime.now()
    cutoff = now - timedelta(days=days)

    recent_people = []
    for md in people_dir.glob("*.md"):
        rec = parse_people_file(md)
        lu = rec.get('last_updated')
        if lu and lu >= cutoff:
            recent_people.append(rec)

    # Sort newest first
    recent_people.sort(key=lambda r: r.get('last_updated') or datetime.min, reverse=True)

    with open(output_path, 'w') as f:
        f.write("# Recent People Touchpoints (for follow-ups)\n")
        f.write(f"*Generated: {now.strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write(f"People included: `people/*.md` where Last Updated is within the last ~{days} days.\n\n")

        f.write("## 📊 Summary\n\n")
        f.write(f"- **People scanned:** {len(list(people_dir.glob('*.md')))}\n")
        f.write(f"- **Recently updated:** {len(recent_people)}\n\n")

        if not recent_people:
            f.write("_No recently updated people files found._\n")
            return

        f.write("## Recently updated people\n\n")
        for rec in recent_people:
            path = rec['path']
            names = [n for n in rec.get('names', []) if n]
            display_name = names[0] if names else path.stem

            f.write(f"### {display_name}\n\n")
            f.write(f"- **File:** people/{path.name}\n")
            f.write(f"- **Last Updated:** {(rec.get('last_updated') or '').strftime('%Y-%m-%d') if rec.get('last_updated') else 'Unknown'}\n")

            # iMessage match (prefer phone)
            matched_im = None
            for p in rec.get('phones', []):
                matched_im = im_by_phone.get(p)
                if matched_im:
                    break
            if not matched_im:
                # fallback: match by name slug
                for n in names:
                    matched_im = im_by_name.get(slugify(n))
                    if matched_im:
                        break

            if matched_im:
                f.write(f"- **Latest iMessage:** {matched_im.get('last_msg')}\n")
                if matched_im.get('recent'):
                    last_preview = matched_im['recent'][-1]
                    f.write(f"  - Preview: [{last_preview.get('date')}] {last_preview.get('sender')}: {last_preview.get('preview')}\n")
            else:
                f.write("- **Latest iMessage:** (no match in this sync export)\n")

            # Email match
            matched_email = None
            for e in rec.get('emails', []):
                em = normalize_email(e)
                if em in recv_by_email or em in sent_by_email:
                    matched_email = em
                    break

            if matched_email:
                recv = recv_by_email.get(matched_email)
                sent = sent_by_email.get(matched_email)

                # Use whichever is newer (string compare works for YYYY-MM-DD HH:MM)
                recv_dt = recv.get('last_date') if recv else None
                sent_dt = sent.get('last_date') if sent else None

                f.write("- **Latest Email:**\n")
                if recv_dt:
                    f.write(f"  - Received: {recv_dt}\n")
                    if recv.get('emails'):
                        f.write(f"    - Subject: {recv['emails'][-1].get('subject')}\n")
                if sent_dt:
                    f.write(f"  - Sent: {sent_dt}\n")
                    if sent.get('emails'):
                        f.write(f"    - Subject: {sent['emails'][-1].get('subject')}\n")
            else:
                f.write("- **Latest Email:** (no match in this sync export)\n")

            f.write("\n")

def generate_imessage_report(contacts, output_path):
    """Generate comprehensive iMessage contact directory."""
    
    with open(output_path, 'w') as f:
        f.write(f"# iMessage Contact Directory\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write("---\n\n")
        
        # Separate into categories
        recent = [c for c in contacts if c.get('is_recent') and c.get('recent')]
        other = [c for c in contacts if not c.get('is_recent')]
        
        f.write(f"## 📊 Summary\n\n")
        f.write(f"- **Total Threads:** {len(contacts)}\n")
        f.write(f"- **Recently Active (last ~14 days):** {len(recent)}\n")
        f.write(f"- **Older / Inactive:** {len(other)}\n\n")
        f.write("---\n\n")
        
        f.write(f"## 🔥 Recently Active Contacts\n\n")
        
        # Sort by last message timestamp (desc)
        recent.sort(key=lambda c: parse_dt_maybe(c.get('last_msg') or '') or datetime.min, reverse=True)
        for contact in recent:
            name = contact['name'] if contact['name'] else contact['identifier']
            f.write(f"### {contact['thread']}. **{name}**\n\n")
            
            if contact['name'] and contact['identifier']:
                f.write(f"- **Phone/ID:** {contact['identifier']}\n")
            
            f.write(f"- **Last Message:** {contact['last_msg']}\n")
            f.write(f"- **Total Messages:** {contact['count']}\n")
            
            if contact['recent']:
                f.write(f"\n**Recent Activity ({len(contact['recent'])} messages):**\n\n")
                for msg in contact['recent'][-3:]:  # Last 3
                    f.write(f"- **[{msg['date']}] {msg['sender']}:** {msg['preview']}\n")
            
            f.write("\n---\n\n")
        
        if other:
            f.write(f"## 💤 Inactive Contacts\n\n")
            for contact in other[:20]:  # Only show first 20
                name = contact['name'] if contact['name'] else contact['identifier']
                f.write(f"- **{name}** - Last: {contact['last_msg'][:10]}\n")
            
            if len(other) > 20:
                f.write(f"\n*...and {len(other) - 20} more inactive contacts*\n")


def generate_slack_report(conversations, output_path):
    """Generate comprehensive Slack conversation directory."""
    
    with open(output_path, 'w') as f:
        f.write(f"# Slack Conversation Directory\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write("---\n\n")
        
        f.write(f"## 📊 Summary\n\n")
        f.write(f"- **Total Conversations:** {len(conversations)}\n")
        total_msgs = sum(c['message_count'] for c in conversations)
        f.write(f"- **Total Messages:** {total_msgs}\n\n")
        f.write("---\n\n")
        
        # Sort by message count
        conversations.sort(key=lambda x: x['message_count'], reverse=True)
        
        for conv in conversations:
            f.write(f"## {conv['channel']}\n\n")
            f.write(f"- **Messages:** {conv['message_count']}\n")
            
            if conv['recent']:
                f.write(f"\n**Recent Messages:**\n\n")
                for msg in conv['recent'][-5:]:
                    f.write(f"- **[{msg['timestamp']}] {msg['sender']}:** {msg['preview']}\n")
            
            f.write("\n---\n\n")


def generate_email_report(contacts, output_path):
    """Generate comprehensive email contact directory."""
    
    with open(output_path, 'w') as f:
        f.write(f"# Email Contact Directory\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write("---\n\n")
        
        f.write(f"## 📊 Summary\n\n")
        f.write(f"- **Total Contacts:** {len(contacts)}\n")
        total_emails = sum(c['count'] for c in contacts.values())
        f.write(f"- **Total Emails:** {total_emails}\n\n")
        f.write("---\n\n")
        
        # Sort by count
        sorted_contacts = sorted(contacts.items(), key=lambda x: x[1]['count'], reverse=True)
        
        for email, data in sorted_contacts:
            name = data.get('name', email)
            f.write(f"## {name}\n\n")
            f.write(f"- **Email:** {data['email']}\n")
            f.write(f"- **Message Count:** {data['count']}\n")
            f.write(f"- **Last Contact:** {data['last_date']}\n")
            
            if data['emails']:
                f.write(f"\n**Recent Emails:**\n\n")
                for email_data in data['emails'][-5:]:
                    f.write(f"- **[{email_data['date']}]** {email_data['subject']}\n")
                    if email_data['preview']:
                        f.write(f"  *Preview:* {email_data['preview']}\n")
            
            f.write("\n---\n\n")


def main():
    parser = argparse.ArgumentParser(
        description='Process daily sync exports into contact directories'
    )
    parser.add_argument('sync_dir', help='Directory containing raw exports')
    
    args = parser.parse_args()
    
    sync_dir = Path(args.sync_dir)
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    
    if not sync_dir.exists():
        print(f"Error: Directory not found: {sync_dir}")
        sys.exit(1)
    
    print(f"Processing daily sync exports from: {sync_dir}")
    print()
    
    # Process iMessages
    imessage_file = sync_dir / "imessages.md"
    imessage_contacts = []
    if imessage_file.exists():
        print("📱 Processing iMessage export...")
        imessage_contacts = parse_imessage_export(imessage_file)
        output = sync_dir / "IMESSAGE_CONTACTS.md"
        generate_imessage_report(imessage_contacts, output)
        print(f"   ✓ Created: {output}")
        print(f"   Found {len(imessage_contacts)} contacts")

        candidates_out = sync_dir / "NEW_PEOPLE_CANDIDATES.md"
        generate_new_people_candidates_report(imessage_contacts, candidates_out, repo_root)
        print(f"   ✓ Created: {candidates_out}")
    else:
        print(f"⚠️  Skipping iMessage (file not found: {imessage_file})")
    
    print()
    
    # Process Slack
    slack_file = sync_dir / "slack.md"
    if slack_file.exists():
        print("💬 Processing Slack export...")
        conversations = parse_slack_export(slack_file)
        output = sync_dir / "SLACK_CONTACTS.md"
        generate_slack_report(conversations, output)
        print(f"   ✓ Created: {output}")
        print(f"   Found {len(conversations)} conversations")
    else:
        print(f"⚠️  Skipping Slack (file not found: {slack_file})")
    
    print()
    
    # Process Emails (Received)
    email_received = sync_dir / "emails_received.md"
    received_contacts = {}
    if email_received.exists():
        print("📧 Processing received emails...")
        received_contacts = parse_email_export(email_received)
        output = sync_dir / "EMAIL_RECEIVED_CONTACTS.md"
        generate_email_report(received_contacts, output)
        print(f"   ✓ Created: {output}")
        print(f"   Found {len(received_contacts)} contacts")
    else:
        print(f"⚠️  Skipping received emails (file not found: {email_received})")
    
    print()
    
    # Process Emails (Sent)
    email_sent = sync_dir / "emails_sent.md"
    sent_contacts = {}
    if email_sent.exists():
        print("📤 Processing sent emails...")
        sent_contacts = parse_email_export(email_sent)
        output = sync_dir / "EMAIL_SENT_CONTACTS.md"
        generate_email_report(sent_contacts, output)
        print(f"   ✓ Created: {output}")
        print(f"   Found {len(sent_contacts)} contacts")
    else:
        print(f"⚠️  Skipping sent emails (file not found: {email_sent})")

    # Cross-source follow-up report: recently updated people + touchpoints
    touchpoints_out = sync_dir / "RECENT_PEOPLE_TOUCHPOINTS.md"
    generate_recent_people_touchpoints_report(
        repo_root=repo_root,
        imessage_contacts=imessage_contacts,
        email_received_contacts=received_contacts,
        email_sent_contacts=sent_contacts,
        output_path=touchpoints_out,
        days=14,
    )
    if touchpoints_out.exists():
        print(f"   ✓ Created: {touchpoints_out}")

    # Augment NEW_PEOPLE_CANDIDATES with platform-mediated email people (e.g., LinkedIn invites)
    if email_received.exists():
        platform_candidates = extract_platform_people_candidates_from_received_emails(email_received, repo_root)
        if platform_candidates:
            # Append section to NEW_PEOPLE_CANDIDATES.md (created earlier during iMessage processing)
            candidates_path = sync_dir / "NEW_PEOPLE_CANDIDATES.md"
            if candidates_path.exists():
                with open(candidates_path, 'a') as f:
                    f.write("\n## 📧 Candidates from emails (platform-mediated)\n\n")
                    f.write("These are extracted from received emails where the sender email is a platform address (e.g. LinkedIn),\n")
                    f.write("but the sender *name* appears to be a real person.\n\n")
                    for c in platform_candidates[:25]:
                        f.write(f"- **{c['name']}** (via `{c['email']}`)\n")
                        f.write(f"  - Date: {c['date']}\n")
                        f.write(f"  - Subject: {c['subject']}\n")
                        if c.get('snippet'):
                            f.write(f"  - Snippet: {c['snippet']}\n")
                    if len(platform_candidates) > 25:
                        f.write(f"\n*...and {len(platform_candidates) - 25} more*\n")
                    f.write("\n")

    # Outreach drafts for newly met contacts (review-only, not sending)
    outreach_out = sync_dir / "OUTREACH_DRAFTS.md"
    generate_outreach_drafts_report(
        repo_root=repo_root,
        imessage_contacts=imessage_contacts,
        email_received_path=email_received if email_received.exists() else Path(""),
        output_path=outreach_out,
    )
    if outreach_out.exists():
        print(f"   ✓ Created: {outreach_out}")
    
    print()
    print("✓ Processing complete!")
    print()
    print("Generated contact directories:")
    for report in ['IMESSAGE_CONTACTS.md', 'NEW_PEOPLE_CANDIDATES.md', 'RECENT_PEOPLE_TOUCHPOINTS.md', 'OUTREACH_DRAFTS.md', 'SLACK_CONTACTS.md', 'EMAIL_RECEIVED_CONTACTS.md', 'EMAIL_SENT_CONTACTS.md']:
        report_path = sync_dir / report
        if report_path.exists():
            print(f"  - {report_path}")


if __name__ == '__main__':
    main()

