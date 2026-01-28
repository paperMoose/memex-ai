#!/usr/bin/env python3
"""
Action Items Report
Scans all markdown files in the CRM and extracts open action items,
ranked by priority and date.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass
from enum import IntEnum

class Priority(IntEnum):
    """Priority levels for action items"""
    URGENT = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    NONE = 5

@dataclass
class ActionItem:
    text: str
    file_path: str
    file_name: str
    line_number: int
    priority: Priority
    date_added: Optional[datetime]
    context: str  # Surrounding context (section header, etc.)
    
    def __repr__(self):
        priority_emoji = {
            Priority.URGENT: "🔴",
            Priority.HIGH: "🟡", 
            Priority.MEDIUM: "🟢",
            Priority.LOW: "⚪",
            Priority.NONE: "⚫"
        }
        date_str = self.date_added.strftime("%Y-%m-%d") if self.date_added else "Unknown"
        return f"{priority_emoji[self.priority]} [{date_str}] {self.text} ({self.file_name})"

def extract_priority(text: str) -> Priority:
    """Extract priority level from action item text"""
    text_upper = text.upper()
    if "URGENT" in text_upper or "🔴" in text:
        return Priority.URGENT
    elif "HIGH" in text_upper or "🟡" in text:
        return Priority.HIGH
    elif "MEDIUM" in text_upper or "🟢" in text:
        return Priority.MEDIUM
    elif "LOW" in text_upper or "⚪" in text:
        return Priority.LOW
    else:
        return Priority.NONE

def extract_date(text: str, file_content: List[str], line_idx: int) -> Optional[datetime]:
    """
    Extract date from action item or surrounding context.
    Tries multiple strategies:
    1. Standard *(added YYYY-MM-DD)* format in action item
    2. Date in the action item text itself
    3. Date in nearby "Last Updated" field
    4. Date in surrounding section headers
    """
    # Priority 1: Look for standard *(added YYYY-MM-DD)* format
    added_pattern = r'\*\(added\s+(\d{4}-\d{2}-\d{2})'
    added_match = re.search(added_pattern, text, re.IGNORECASE)
    if added_match:
        try:
            date_str = added_match.group(1)
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            pass
    
    # Priority 2: Look for *(moved from YYYY-MM-DD)* format
    moved_pattern = r'\*\(moved from\s+(\d{4}-\d{2}-\d{2})'
    moved_match = re.search(moved_pattern, text, re.IGNORECASE)
    if moved_match:
        try:
            date_str = moved_match.group(1)
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            pass
    
    # Pattern for various date formats
    date_patterns = [
        r'\b(\d{4}[-/]\d{2}[-/]\d{2})\b',  # YYYY-MM-DD or YYYY/MM/DD
        r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b',  # Month DD, YYYY
        r'\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b',  # MM-DD-YYYY or MM/DD/YYYY
    ]
    
    # Try to find date in the action item text itself
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                date_str = match.group(0)
                # Try parsing with different formats
                for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%b %d, %Y', '%B %d, %Y', '%m-%d-%Y', '%m/%d/%Y']:
                    try:
                        return datetime.strptime(date_str, fmt)
                    except ValueError:
                        continue
            except:
                pass
    
    # Look backwards in file for "Last Updated" or similar
    for i in range(max(0, line_idx - 20), line_idx):
        line = file_content[i]
        if "Last Updated:" in line or "last updated:" in line.lower():
            for pattern in date_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    try:
                        date_str = match.group(0)
                        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%b %d, %Y', '%B %d, %Y']:
                            try:
                                return datetime.strptime(date_str, fmt)
                            except ValueError:
                                continue
                    except:
                        pass
    
    return None

def extract_context(file_content: List[str], line_idx: int) -> str:
    """Extract surrounding context (section headers) for the action item"""
    context_parts = []
    
    # Look backwards for section headers (lines starting with #)
    for i in range(line_idx - 1, max(0, line_idx - 50), -1):
        line = file_content[i].strip()
        if line.startswith('#'):
            # Remove markdown header symbols
            header = re.sub(r'^#+\s*', '', line)
            context_parts.insert(0, header)
            if line.startswith('# '):  # Top-level header, stop here
                break
    
    return " > ".join(context_parts) if context_parts else "Root"

def scan_file(file_path: str) -> List[ActionItem]:
    """Scan a single markdown file for action items"""
    action_items = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for idx, line in enumerate(lines):
            # Look for unchecked action items: - [ ]
            if re.match(r'^\s*-\s*\[\s*\]\s+', line):
                # Extract the action text (remove checkbox)
                text = re.sub(r'^\s*-\s*\[\s*\]\s+', '', line).strip()
                
                # Skip empty action items
                if not text:
                    continue
                
                priority = extract_priority(text)
                date_added = extract_date(text, lines, idx)
                context = extract_context(lines, idx)
                
                action_items.append(ActionItem(
                    text=text,
                    file_path=file_path,
                    file_name=os.path.basename(file_path),
                    line_number=idx + 1,
                    priority=priority,
                    date_added=date_added,
                    context=context
                ))
    
    except Exception as e:
        print(f"Error scanning {file_path}: {e}")
    
    return action_items

def scan_directory(root_dir: str, exclude_dirs: List[str] = None) -> List[ActionItem]:
    """Recursively scan directory for markdown files and extract action items"""
    if exclude_dirs is None:
        exclude_dirs = ['.git', 'node_modules', '__pycache__', '.cursor']
    
    action_items = []
    root_path = Path(root_dir)
    
    # Find all markdown files
    for md_file in root_path.rglob('*.md'):
        # Skip excluded directories
        if any(excluded in str(md_file) for excluded in exclude_dirs):
            continue
        
        items = scan_file(str(md_file))
        action_items.extend(items)
    
    return action_items

def format_report(action_items: List[ActionItem], format: str = 'table') -> str:
    """Format action items into a report"""
    if not action_items:
        return "No action items found."
    
    # Sort by priority first, then by date (newest first)
    sorted_items = sorted(
        action_items,
        key=lambda x: (
            x.priority.value,
            x.date_added if x.date_added else datetime.min
        ),
        reverse=False  # Lower priority value = higher priority
    )
    
    if format == 'table':
        output = []
        output.append("\n" + "="*120)
        output.append("ACTION ITEMS REPORT")
        output.append("="*120 + "\n")
        
        current_priority = None
        for item in sorted_items:
            # Add priority section headers
            if item.priority != current_priority:
                current_priority = item.priority
                priority_names = {
                    Priority.URGENT: "🔴 URGENT",
                    Priority.HIGH: "🟡 HIGH PRIORITY",
                    Priority.MEDIUM: "🟢 MEDIUM PRIORITY",
                    Priority.LOW: "⚪ LOW PRIORITY",
                    Priority.NONE: "⚫ NO PRIORITY"
                }
                output.append(f"\n{'='*120}")
                output.append(f"{priority_names[current_priority]}")
                output.append(f"{'='*120}\n")
            
            date_str = item.date_added.strftime("%Y-%m-%d") if item.date_added else "No date"
            output.append(f"[{date_str}] {item.text}")
            output.append(f"  File: {item.file_path}")
            output.append(f"  Line: {item.line_number}")
            output.append(f"  Context: {item.context}")
            output.append("")
        
        output.append(f"\nTotal: {len(action_items)} action items")
        return "\n".join(output)
    
    elif format == 'json':
        import json
        items_dict = []
        for item in sorted_items:
            items_dict.append({
                'text': item.text,
                'file_path': item.file_path,
                'file_name': item.file_name,
                'line_number': item.line_number,
                'priority': item.priority.name,
                'date_added': item.date_added.isoformat() if item.date_added else None,
                'context': item.context
            })
        return json.dumps(items_dict, indent=2)
    
    elif format == 'markdown':
        output = []
        output.append("# Action Items Report\n")
        
        current_priority = None
        for item in sorted_items:
            if item.priority != current_priority:
                current_priority = item.priority
                priority_names = {
                    Priority.URGENT: "🔴 URGENT",
                    Priority.HIGH: "🟡 HIGH PRIORITY",
                    Priority.MEDIUM: "🟢 MEDIUM PRIORITY",
                    Priority.LOW: "⚪ LOW PRIORITY",
                    Priority.NONE: "⚫ NO PRIORITY"
                }
                output.append(f"\n## {priority_names[current_priority]}\n")
            
            date_str = item.date_added.strftime("%Y-%m-%d") if item.date_added else "No date"
            output.append(f"- **[{date_str}]** {item.text}")
            output.append(f"  - File: `{item.file_path}`")
            output.append(f"  - Line: {item.line_number}")
            output.append(f"  - Context: {item.context}\n")
        
        output.append(f"\n---\n**Total:** {len(action_items)} action items")
        return "\n".join(output)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Scan CRM files for action items and generate report'
    )
    parser.add_argument(
        '--dir',
        default='.',
        help='Root directory to scan (default: current directory)'
    )
    parser.add_argument(
        '--format',
        choices=['table', 'json', 'markdown'],
        default='table',
        help='Output format (default: table)'
    )
    parser.add_argument(
        '--output',
        help='Output file path (default: print to stdout)'
    )
    parser.add_argument(
        '--priority',
        choices=['URGENT', 'HIGH', 'MEDIUM', 'LOW', 'ALL'],
        default='ALL',
        help='Filter by priority level (default: ALL)'
    )
    parser.add_argument(
        '--since',
        help='Only show items added on or after this date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--before',
        help='Only show items added before this date (YYYY-MM-DD)'
    )
    
    args = parser.parse_args()
    
    # Scan for action items
    print(f"Scanning {args.dir} for action items...", flush=True)
    action_items = scan_directory(args.dir)
    
    # Filter by priority if specified
    if args.priority != 'ALL':
        priority_filter = Priority[args.priority]
        action_items = [item for item in action_items if item.priority == priority_filter]
    
    # Filter by date if specified
    if args.since:
        try:
            since_date = datetime.strptime(args.since, '%Y-%m-%d')
            action_items = [item for item in action_items if item.date and item.date >= since_date]
        except ValueError:
            print(f"Error: Invalid date format for --since. Use YYYY-MM-DD")
            return
    
    if args.before:
        try:
            before_date = datetime.strptime(args.before, '%Y-%m-%d')
            action_items = [item for item in action_items if item.date and item.date < before_date]
        except ValueError:
            print(f"Error: Invalid date format for --before. Use YYYY-MM-DD")
            return
    
    # Generate report
    report = format_report(action_items, args.format)
    
    # Output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"Report saved to {args.output}")
    else:
        print(report)

if __name__ == '__main__':
    main()

