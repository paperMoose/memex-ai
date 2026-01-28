#!/usr/bin/env python3
"""
Action Items Standardization Script
Audits and fixes action items to match the standard format defined in
.cursor/rules/action-items-standard.mdc
"""

import os
import re
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ActionItemIssue:
    file_path: str
    line_number: int
    line_content: str
    issue_type: str
    suggested_fix: str
    severity: str  # 'warning' or 'error'

@dataclass
class FileAudit:
    file_path: str
    total_action_items: int
    issues: List[ActionItemIssue]
    has_action_items_section: bool
    last_updated_date: Optional[str]
    
    @property
    def compliance_score(self) -> float:
        """Calculate compliance score (0-100%)"""
        if self.total_action_items == 0:
            return 100.0
        return max(0, 100 - (len(self.issues) / self.total_action_items * 100))

def extract_last_updated(file_content: List[str]) -> Optional[str]:
    """Extract Last Updated date from file"""
    for line in file_content:
        if "Last Updated:" in line or "**Last Updated:**" in line:
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', line)
            if date_match:
                return date_match.group(1)
    return None

def has_action_items_section(file_content: List[str]) -> bool:
    """Check if file has proper ## Action Items section"""
    for line in file_content:
        if re.match(r'^##\s+Action Items\s*$', line.strip()):
            return True
    return False

def is_in_action_items_section(file_content: List[str], line_idx: int) -> bool:
    """Check if a line is within an Action Items section"""
    # Look backwards for section header
    for i in range(line_idx - 1, max(0, line_idx - 50), -1):
        line = file_content[i].strip()
        if line.startswith('## '):
            return 'Action Items' in line or 'action items' in line.lower()
    return False

def is_in_completion_criteria_section(file_content: List[str], line_idx: int) -> bool:
    """Check if line is in Completion Criteria (valid for task context files)"""
    for i in range(line_idx - 1, max(0, line_idx - 30), -1):
        line = file_content[i].strip()
        if line.startswith('## '):
            return 'Completion Criteria' in line
    return False

def has_date_tag(line: str) -> bool:
    """Check if action item has proper date tag"""
    return bool(re.search(r'\*\((added|moved from)\s+\d{4}-\d{2}-\d{2}', line, re.IGNORECASE))

def get_priority(line: str) -> Optional[str]:
    """Extract priority from action item"""
    line_upper = line.upper()
    # Check for text priorities first (preferred)
    if "**URGENT:**" in line or "**Urgent:**" in line:
        return "URGENT"
    elif "**HIGH:**" in line or "**High:**" in line:
        return "HIGH"
    elif "**MEDIUM:**" in line or "**Medium:**" in line:
        return "MEDIUM"
    elif "**LOW:**" in line or "**Low:**" in line:
        return "LOW"
    # Check for unbolded priorities (need fixing)
    elif "URGENT:" in line_upper:
        return "URGENT"
    elif "HIGH:" in line_upper:
        return "HIGH"
    elif "MEDIUM:" in line_upper:
        return "MEDIUM"
    elif "LOW:" in line_upper:
        return "LOW"
    # Check for emoji priorities (need replacing)
    elif "🔴" in line:
        return "URGENT"
    elif "🟡" in line:
        return "HIGH"
    elif "🟢" in line:
        return "MEDIUM"
    elif "⚪" in line or "⚫" in line:
        return "LOW"
    return None

