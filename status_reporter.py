import os
import re
import argparse # Added for command-line arguments
import sys
from datetime import datetime, timedelta # Added timedelta

# Define base directories
ACTIVE_LEADS_DIR = "active_leads"
PROJECTS_DIR = "projects"
PEOPLE_DIR = "people" # Added PEOPLE_DIR
ARCHIVE_SUBDIR = "archive"
DONE_SUBDIR = "done"
STALE_THRESHOLD_DAYS = 7

# Heuristic section names that often contain "what changed lately" in project files.
UPDATE_SECTION_HEADINGS = [
    "Timeline",
    "Meeting Notes",
    "Notes",
    "Updates",
    "Progress",
]


def _clip_one_line(s: str, max_len: int = 120) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    if not s:
        return ""
    return s if len(s) <= max_len else (s[: max_len - 1] + "…")


def extract_latest_update(file_content: str) -> str:
    """
    Best-effort extraction of a "latest update" snippet from a markdown file.

    Strategy:
    1) Look for a few common narrative sections (Timeline/Meeting Notes/etc.).
    2) Within those, find the most recent dated line/heading and use that line as the snippet.
    3) Fall back to the most recent dated non-status line anywhere in the file.
    """
    if not file_content:
        return "N/A"

    lines = file_content.splitlines()

    # Identify the Status block range so we can avoid treating it as "latest update".
    status_start = None
    status_end = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*##\s+Status\s*$", line, flags=re.IGNORECASE):
            status_start = i
            # find next "## " heading
            for j in range(i + 1, len(lines)):
                if re.match(r"^\s*##\s+\S+", lines[j]):
                    status_end = j
                    break
            if status_end is None:
                status_end = len(lines)
            break

    def in_status_block(idx: int) -> bool:
        if status_start is None or status_end is None:
            return False
        return status_start <= idx < status_end

    # Helper: scan a range of lines for dated lines and pick newest.
    best = (None, None)  # (date_obj, snippet_line)

    def consider_line(idx: int, text: str):
        nonlocal best
        if in_status_block(idx):
            return
        m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if not m:
            return
        d = parse_date_string(m.group(1))
        if not d:
            return
        snippet = _clip_one_line(text)
        if not snippet:
            return
        if best[0] is None or d > best[0]:
            best = (d, snippet)

    # 1) Scan common sections
    for heading in UPDATE_SECTION_HEADINGS:
        # find section header line index
        for i, line in enumerate(lines):
            if re.match(rf"^\s*##\s+{re.escape(heading)}\s*$", line, flags=re.IGNORECASE):
                # scan until next ## heading
                for j in range(i + 1, len(lines)):
                    if re.match(r"^\s*##\s+\S+", lines[j]):
                        end = j
                        break
                else:
                    end = len(lines)

                for k in range(i + 1, end):
                    consider_line(k, lines[k])
                break  # only first matching section

    # 2) If nothing found, scan whole file (excluding status block)
    if best[0] is None:
        for i, line in enumerate(lines):
            consider_line(i, line)

    return best[1] if best[1] else "N/A"

def get_md_files(directory_path, exclude_subdir_name=None):
    """
    Scans a directory for .md files, optionally excluding a specific subdirectory.

    Args:
        directory_path (str): The path to the directory to scan.
        exclude_subdir_name (str, optional): The name of a subdirectory to exclude. Defaults to None.

    Returns:
        list: A list of full paths to .md files.
    """
    md_files = []
    if not os.path.isdir(directory_path):
        # print(f"Warning: Directory not found: {directory_path}") # Optional warning
        return md_files
    for root, dirs, files in os.walk(directory_path):
        if exclude_subdir_name and exclude_subdir_name in dirs:
            dirs.remove(exclude_subdir_name)  # Don't traverse into the excluded subdirectory

        for file in files:
            if file.endswith(".md"):
                md_files.append(os.path.join(root, file))
    return md_files

