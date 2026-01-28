#!/usr/bin/env python3
"""
Person Data Dump - Dead Simple

Dumps ALL data we have about a person from all sources.
AI can then decide what to do with it.

Usage:
    python3 scripts/person_dump.py "Jane Doe"
    python3 scripts/person_dump.py --file people/jane-doe.md
"""

import argparse
import json
import subprocess
import sys
import re
from pathlib import Path

def run_cmd(cmd):
    """Run command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
        return result.stdout
    except Exception as e:
        return f"Error: {e}"

def extract_contact_info(person_file):
    """Extract name, phone, email, company from person file"""
    if not Path(person_file).exists():
        return None, None, None, None
    
    content = Path(person_file).read_text()
    
    # Extract name from title
    name = None
    if match := re.search(r'^# (.+)$', content, re.MULTILINE):
        name = match.group(1)
    
    # Extract phone
    phone = None
    if match := re.search(r'Phone:?\s*(\+?\d[\d\s\-\(\)]+)', content, re.IGNORECASE):
        phone = match.group(1).strip()
    
    # Extract email
    email = None
    if match := re.search(r'Email:?\s*([^\s\n]+@[^\s\n]+)', content, re.IGNORECASE):
        email = match.group(1).strip()
    
    # Extract company/organization
    company = None
    if match := re.search(r'(?:Company|Organization|Current):\s*(.+)$', content, re.MULTILINE | re.IGNORECASE):
        company = match.group(1).strip()
    # Also try to extract from email domain
    elif email and '@' in email:
        domain = email.split('@')[1].split('.')[0]
        if domain not in ['gmail', 'yahoo', 'hotmail', 'outlook', 'icloud', 'me']:
            company = domain
    
    return name, phone, email, company

def find_person_file(name):
    """Try to find person file by name"""
    people_dir = Path("people")
    if not people_dir.exists():
        return None
    
    # Try exact kebab-case match
    kebab = name.lower().replace(' ', '-')
    exact_match = people_dir / f"{kebab}.md"
    if exact_match.exists():
        return str(exact_match)
    
    # Try partial match
    for file in people_dir.glob("*.md"):
        content = file.read_text()
        if re.search(rf'^# {re.escape(name)}$', content, re.MULTILINE | re.IGNORECASE):
            return str(file)
    
    return None

def main():
    parser = argparse.ArgumentParser(description='Dump all data about a person')
    parser.add_argument('name', nargs='?', help='Person name')
    parser.add_argument('--file', help='Person file path')
    parser.add_argument('--phone', help='Phone number')
    parser.add_argument('--email', help='Email address')
    
    args = parser.parse_args()
    
    # Determine name and identifiers
    name = args.name
    phone = args.phone
    email = args.email
    person_file = args.file
    
    # If name provided but no file, try to find it
    if name and not person_file:
        person_file = find_person_file(name)
    
    # If file provided, extract info from it
    company = None
    if person_file:
        extracted_name, extracted_phone, extracted_email, extracted_company = extract_contact_info(person_file)
        name = name or extracted_name
        phone = phone or extracted_phone
        email = email or extracted_email
        company = extracted_company
    
    if not name:
        print("Error: Must provide name or --file", file=sys.stderr)
        sys.exit(1)
    
    # Build identifier list for searching
    identifiers = [name]
    if phone:
        identifiers.append(phone)
        identifiers.append(phone.replace('+1', '').replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', ''))
    if email:
        identifiers.append(email)
        identifiers.append(email.split('@')[0])  # username part
    
    # Build search terms for Whisper (name parts + company)
    whisper_search_terms = []
    name_parts = name.split()
    
    # Add each name part (first, last, etc)
    for part in name_parts:
        if len(part) > 2:  # Skip initials
            whisper_search_terms.append(part)
    
    # Add company if exists
    if company:
        whisper_search_terms.append(company)
    
    print("=" * 80)
    print(f"COMPLETE DATA DUMP: {name}")
    print("=" * 80)
    print(f"Identifiers: {', '.join(identifiers)}")
    if company:
        print(f"Company: {company}")
    if person_file:
        print(f"File: {person_file}")
    print("=" * 80)
    print()
    
    # 1. IMESSAGES
    print("=" * 80)
    print("📱 IMESSAGES")
    print("=" * 80)
    contacts_str = ",".join(identifiers)
    imsg_cmd = f'python3 scripts/imessage_dump.py --contacts "{contacts_str}" --since 2023-01-01 --limit 200'
    imessages = run_cmd(imsg_cmd)
    
    if imessages and len(imessages) > 100:
        print(imessages)
    else:
        print("(No iMessages found)")
    print()
    
    # 2. EMAILS
    print("=" * 80)
    print("📧 EMAILS")
    print("=" * 80)
    
    all_emails = []
    for identifier in identifiers[:5]:  # Limit to first 5 to avoid too many searches
        email_cmd = f'python3 scripts/email_search.py --from "{identifier}" --limit 50 --json'
        output = run_cmd(email_cmd)
        try:
            emails = json.loads(output)
            if emails:
                all_emails.extend(emails)
        except:
            pass
    
    # Deduplicate
    if all_emails:
        unique_emails = {e['id']: e for e in all_emails}.values()
        unique_emails = sorted(unique_emails, key=lambda x: x.get('date', ''), reverse=True)
        
        print(f"Found {len(unique_emails)} emails:\n")
        for email in unique_emails[:50]:  # Show top 50
            date = email.get('date', 'Unknown')
            subject = email.get('subject', 'No subject')
            from_addr = email.get('email', 'Unknown')
            print(f"[{date}] {subject}")
            print(f"  From: {from_addr}")
            print()
    else:
        print("(No emails found)")
    print()
    
    # 3. WHISPER TRANSCRIPTS
    print("=" * 80)
    print("🎙️  WHISPER TRANSCRIPTS")
    print("=" * 80)
    
    # Ensure whisper transcripts are extracted
    whisper_dir = Path("/tmp/whisper_all")
    if not whisper_dir.exists():
        print("Extracting Whisper transcripts...")
        run_cmd("python3 scripts/whisper_extract_crm.py --output-dir /tmp/whisper_all 2>/dev/null")
    
    print(f"Searching for: {', '.join(whisper_search_terms)}")
    print()
    
    # Search for ANY of the terms (name parts or company)
    all_files = set()
    for term in whisper_search_terms:
        whisper_cmd = f'grep -r -i "{term}" /tmp/whisper_all/*.md 2>/dev/null'
        whisper_output = run_cmd(whisper_cmd)
        
        if whisper_output:
            for line in whisper_output.split('\n'):
                if match := re.search(r'/tmp/whisper_all/([^:]+\.md)', line):
                    all_files.add(match.group(1))
    
    if all_files:
        print(f"Mentioned in {len(all_files)} transcript(s):\n")
        
        for filename in sorted(all_files):
            filepath = f"/tmp/whisper_all/{filename}"
            print(f"{'='*80}")
            print(f"📄 {filename}")
            print(f"{'='*80}")
            
            # Read entire transcript
            try:
                with open(filepath, 'r') as f:
                    content = f.read()
                    print(content)
            except Exception as e:
                print(f"(Could not read file: {e})")
            
            print()
    else:
        print("(No Whisper transcripts found)")
    
    print()
    print("=" * 80)
    print("END DATA DUMP")
    print("=" * 80)

if __name__ == "__main__":
    main()

