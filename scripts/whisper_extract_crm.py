#!/usr/bin/env python3
"""
Extract transcripts from MacWhisper .whisper files for CRM enrichment.

.whisper files are ZIP archives containing:
- metadata.json: transcription with timestamps and speaker labels
- originalAudio: original audio file
- version: format version

Usage:
    # Extract today's transcripts (DEFAULT - everything created today)
    python3 scripts/whisper_extract_crm.py
    
    # Extract last 3-4 transcripts regardless of date
    python3 scripts/whisper_extract_crm.py --last-n 4
    
    # Extract ALL transcripts from ~/macwhisper
    python3 scripts/whisper_extract_crm.py --all
    
    # Extract specific file
    python3 scripts/whisper_extract_crm.py --file "path/to/file.whisper"
    
    # Specify custom source directory
    python3 scripts/whisper_extract_crm.py --source-dir "/path/to/whisper/files"
    
    # Output as JSON instead of markdown
    python3 scripts/whisper_extract_crm.py --format json
    
    # Specify output directory
    python3 scripts/whisper_extract_crm.py --output-dir "/path/to/output"

DEFAULT BEHAVIOR (no flags):
    - Extracts ALL recordings created/modified TODAY (based on file modification time)
    - This includes the last 3-4 recordings if they were done today
    - Automatically filters to current day only
"""

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def format_timestamp(ms: int) -> str:
    """Convert milliseconds to MM:SS format."""
    seconds = ms / 1000
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def extract_whisper_metadata(whisper_file: Path) -> Optional[Dict]:
    """Extract metadata.json from a .whisper file."""
    try:
        with zipfile.ZipFile(whisper_file, 'r') as z:
            with z.open('metadata.json') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error extracting {whisper_file.name}: {e}", file=sys.stderr)
        return None


def format_transcript_markdown(data: Dict, filename: str) -> str:
    """Format transcript as markdown for CRM enrichment."""
    lines = []
    
    # Header
    lines.append(f"# Transcript: {data.get('originalMediaFilename', filename)}")
    lines.append("")
    
    # Metadata
    lines.append("## Metadata")
    lines.append(f"- **File:** {filename}")
    lines.append(f"- **Language:** {data.get('detectedLanguageRaw', 'unknown')}")
    lines.append(f"- **Model:** {data.get('modelEngine', 'unknown')}")
    
    # Convert date created (Apple's reference date format)
    date_created = data.get('dateCreated')
    if date_created:
        # Apple's reference date is 2001-01-01
        apple_epoch = datetime(2001, 1, 1)
        created_date = apple_epoch.timestamp() + date_created
        lines.append(f"- **Created:** {datetime.fromtimestamp(created_date).strftime('%Y-%m-%d %H:%M:%S')}")
    
    lines.append("")
    
    # Speakers
    speakers = data.get('speakers', [])
    if speakers:
        lines.append("## Speakers")
        for speaker in speakers:
            lines.append(f"- {speaker.get('name', 'Unknown')}")
        lines.append("")
    
    # Full transcript
    lines.append("## Full Transcript")
    lines.append("")
    full_text = " ".join([seg['text'] for seg in data.get('transcripts', [])])
    lines.append(full_text)
    lines.append("")
    
    # Segmented transcript with speakers and timestamps
    lines.append("## Detailed Transcript")
    lines.append("")
    
    for seg in data.get('transcripts', []):
        speaker = seg.get('speaker', {}).get('name', 'Unknown')
        start = format_timestamp(seg.get('start', 0))
        end = format_timestamp(seg.get('end', 0))
        text = seg.get('text', '')
        
        lines.append(f"**{speaker}** [{start} - {end}]")
        lines.append(f"{text}")
        lines.append("")
    
    return "\n".join(lines)