def extract_field(content_block, field_name):
    """Extracts a specific field value from a Markdown status block using regex."""
    # Regex to find "- **Field Name:** Value" and capture "Value"
    # It handles potential leading/trailing whitespace around the value.
    match = re.search(r"- \*\*" + re.escape(field_name) + r":\*\*\s*(.*)", content_block, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return "N/A"

def extract_reminders(content_block):
    """Extracts all list items from a '## Reminders' section."""
    reminders_match = re.search(r"## Reminders\s*\n(.*?)(?=\n## |\Z)", content_block, re.DOTALL | re.IGNORECASE)
    if not reminders_match:
        return "N/A"
    
    reminders_content = reminders_match.group(1)
    # Find all list items (lines starting with '-' or '*')
    reminder_items = re.findall(r"^\s*[-*]\s+(.*)", reminders_content, re.MULTILINE)
    if reminder_items:
        return "; ".join(r.strip() for r in reminder_items) # Join multiple reminders with a semicolon
    return "N/A"

def parse_date_string(date_str):
    """Attempts to parse a date string from common formats into a datetime.date object."""
    if not date_str or date_str.lower() == "n/a":
        return None

    # If multiple dates indicated by '->', take the last one.
    if "->" in date_str:
        date_str = date_str.split("->")[-1]

    # Clean common markdown like **
    date_str = date_str.replace("**", "").strip()

    # Define common date formats to try
    date_formats = [
        "%Y-%m-%d",      # e.g., 2025-05-09
        "%B %d, %Y",     # e.g., May 9, 2025
        "%b %d, %Y",      # e.g., Mar 9, 2025
        "%m/%d/%Y",      # e.g., 05/09/2025
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None # Could not parse with any known format

def parse_status_block(file_content, file_type):
    """
    Parses the ## Status block from the file content.

    Args:
        file_content (str): The entire content of the Markdown file.
        file_type (str): Either "lead" or "project".

    Returns:
        dict: A dictionary containing the extracted status fields.
    """
    status_data = {}
    # Regex to find the "## Status" section and capture everything until the next ## heading or end of file
    status_block_match = re.search(r"## Status\s*\n(.*?)(?=\n## |\Z)", file_content, re.DOTALL | re.IGNORECASE)

    if not status_block_match:
        # For people files, we might not have a "Status" block but a "Reminders" block
        if file_type == "person":
            status_data["Reminders"] = extract_reminders(file_content)
            # People files might not have a "Last Updated" in a status block
            # We could try to find a general "Last Updated" or rely on file mod time if needed elsewhere
            status_data["LastUpdatedDateObj"] = None 
            status_data["Last Updated"] = "N/A" 
            return status_data
        
        status_data["Error"] = "Status block not found"
        status_data["LastUpdatedDateObj"] = None
        status_data["Last Updated"] = "N/A"
        return status_data

    status_block_content = status_block_match.group(1)

    if file_type == "lead":
        status_data["Stage"] = extract_field(status_block_content, "Stage")
        status_data["Next Step"] = extract_field(status_block_content, "Next Step")
        # status_data["Last Updated"] = extract_field(status_block_content, "Last Updated") # Keep common one below
        status_data["Reason (if Archived)"] = extract_field(status_block_content, "Reason (if Archived)")
    elif file_type == "project":
        status_data["Current Status"] = extract_field(status_block_content, "Current Status")
        status_data["Next Milestone"] = extract_field(status_block_content, "Next Milestone")
        status_data["Due Date"] = extract_field(status_block_content, "Due Date")
        status_data["Completion Date (if Done)"] = extract_field(status_block_content, "Completion Date (if Done)")
        # status_data["Last Updated"] = extract_field(status_block_content, "Last Updated") # Keep common one below
    elif file_type == "person": # Added handling for person type
        # People files might have a different structure or no formal "Status" block
        # We'll primarily look for reminders. Last Updated might be handled differently or not be present.
        status_data["Reminders"] = extract_reminders(file_content) # Extract from general content if no status block
        # If a person file *does* have a "## Status" block for some reason, extract_field would look there.
        # If not, we need a robust way to find "Last Updated" if it exists outside "## Status"
        # For now, let's assume "Last Updated" might be in a status block if one exists,
        # or it might be manually managed / not present for people in the same way as leads/projects.

    last_updated_str = extract_field(status_block_content, "Last Updated")
    status_data["Last Updated"] = last_updated_str
    status_data["LastUpdatedDateObj"] = parse_date_string(last_updated_str)

    return status_data

def dump_directory_content(directory_path, dir_identifier_for_message, exclude_subdir_name=None):
    """Prints the content of all .md files in a directory."""
    md_files = get_md_files(directory_path, exclude_subdir_name=exclude_subdir_name)
    
    # Special handling for people directory as it has no subdirs to exclude by default
    if dir_identifier_for_message == "people" and exclude_subdir_name is not None:
         # This logic might need adjustment if people dir ever has subdirs to exclude by default
        pass # Currently, get_md_files for people dir doesn't take exclude_subdir_name

    if not md_files:
        if exclude_subdir_name and dir_identifier_for_message != "people":
            print(f"No .md files found in '{directory_path}' (excluding '{exclude_subdir_name}').")
        else:
            print(f"No .md files found in '{directory_path}'.")
        return

    for file_path in md_files:
        relative_path = os.path.relpath(file_path)
        print(f"\n--- START FILE: {relative_path} ---\n")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                print(f.read())
        except Exception as e:
            print(f"Error reading file {relative_path}: {e}")
        print(f"\n--- END FILE: {relative_path} ---\n")

def main():
    parser = argparse.ArgumentParser(description="Report status of active leads and projects, or dump their content.")
    parser.add_argument("--dump-content", choices=["leads", "projects", "people"], # Added "people"
                        help="Specify 'leads', 'projects', or 'people' to dump .md file content from the respective directory.")
    parser.add_argument("--include-people-reminders", action="store_true", # New argument
                        help="Include reminders from people files in the status report.")
    
    args = parser.parse_args()

    if args.dump_content:
        if args.dump_content == "leads":
            print(f"Dumping content from '{ACTIVE_LEADS_DIR}' directory (excluding '{ARCHIVE_SUBDIR}')...")
            dump_directory_content(ACTIVE_LEADS_DIR, "leads", exclude_subdir_name=ARCHIVE_SUBDIR)
        elif args.dump_content == "projects":
            print(f"Dumping content from '{PROJECTS_DIR}' directory (excluding '{DONE_SUBDIR}')...")
            dump_directory_content(PROJECTS_DIR, "projects", exclude_subdir_name=DONE_SUBDIR)
        elif args.dump_content == "people":
            print(f"Dumping content from '{PEOPLE_DIR}' directory...")
            dump_directory_content(PEOPLE_DIR, "people") # People dir typically has no subdirs like archive/done
        return # Exit after dumping content

    # --- Original status reporting logic ---
    all_statuses = []
    today = datetime.now().date()

    # Process active leads (excluding archive)
    lead_files = get_md_files(ACTIVE_LEADS_DIR, exclude_subdir_name=ARCHIVE_SUBDIR)
    for file_path in lead_files:
        status_item = {"File": os.path.relpath(file_path), "Type": "Active Lead"}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            parsed_data = parse_status_block(content, "lead")
            status_item.update(parsed_data)

            last_updated_obj = status_item.get("LastUpdatedDateObj")
            if last_updated_obj:
                age = (today - last_updated_obj).days
                if age > STALE_THRESHOLD_DAYS:
                    status_item["Staleness"] = f">{STALE_THRESHOLD_DAYS}d old"
                else:
                    status_item["Staleness"] = "Current"
            else:
                status_item["Staleness"] = "No Date"
        except Exception as e:
            status_item["Error"] = str(e)
            status_item["Staleness"] = "N/A"
        all_statuses.append(status_item)

    # Process projects (excluding done)
    project_files = get_md_files(PROJECTS_DIR, exclude_subdir_name=DONE_SUBDIR)
    for file_path in project_files:
        status_item = {"File": os.path.relpath(file_path), "Type": "Project"}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            parsed_data = parse_status_block(content, "project")
            status_item.update(parsed_data)

            # For in-progress projects, add a lightweight "latest update" snippet so you
            # can see what changed without opening each file.
            current_status = (status_item.get("Current Status") or "").lower()
            if "in progress" in current_status:
                status_item["Latest Update"] = extract_latest_update(content)
            else:
                status_item["Latest Update"] = ""

            last_updated_obj = status_item.get("LastUpdatedDateObj")
            if last_updated_obj:
                age = (today - last_updated_obj).days
                if age > STALE_THRESHOLD_DAYS:
                    status_item["Staleness"] = f">{STALE_THRESHOLD_DAYS}d old"
                else:
                    status_item["Staleness"] = "Current"
            else:
                status_item["Staleness"] = "No Date"
        except Exception as e:
            status_item["Error"] = str(e)
            status_item["Staleness"] = "N/A"
        all_statuses.append(status_item)
    
    # Process people files if requested
    if args.include_people_reminders:
        people_files = get_md_files(PEOPLE_DIR) # No subdirectories to exclude by default
        for file_path in people_files:
            status_item = {"File": os.path.relpath(file_path), "Type": "Person"}
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # For people, we're interested in reminders.
                # The parse_status_block for "person" will now try to get ## Reminders
                # It won't calculate staleness based on "Last Updated" from a Status block unless it exists.
                parsed_data = parse_status_block(content, "person")
                status_item.update(parsed_data)
                
                # People files don't have the same "Staleness" concept tied to a status block's "Last Updated"
                # So, we'll set it to N/A for now or could define a different logic later (e.g., file modification time)
                status_item["Staleness"] = "N/A" 

            except Exception as e:
                status_item["Error"] = str(e)
                status_item["Reminders"] = "Error reading file"
                status_item["Staleness"] = "N/A"
            all_statuses.append(status_item)

    # --- Output Formatting ---
    print(f"Status Report - {today.strftime('%Y-%m-%d')}\n")

    if not all_statuses:
        print("No active leads or projects found in specified directories.")
        return

    # Define a preferred order of columns. Others will be appended alphabetically.
    preferred_headers = [
        "File", "Type", "Staleness", "Stage", "Current Status",
        "Latest Update",
        "Next Step", "Next Milestone", "Last Updated", "Due Date",
        "Completion Date (if Done)", "Reason (if Archived)", "Error"
    ]
    if args.include_people_reminders:
        preferred_headers.insert(2, "Reminders") # Insert Reminders after Type

    # Get all unique keys from all_statuses to form the full header list
    all_keys_found = set()
    for item in all_statuses:
        all_keys_found.update(item.keys())
    
    # Start with preferred headers that actually exist in the data
    final_headers = [h for h in preferred_headers if h in all_keys_found]
    # Add any other keys found in data that are not in preferred_headers, sorted alphabetically
    for key in sorted(list(all_keys_found)):
        if key not in final_headers and key != "LastUpdatedDateObj": # Exclude helper field
            final_headers.append(key)

    # Calculate column widths dynamically
    col_widths = {header: len(header) for header in final_headers} # Initialize with header lengths
    for item in all_statuses:
        for header in final_headers:
            col_widths[header] = max(col_widths[header], len(str(item.get(header, ""))))

    # Print header
    header_row_parts = []
    for header in final_headers:
        header_row_parts.append(header.ljust(col_widths[header]))
    header_row = " | ".join(header_row_parts)
    print(header_row)
    print("-" * len(header_row))

    # Print data rows
    for item in all_statuses:
        row_parts = []
        for header in final_headers:
            value = str(item.get(header, "")) # Use empty string for missing values for cleaner table
            row_parts.append(value.ljust(col_widths[header]))
        print(" | ".join(row_parts))

if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Allow piping to tools like head without an ugly stack trace.
        try:
            sys.stdout.close()
        except Exception:
            pass