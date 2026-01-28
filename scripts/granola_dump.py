#!/usr/bin/env python3
"""
granola_dump.py

Extract meeting transcripts from Granola's local cache.

Granola stores meeting data in:
  ~/Library/Application Support/Granola/cache-v3.json

This contains:
  - documents: Meeting metadata (title, created_at, notes, attendees)
  - transcripts: Full transcript segments with timestamps

Usage:
    # Extract today's meetings (DEFAULT)
    python3 scripts/granola_dump.py

    # Extract last N meetings
    python3 scripts/granola_dump.py --last-n 5

    # Extract all meetings
    python3 scripts/granola_dump.py --all

    # Extract meetings since a date
    python3 scripts/granola_dump.py --since 2026-01-01

    # Search for meetings by title
    python3 scripts/granola_dump.py --search "standup"

    # Output as JSON
    python3 scripts/granola_dump.py --format json

    # Save to directory
    python3 scripts/granola_dump.py --output-dir /tmp/granola_transcripts
"""

import argparse
import json
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple


GRANOLA_CACHE_PATH = Path.home() / "Library/Application Support/Granola/cache-v3.json"


def load_granola_data() -> Tuple[Dict, Dict]:
    """Load documents and transcripts from Granola cache."""
    if not GRANOLA_CACHE_PATH.exists():
        print(f"Error: Granola cache not found at {GRANOLA_CACHE_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(GRANOLA_CACHE_PATH, 'r') as f:
        data = json.load(f)

    cache = json.loads(data["cache"])
    documents = cache["state"]["documents"]
    transcripts = cache["state"].get("transcripts", {})

    return documents, transcripts


def parse_date(date_str: str) -> date:
    """Parse ISO date string to date object."""
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
    except:
        return None


def filter_documents(
    documents: Dict,
    since: Optional[date] = None,
    search: Optional[str] = None,
    last_n: Optional[int] = None,
    today_only: bool = False,
    include_all: bool = False,
) -> List[Dict]:
    """Filter and sort documents based on criteria."""
    # Convert to list with parsed dates
    docs_list = []
    for doc_id, doc in documents.items():
        if doc.get('deleted_at'):
            continue
        if doc.get('type') != 'meeting':
            continue

        doc_with_id = {**doc, 'doc_id': doc_id}
        created = parse_date(doc.get('created_at', ''))
        doc_with_id['created_date'] = created
        docs_list.append(doc_with_id)

    # Sort by created_at descending (most recent first)
    docs_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    # Apply filters
    if include_all:
        pass  # No filtering
    elif last_n:
        docs_list = docs_list[:last_n]
    elif today_only:
        today = date.today()
        docs_list = [d for d in docs_list if d.get('created_date') == today]
    elif since:
        docs_list = [d for d in docs_list if d.get('created_date') and d['created_date'] >= since]

    # Apply search filter
    if search:
        search_lower = search.lower()
        docs_list = [d for d in docs_list if search_lower in d.get('title', '').lower()]

    return docs_list


def format_transcript_markdown(doc: Dict, segments: List[Dict]) -> str:
    """Format a meeting transcript as markdown."""
    lines = []

    # Header
    title = doc.get('title', 'Untitled Meeting')
    lines.append(f"# {title}")
    lines.append("")

    # Metadata
    lines.append("## Metadata")
    lines.append(f"- **ID:** {doc.get('doc_id', 'unknown')}")
    lines.append(f"- **Created:** {doc.get('created_at', 'unknown')}")
    lines.append(f"- **Updated:** {doc.get('updated_at', 'unknown')}")
    lines.append(f"- **Source:** {doc.get('creation_source', 'unknown')}")

    # People/attendees
    people = doc.get('people', {})
    if people:
        creator = people.get('creator', {})
        if creator:
            lines.append(f"- **Creator:** {creator.get('name', 'unknown')} ({creator.get('email', '')})")

        attendees = people.get('attendees', [])
        if attendees:
            lines.append(f"- **Attendees:** {', '.join([a.get('name', a.get('email', 'unknown')) for a in attendees])}")

    lines.append("")

    # Notes (if any)
    notes_markdown = doc.get('notes_markdown', '').strip()
    if notes_markdown:
        lines.append("## Notes")
        lines.append(notes_markdown)
        lines.append("")

    # Transcript
    if segments:
        lines.append("## Transcript")
        lines.append(f"*{len(segments)} segments*")
        lines.append("")

        for seg in segments:
            timestamp = seg.get('start_timestamp', '')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime('%H:%M:%S')
                except:
                    time_str = timestamp
            else:
                time_str = '??:??:??'

            text = seg.get('text', '').strip()
            source = seg.get('source', 'unknown')

            if text:
                lines.append(f"**[{time_str}]** {text}")
                lines.append("")
    else:
        lines.append("## Transcript")
        lines.append("*No transcript available*")
        lines.append("")

    return "\n".join(lines)


def format_transcript_json(doc: Dict, segments: List[Dict]) -> Dict:
    """Format a meeting transcript as JSON."""
    return {
        'id': doc.get('doc_id'),
        'title': doc.get('title'),
        'created_at': doc.get('created_at'),
        'updated_at': doc.get('updated_at'),
        'creation_source': doc.get('creation_source'),
        'notes_markdown': doc.get('notes_markdown', ''),
        'people': doc.get('people', {}),
        'transcript_segments': segments,
        'segment_count': len(segments),
    }


def main():
    parser = argparse.ArgumentParser(
        description='Extract meeting transcripts from Granola',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--since',
        type=str,
        help='Only include meetings since this date (YYYY-MM-DD, today, yesterday)'
    )
    parser.add_argument(
        '--last-n',
        type=int,
        help='Only include the last N meetings (most recent)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Include all meetings (overrides default today-only behavior)'
    )
    parser.add_argument(
        '--search',
        type=str,
        help='Filter meetings by title (case-insensitive substring match)'
    )
    parser.add_argument(
        '--format',
        choices=['markdown', 'json'],
        default='markdown',
        help='Output format (default: markdown)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output to single file (otherwise stdout)'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Output directory (creates one file per meeting)'
    )
    parser.add_argument(
        '--list-only',
        action='store_true',
        help='Just list meeting titles without transcripts'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output to stderr'
    )

    args = parser.parse_args()

    # Load data
    if args.verbose:
        print(f"Loading Granola data from {GRANOLA_CACHE_PATH}...", file=sys.stderr)

    documents, transcripts = load_granola_data()

    if args.verbose:
        print(f"Found {len(documents)} documents, {len(transcripts)} transcripts", file=sys.stderr)

    # Parse since date
    since_date = None
    if args.since:
        if args.since == 'today':
            since_date = date.today()
        elif args.since == 'yesterday':
            since_date = date.today().replace(day=date.today().day - 1)
        else:
            try:
                since_date = datetime.strptime(args.since, '%Y-%m-%d').date()
            except ValueError:
                print(f"Error: Invalid date format '{args.since}'. Use YYYY-MM-DD, today, or yesterday.", file=sys.stderr)
                sys.exit(1)

    # Filter documents
    # Default behavior: today only (unless --all, --last-n, or --since specified)
    today_only = not args.all and not args.last_n and not args.since

    filtered_docs = filter_documents(
        documents,
        since=since_date,
        search=args.search,
        last_n=args.last_n,
        today_only=today_only,
        include_all=args.all,
    )

    if not filtered_docs:
        if today_only:
            print("No meetings found for today. Use --all or --since to see older meetings.", file=sys.stderr)
        else:
            print("No meetings found matching criteria.", file=sys.stderr)
        return 0

    if args.verbose or args.list_only:
        print(f"\nFound {len(filtered_docs)} meeting(s):", file=sys.stderr)
        for doc in filtered_docs:
            created = doc.get('created_at', '')[:10]
            title = doc.get('title', 'Untitled')[:60]
            print(f"  [{created}] {title}", file=sys.stderr)
        print("", file=sys.stderr)

    if args.list_only:
        return 0

    # Create output directory if specified
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    # Process each meeting
    outputs = []
    for doc in filtered_docs:
        doc_id = doc.get('doc_id') or doc.get('id')
        segments = transcripts.get(doc_id, [])

        if args.format == 'json':
            output = format_transcript_json(doc, segments)
            outputs.append(output)
        else:
            output = format_transcript_markdown(doc, segments)
            outputs.append(output)

        # Write to individual file if output_dir specified
        if args.output_dir:
            safe_title = "".join(c if c.isalnum() or c in ' -_' else '_' for c in doc.get('title', 'untitled')[:50])
            created_date = doc.get('created_at', '')[:10]
            ext = '.json' if args.format == 'json' else '.md'
            filename = f"{created_date}_{safe_title}{ext}"
            filepath = args.output_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                if args.format == 'json':
                    json.dump(output, f, indent=2, ensure_ascii=False)
                else:
                    f.write(output)

            if args.verbose:
                print(f"  Wrote: {filepath}", file=sys.stderr)

    # Write combined output
    if args.output or (not args.output_dir):
        if args.format == 'json':
            content = json.dumps(outputs, indent=2, ensure_ascii=False)
        else:
            content = "\n\n---\n\n".join(outputs)

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Wrote {len(filtered_docs)} meeting(s) to {args.output}", file=sys.stderr)
        else:
            print(content)

    if args.output_dir:
        print(f"Wrote {len(filtered_docs)} meeting(s) to {args.output_dir}", file=sys.stderr)

    return 0


if __name__ == '__main__':
    sys.exit(main())