def format_transcript_json(data: Dict, filename: str) -> str:
    """Format transcript as JSON for programmatic CRM enrichment."""
    # Convert date created
    date_created = data.get('dateCreated')
    created_str = None
    if date_created:
        apple_epoch = datetime(2001, 1, 1)
        created_date = apple_epoch.timestamp() + date_created
        created_str = datetime.fromtimestamp(created_date).isoformat()
    
    output = {
        'filename': filename,
        'original_filename': data.get('originalMediaFilename', filename),
        'language': data.get('detectedLanguageRaw', 'unknown'),
        'model': data.get('modelEngine', 'unknown'),
        'created': created_str,
        'speakers': [s.get('name') for s in data.get('speakers', [])],
        'full_text': " ".join([seg['text'] for seg in data.get('transcripts', [])]),
        'segments': [
            {
                'speaker': seg.get('speaker', {}).get('name', 'Unknown'),
                'text': seg.get('text', ''),
                'start_ms': seg.get('start', 0),
                'end_ms': seg.get('end', 0),
                'start_seconds': seg.get('start', 0) / 1000,
                'end_seconds': seg.get('end', 0) / 1000,
            }
            for seg in data.get('transcripts', [])
        ]
    }
    
    return json.dumps(output, indent=2)


def process_whisper_file(
    whisper_file: Path,
    output_dir: Path,
    format_type: str = 'markdown'
) -> bool:
    """Process a single .whisper file and save transcript."""
    print(f"Processing: {whisper_file.name}")
    
    # Extract metadata
    data = extract_whisper_metadata(whisper_file)
    if not data:
        return False
    
    # Format output
    if format_type == 'json':
        content = format_transcript_json(data, whisper_file.name)
        ext = '.json'
    else:
        content = format_transcript_markdown(data, whisper_file.name)
        ext = '.md'
    
    # Save to output directory
    output_file = output_dir / f"{whisper_file.stem}{ext}"
    output_file.write_text(content, encoding='utf-8')
    
    print(f"  ✓ Saved to: {output_file}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Extract transcripts from MacWhisper .whisper files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--source-dir',
        type=Path,
        default=Path.home() / 'macwhisper',
        help='Directory containing .whisper files (default: ~/macwhisper)'
    )
    parser.add_argument(
        '--file',
        type=Path,
        help='Process a single .whisper file instead of directory'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Output directory (default: /tmp/whisper_transcripts_TIMESTAMP)'
    )
    parser.add_argument(
        '--format',
        choices=['markdown', 'json'],
        default='markdown',
        help='Output format (default: markdown)'
    )
    parser.add_argument(
        '--today',
        action='store_true',
        help='Only process recordings from today (default: True unless --all is specified)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Process all recordings (overrides default today-only behavior)'
    )
    parser.add_argument(
        '--last-n',
        type=int,
        help='Process only the last N most recent recordings'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Create output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = Path(f"/tmp/whisper_transcripts_{timestamp}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")
    print()
    
    # Create temp directory for copying files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Get list of files to process
        if args.file:
            if not args.file.exists():
                print(f"Error: File not found: {args.file}", file=sys.stderr)
                return 1
            whisper_files = [args.file]
        else:
            if not args.source_dir.exists():
                print(f"Error: Directory not found: {args.source_dir}", file=sys.stderr)
                return 1
            all_whisper_files = list(args.source_dir.glob('*.whisper'))
            
            # Filter by date/count unless --all is specified
            if args.all:
                whisper_files = all_whisper_files
                print(f"Processing ALL recordings")
            elif args.last_n:
                # Sort by modification time and take last N
                whisper_files = sorted(all_whisper_files, key=lambda f: f.stat().st_mtime)[-args.last_n:]
                print(f"Processing last {args.last_n} recordings (by modification time)")
            else:
                # DEFAULT: only today's recordings (all of them)
                today = datetime.now().date()
                whisper_files = []
                for f in all_whisper_files:
                    file_date = datetime.fromtimestamp(f.stat().st_mtime).date()
                    if file_date == today:
                        whisper_files.append(f)
                print(f"📅 DEFAULT: Processing ALL recordings from today ({today})")
                print(f"   This includes last 3-4 recordings if they were created today")
        
        if not whisper_files:
            print("No .whisper files found matching criteria")
            return 0
        
        print(f"Found {len(whisper_files)} .whisper file(s)")
        print()
        
        # Process each file
        success_count = 0
        for whisper_file in whisper_files:
            # Copy to temp directory (safely work with copy)
            temp_copy = temp_path / whisper_file.name
            if args.verbose:
                print(f"Copying to temp: {whisper_file.name}")
            shutil.copy2(whisper_file, temp_copy)
            
            # Process the temp copy
            if process_whisper_file(temp_copy, output_dir, args.format):
                success_count += 1
            print()
        
        print(f"✓ Successfully processed {success_count}/{len(whisper_files)} files")
        print(f"✓ Transcripts saved to: {output_dir}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