def audit_file(file_path: str) -> FileAudit:
    """Audit a single file for action item compliance"""
    issues = []
    action_items_count = 0
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        last_updated = extract_last_updated(lines)
        has_section = has_action_items_section(lines)
        is_task_context = 'task_context/' in file_path
        
        for idx, line in enumerate(lines):
            # Check if it's an action item
            if not re.match(r'^\s*-\s*\[\s*\]\s+', line):
                continue
            
            action_items_count += 1
            line_num = idx + 1
            
            # Issue 1: Action item not in proper section
            in_action_section = is_in_action_items_section(lines, idx)
            in_completion_section = is_in_completion_criteria_section(lines, idx)
            
            if not is_task_context and not in_action_section:
                issues.append(ActionItemIssue(
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line.strip(),
                    issue_type='wrong_section',
                    suggested_fix='Move to ## Action Items section',
                    severity='warning'
                ))
            
            # Issue 2: Missing priority (CRITICAL - REQUIRED)
            priority = get_priority(line)
            if not priority:
                # Suggest MEDIUM as default if no priority
                cleaned_line = line.strip()
                # Insert after checkbox
                suggested_fix = cleaned_line.replace('- [ ] ', '- [ ] **MEDIUM:** ', 1)
                
                issues.append(ActionItemIssue(
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line.strip(),
                    issue_type='missing_priority',
                    suggested_fix=suggested_fix,
                    severity='error'
                ))
            
            # Issue 3: Missing date tag (CRITICAL - REQUIRED)
            if not has_date_tag(line):
                suggested_date = last_updated or datetime.now().strftime('%Y-%m-%d')
                cleaned_line = line.strip()
                # Add date before existing closing parenthesis if any, or at end
                if cleaned_line.endswith(')'):
                    suggested_fix = cleaned_line[:-1] + f', added {suggested_date})*'
                else:
                    suggested_fix = cleaned_line.rstrip() + f' *(added {suggested_date})*'
                
                issues.append(ActionItemIssue(
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line.strip(),
                    issue_type='missing_date',
                    suggested_fix=suggested_fix,
                    severity='error'
                ))
            
            # Issue 4: Priority keyword not properly formatted
            if priority:
                # Check if it's properly bolded
                if f"**{priority}:**" not in line and f"**{priority.capitalize()}:**" not in line:
                    issues.append(ActionItemIssue(
                        file_path=file_path,
                        line_number=line_num,
                        line_content=line.strip(),
                        issue_type='priority_format',
                        suggested_fix=f'Use **{priority}:** format (bolded text, not emoji)',
                        severity='warning'
                    ))
            
            # Issue 5: Using emoji instead of text priority
            if any(emoji in line for emoji in ['🔴', '🟡', '🟢', '⚪', '⚫']):
                issues.append(ActionItemIssue(
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line.strip(),
                    issue_type='emoji_priority',
                    suggested_fix='Replace emoji with text priority: **URGENT:**, **HIGH:**, **MEDIUM:**, or **LOW:**',
                    severity='warning'
                ))
        
        # Issue 4: File has action items but no ## Action Items section
        if action_items_count > 0 and not has_section and not is_task_context:
            issues.append(ActionItemIssue(
                file_path=file_path,
                line_number=0,
                line_content='',
                issue_type='missing_section',
                suggested_fix='Add ## Action Items section header',
                severity='warning'
            ))
        
        return FileAudit(
            file_path=file_path,
            total_action_items=action_items_count,
            issues=issues,
            has_action_items_section=has_section,
            last_updated_date=last_updated
        )
    
    except Exception as e:
        print(f"Error auditing {file_path}: {e}")
        return FileAudit(
            file_path=file_path,
            total_action_items=0,
            issues=[],
            has_action_items_section=False,
            last_updated_date=None
        )

def audit_directory(root_dir: str, exclude_dirs: List[str] = None) -> List[FileAudit]:
    """Audit all markdown files in directory"""
    if exclude_dirs is None:
        exclude_dirs = ['.git', 'node_modules', '__pycache__', '.cursor']
    
    audits = []
    root_path = Path(root_dir)
    
    for md_file in root_path.rglob('*.md'):
        # Skip excluded directories
        if any(excluded in str(md_file) for excluded in exclude_dirs):
            continue
        
        # Skip files with no action items potential
        if md_file.name in ['README.md', 'ACTION_ITEMS_GUIDE.md']:
            continue
        
        audit = audit_file(str(md_file))
        if audit.total_action_items > 0:  # Only include files with action items
            audits.append(audit)
    
    return audits

def apply_fixes(file_path: str, dry_run: bool = True) -> int:
    """Apply automatic fixes to a file"""
    fixes_applied = 0
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        last_updated = extract_last_updated(lines)
        default_date = last_updated or datetime.now().strftime('%Y-%m-%d')
        modified_lines = []
        
        for line in lines:
            original_line = line
            
            # Check if it's an action item
            if re.match(r'^\s*-\s*\[\s*\]\s+', line):
                modified = False
                
                # Fix 1: Add priority if missing
                priority = get_priority(line)
                if not priority:
                    # Add **MEDIUM:** after checkbox
                    line = line.replace('- [ ] ', '- [ ] **MEDIUM:** ', 1)
                    fixes_applied += 1
                    modified = True
                    priority = 'MEDIUM'  # Update for further processing
                
                # Fix 2: Replace emoji priorities with text
                if any(emoji in line for emoji in ['🔴', '🟡', '🟢', '⚪', '⚫']):
                    emoji_map = {'🔴': 'URGENT', '🟡': 'HIGH', '🟢': 'MEDIUM', '⚪': 'LOW', '⚫': 'LOW'}
                    for emoji, priority_text in emoji_map.items():
                        if emoji in line:
                            # Remove emoji and add text priority if not already there
                            line = line.replace(emoji, '')
                            if f"**{priority_text}:**" not in line:
                                line = line.replace('- [ ] ', f'- [ ] **{priority_text}:** ', 1)
                            fixes_applied += 1
                            modified = True
                            break
                
                # Fix 3: Bold priority keywords if unbolded
                priority = get_priority(line)
                if priority:
                    if f"**{priority}:**" not in line and f"**{priority.capitalize()}:**" not in line:
                        # Replace unbolded with bolded
                        for priority_variant in [priority.upper(), priority.capitalize(), priority.lower()]:
                            if f"{priority_variant}:" in line and f"**{priority_variant}:**" not in line:
                                line = line.replace(f"{priority_variant}:", f"**{priority.upper()}:**", 1)
                                fixes_applied += 1
                                modified = True
                                break
                
                # Fix 4: Add date if missing
                if not has_date_tag(line):
                    cleaned = line.rstrip()
                    # Don't add if it already has other date formats
                    if not re.search(r'\(\d{4}-\d{2}-\d{2}\)', line):
                        cleaned = cleaned + f' *(added {default_date})*\n'
                        fixes_applied += 1
                        modified = True
                        line = cleaned
            
            modified_lines.append(line)
        
        if fixes_applied > 0 and not dry_run:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(modified_lines)
            print(f"✅ Applied {fixes_applied} fixes to {file_path}")
        elif fixes_applied > 0 and dry_run:
            print(f"🔍 Would apply {fixes_applied} fixes to {file_path}")
        
        return fixes_applied
    
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return 0

