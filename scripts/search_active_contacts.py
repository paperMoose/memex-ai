#!/usr/bin/env python3
"""
search_active_contacts.py

Extracts primary contacts from active leads/projects and searches recent emails
for those contacts, generating a focused email summary.

Usage:
    python3 scripts/search_active_contacts.py --output /tmp/output.md
"""

import argparse
import subprocess
import re
import sys
from pathlib import Path
from datetime import datetime


def extract_contacts_from_crm(repo_root):
    """Extract primary contact emails/names from active leads and projects."""
    contacts = []
    
    # Directories to scan
    dirs = [
        repo_root / "active_leads",
        repo_root / "projects"
    ]
    
    for dir_path in dirs:
        if not dir_path.exists():
            continue
            
        for md_file in dir_path.glob("*.md"):
            try:
                content = md_file.read_text()
                
                # Extract emails from common patterns
                # Pattern: **Email:** email@domain.com
                email_matches = re.findall(r'\*\*Email:\*\*\s*([^\s<>\n]+@[^\s<>\n]+)', content)
                contacts.extend(email_matches)
                
                # Pattern: email@domain.com in contact info sections
                email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                
                # Only look in first 100 lines (contact info section)
                first_lines = '\n'.join(content.split('\n')[:100])
                more_emails = re.findall(email_pattern, first_lines)
                contacts.extend(more_emails)
                
                # Extract primary contact names
                # Pattern: **Primary Contact:** Name Name
                name_matches = re.findall(r'\*\*Primary Contact:\*\*\s*([A-Za-z]+ [A-Za-z]+)', content)
                contacts.extend(name_matches)
                
                # Pattern: **Name:** Name Name  
                name_matches2 = re.findall(r'\*\*Name:\*\*\s*([A-Za-z]+ [A-Za-z]+)', content)
                contacts.extend(name_matches2)
                
            except Exception as e:
                print(f"Warning: Could not read {md_file}: {e}", file=sys.stderr)
    
    # Deduplicate and filter out common non-person emails
    filtered = set()
    exclude_patterns = [
        'noreply', 'no-reply', 'newsletter', 'notifications', 
        'support@', 'info@', 'hello@', 'team@', 'sales@',
        '@slack.com', '@google.com', '@notification', '@email.',
        'you@company.com', 'you@gmail.com'  # Exclude self (replace with your emails)
    ]
    
    for contact in contacts:
        contact = contact.strip()
        if not contact:
            continue
        
        # Skip excluded patterns
        skip = False
        for pattern in exclude_patterns:
            if pattern.lower() in contact.lower():
                skip = True
                break
        
        if not skip:
            filtered.add(contact)
    
    return list(filtered)


def search_emails_for_contact(contact, script_dir, limit=10):
    """Search emails for a specific contact using email_search.py."""
    try:
        # Try searching by email/name
        result = subprocess.run(
            [
                sys.executable,
                str(script_dir / "email_search.py"),
                "--from", contact,
                "--limit", str(limit)
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            # Filter out header lines
            data_lines = [l for l in lines if l.strip() and not l.startswith('Date') and not l.startswith('--')]
            if data_lines:
                return data_lines
                
    except subprocess.TimeoutExpired:
        print(f"Warning: Timeout searching for {contact}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Error searching for {contact}: {e}", file=sys.stderr)
    
    return []


def main():
    parser = argparse.ArgumentParser(
        description='Search emails for active CRM contacts'
    )
    parser.add_argument('--output', required=True, help='Output markdown file')
    parser.add_argument('--limit', type=int, default=5, help='Max emails per contact')
    
    args = parser.parse_args()
    
    # Get repo root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    
    print("Extracting contacts from active leads and projects...")
    contacts = extract_contacts_from_crm(repo_root)
    print(f"Found {len(contacts)} unique contacts")
    
    # Search emails for each contact
    results = {}
    for i, contact in enumerate(contacts[:30], 1):  # Limit to 30 contacts
        print(f"  [{i}/{min(len(contacts), 30)}] Searching: {contact}")
        emails = search_emails_for_contact(contact, script_dir, args.limit)
        if emails:
            results[contact] = emails
    
    # Generate report
    output_path = Path(args.output)
    with open(output_path, 'w') as f:
        f.write(f"# Active Contact Email Summary\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write(f"Searched {len(contacts)} contacts from active leads/projects.\n")
        f.write(f"Found emails from {len(results)} contacts.\n\n")
        f.write("---\n\n")
        
        if not results:
            f.write("No recent emails found from active contacts.\n")
        else:
            # Sort by contact name
            for contact in sorted(results.keys()):
                emails = results[contact]
                f.write(f"## {contact}\n\n")
                for email in emails[:5]:
                    f.write(f"- {email}\n")
                f.write("\n---\n\n")
    
    print(f"\n✓ Report generated: {output_path}")
    print(f"  Found emails from {len(results)} contacts")


if __name__ == '__main__':
    main()