def format_audit_report(audits: List[FileAudit], show_compliant: bool = False) -> str:
    """Format audit report"""
    output = []
    output.append("\n" + "="*120)
    output.append("ACTION ITEMS STANDARDIZATION AUDIT")
    output.append("="*120 + "\n")
    
    # Summary statistics
    total_files = len(audits)
    total_action_items = sum(a.total_action_items for a in audits)
    total_issues = sum(len(a.issues) for a in audits)
    compliant_files = [a for a in audits if len(a.issues) == 0]
    
    output.append(f"📊 Summary:")
    output.append(f"  - Files scanned: {total_files}")
    output.append(f"  - Total action items: {total_action_items}")
    output.append(f"  - Files with issues: {total_files - len(compliant_files)}")
    output.append(f"  - Total issues found: {total_issues}")
    output.append(f"  - Compliance rate: {len(compliant_files)/total_files*100:.1f}%")
    output.append("")
    
    # Issue breakdown
    issue_types = {}
    for audit in audits:
        for issue in audit.issues:
            issue_types[issue.issue_type] = issue_types.get(issue.issue_type, 0) + 1
    
    if issue_types:
        output.append("🔍 Issue Breakdown:")
        for issue_type, count in sorted(issue_types.items(), key=lambda x: x[1], reverse=True):
            output.append(f"  - {issue_type.replace('_', ' ').title()}: {count}")
        output.append("")
    
    # Files with issues
    non_compliant = [a for a in audits if len(a.issues) > 0]
    if non_compliant:
        output.append("⚠️  Files Needing Attention:")
        output.append("")
        for audit in sorted(non_compliant, key=lambda x: len(x.issues), reverse=True):
            score = audit.compliance_score
            score_emoji = "🔴" if score < 50 else "🟡" if score < 80 else "🟢"
            output.append(f"{score_emoji} {audit.file_path}")
            output.append(f"   Compliance: {score:.0f}% | Action Items: {audit.total_action_items} | Issues: {len(audit.issues)}")
            
            # Show first few issues
            for issue in audit.issues[:3]:
                severity_emoji = "⚠️" if issue.severity == 'warning' else "ℹ️"
                output.append(f"   {severity_emoji} Line {issue.line_number}: {issue.issue_type.replace('_', ' ').title()}")
                if issue.line_content:
                    output.append(f"      Current: {issue.line_content[:80]}")
                output.append(f"      Fix: {issue.suggested_fix[:80]}")
            
            if len(audit.issues) > 3:
                output.append(f"   ... and {len(audit.issues) - 3} more issues")
            output.append("")
    
    # Compliant files
    if show_compliant and compliant_files:
        output.append("✅ Compliant Files:")
        for audit in compliant_files:
            output.append(f"  - {audit.file_path} ({audit.total_action_items} action items)")
        output.append("")
    
    return "\n".join(output)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Audit and standardize action items across CRM files'
    )
    parser.add_argument(
        '--dir',
        default='.',
        help='Root directory to scan (default: current directory)'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Apply automatic fixes (adds dates, formats priorities)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be fixed without making changes (default if --fix not specified)'
    )
    parser.add_argument(
        '--show-compliant',
        action='store_true',
        help='Show compliant files in report'
    )
    parser.add_argument(
        '--file',
        help='Audit or fix a single file instead of directory'
    )
    
    args = parser.parse_args()
    
    # Audit
    if args.file:
        audits = [audit_file(args.file)]
    else:
        print(f"🔍 Scanning {args.dir} for action items...", flush=True)
        audits = audit_directory(args.dir)
    
    # Show report
    print(format_audit_report(audits, args.show_compliant))
    
    # Apply fixes if requested
    if args.fix or args.dry_run:
        print("\n" + "="*120)
        print("APPLYING FIXES" if args.fix else "DRY RUN - SHOWING FIXES")
        print("="*120 + "\n")
        
        total_fixes = 0
        files_fixed = 0
        
        for audit in audits:
            if len(audit.issues) > 0:
                fixes = apply_fixes(audit.file_path, dry_run=not args.fix)
                if fixes > 0:
                    total_fixes += fixes
                    files_fixed += 1
        
        print(f"\n{'✅ Applied' if args.fix else '🔍 Would apply'} {total_fixes} fixes across {files_fixed} files")
        
        if args.dry_run or not args.fix:
            print("\nℹ️  Run with --fix (without --dry-run) to apply these changes")

if __name__ == '__main__':
    main()

