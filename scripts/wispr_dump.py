#!/usr/bin/env python3
"""
wispr_dump.py

Extract voice dictations from Wispr Flow's local SQLite database.

Wispr Flow stores dictation history in:
  ~/Library/Application Support/Wispr Flow/flow.sqlite

Each dictation entry includes:
  - formattedText: AI-cleaned dictation text (best quality)
  - asrText: Raw ASR output
  - timestamp, app context, word count, duration

Usage:
    # Extract today's dictations (DEFAULT)
    python3 scripts/wispr_dump.py

    # Extract dictations since a date
    python3 scripts/wispr_dump.py --since 2026-01-20

    # Extract yesterday's dictations
    python3 scripts/wispr_dump.py --since yesterday

    # Extract all dictations
    python3 scripts/wispr_dump.py --all

    # Search dictation text
    python3 scripts/wispr_dump.py --search "pipeline" --all

    # Filter by app
    python3 scripts/wispr_dump.py --app slack --all

    # Output as JSON
    python3 scripts/wispr_dump.py --format json

    # Group by app
    python3 scripts/wispr_dump.py --group-by-app

    # Just stats (no full text)
    python3 scripts/wispr_dump.py --stats --all

    # Save to file
    python3 scripts/wispr_dump.py --output /tmp/wispr_today.md
"""

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict


WISPR_DB_PATH = Path.home() / "Library/Application Support/Wispr Flow/flow.sqlite"


def copy_db_to_tmp() -> Path:
    """Copy SQLite DB to temp dir for safe read-only access."""
    if not WISPR_DB_PATH.exists():
        print(f"Error: Wispr Flow database not found at {WISPR_DB_PATH}", file=sys.stderr)
        sys.exit(1)

    tmp_dir = Path(tempfile.mkdtemp(prefix="wispr_dump_"))
    tmp_db = tmp_dir / "flow.sqlite"
    shutil.copy2(WISPR_DB_PATH, tmp_db)

    # Also copy WAL/SHM if present (for consistency)
    for suffix in ["-wal", "-shm"]:
        src = WISPR_DB_PATH.parent / f"flow.sqlite{suffix}"
        if src.exists():
            shutil.copy2(src, tmp_dir / f"flow.sqlite{suffix}")

    return tmp_db


def parse_since(value: str) -> date:
    """Parse --since value to a date."""
    if value == "today":
        return date.today()
    if value == "yesterday":
        return date.today() - timedelta(days=1)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        # Try relative days like "3d" or "7d"
        if value.endswith("d") and value[:-1].isdigit():
            return date.today() - timedelta(days=int(value[:-1]))
        print(f"Error: Invalid date '{value}'. Use YYYY-MM-DD, today, yesterday, or Nd (e.g. 7d).", file=sys.stderr)
        sys.exit(1)


def query_dictations(
    db_path: Path,
    since: Optional[date] = None,
    until: Optional[date] = None,
    search: Optional[str] = None,
    app_filter: Optional[str] = None,
    include_all: bool = False,
    today_only: bool = False,
) -> List[Dict]:
    """Query dictation entries from the database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    conditions = ["isArchived = 0", "formattedText IS NOT NULL", "length(formattedText) > 0"]
    params = []

    if today_only:
        today_str = date.today().isoformat()
        conditions.append("date(timestamp) = ?")
        params.append(today_str)
    elif since and not include_all:
        conditions.append("date(timestamp) >= ?")
        params.append(since.isoformat())
        if until:
            conditions.append("date(timestamp) <= ?")
            params.append(until.isoformat())

    if search:
        conditions.append("formattedText LIKE ?")
        params.append(f"%{search}%")

    if app_filter:
        conditions.append("LOWER(app) LIKE ?")
        params.append(f"%{app_filter.lower()}%")

    where = " AND ".join(conditions)
    query = f"""
        SELECT transcriptEntityId, timestamp, app, formattedText, asrText,
               numWords, duration
        FROM History
        WHERE {where}
        ORDER BY timestamp ASC
    """

    cursor = conn.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return rows


def format_markdown(rows: List[Dict], group_by_app: bool = False) -> str:
    """Format dictations as markdown."""
    if not rows:
        return "*No dictations found.*"

    lines = []
    total_words = sum(r.get("numWords") or 0 for r in rows)
    total_duration = sum(r.get("duration") or 0 for r in rows)

    # Date range
    first_ts = (rows[0].get("timestamp") or "")[:10] if rows else ""
    last_ts = (rows[-1].get("timestamp") or "")[:10] if rows else ""
    date_range = first_ts if first_ts == last_ts else f"{first_ts} to {last_ts}"

    lines.append(f"# Wispr Flow Dictations")
    lines.append(f"**{len(rows)} dictations** | **{total_words:,} words** | **{total_duration/60:.0f} min** | {date_range}")
    lines.append("")

    if group_by_app:
        by_app: Dict[str, List[Dict]] = {}
        for r in rows:
            app = r.get("app") or "Unknown"
            by_app.setdefault(app, []).append(r)

        for app, app_rows in sorted(by_app.items(), key=lambda x: -len(x[1])):
            app_words = sum(r.get("numWords") or 0 for r in app_rows)
            lines.append(f"## {app} ({len(app_rows)} dictations, {app_words:,} words)")
            lines.append("")
            for r in app_rows:
                _append_entry(lines, r)
    else:
        current_date = None
        for r in rows:
            entry_date = (r.get("timestamp") or "")[:10]
            if entry_date != current_date:
                current_date = entry_date
                lines.append(f"## {current_date}")
                lines.append("")
            _append_entry(lines, r)

    return "\n".join(lines)


def _append_entry(lines: List[str], r: Dict):
    """Append a single dictation entry to lines."""
    try:
        raw_ts = r.get("timestamp") or ""
        ts = datetime.fromisoformat(raw_ts.replace(" +00:00", "+00:00"))
        time_str = ts.strftime("%H:%M")
    except Exception:
        time_str = "??:??"

    app = r.get("app") or ""
    # Shorten common app bundle IDs
    app_short = app.split(".")[-1] if "." in app else app

    words = r.get("numWords") or 0
    text = (r.get("formattedText") or "").strip()

    lines.append(f"**[{time_str}]** `{app_short}` ({words}w)")
    lines.append(f"> {text}")
    lines.append("")


def format_json(rows: List[Dict]) -> str:
    """Format dictations as JSON."""
    entries = []
    for r in rows:
        entries.append({
            "id": r["transcriptEntityId"],
            "timestamp": r["timestamp"],
            "app": r.get("app"),
            "text": (r.get("formattedText") or "").strip(),
            "raw_text": (r.get("asrText") or "").strip(),
            "words": r.get("numWords"),
            "duration_seconds": r.get("duration"),
        })
    return json.dumps(entries, indent=2, ensure_ascii=False)


def format_plain(rows: List[Dict]) -> str:
    """Just the text, concatenated. Useful for piping to other tools."""
    texts = [(r.get("formattedText") or "").strip() for r in rows]
    return "\n\n".join(t for t in texts if t)


def format_stats(rows: List[Dict]) -> str:
    """Summary statistics only."""
    if not rows:
        return "No dictations found."

    total_words = sum(r.get("numWords") or 0 for r in rows)
    total_duration = sum(r.get("duration") or 0 for r in rows)

    # By app
    by_app: Dict[str, int] = {}
    for r in rows:
        app = r.get("app") or "Unknown"
        app_short = app.split(".")[-1] if "." in app else app
        by_app[app_short] = by_app.get(app_short, 0) + 1

    # By date
    by_date: Dict[str, int] = {}
    for r in rows:
        ts = r.get("timestamp") or ""
        d = ts[:10] if ts else "unknown"
        by_date[d] = by_date.get(d, 0) + 1

    lines = [
        f"Dictations: {len(rows)}",
        f"Total words: {total_words:,}",
        f"Total duration: {total_duration/60:.1f} min",
        f"Avg words/dictation: {total_words // len(rows) if rows else 0}",
        "",
        "By app:",
    ]
    for app, count in sorted(by_app.items(), key=lambda x: -x[1]):
        lines.append(f"  {app}: {count}")

    lines.append("")
    lines.append("By date:")
    for d, count in sorted(by_date.items()):
        lines.append(f"  {d}: {count}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extract voice dictations from Wispr Flow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--since", type=str, help="Since date (YYYY-MM-DD, today, yesterday, or Nd like 7d)")
    parser.add_argument("--until", type=str, help="Until date (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="Include all dictations")
    parser.add_argument("--search", type=str, help="Search dictation text (case-insensitive)")
    parser.add_argument("--app", type=str, help="Filter by app name (substring match)")
    parser.add_argument("--format", choices=["markdown", "json", "plain"], default="markdown", help="Output format (default: markdown)")
    parser.add_argument("--group-by-app", action="store_true", help="Group output by app instead of date")
    parser.add_argument("--stats", action="store_true", help="Show summary statistics only")
    parser.add_argument("--output", type=Path, help="Output to file (otherwise stdout)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output to stderr")

    args = parser.parse_args()

    # Copy DB for safe access
    if args.verbose:
        print(f"Copying database from {WISPR_DB_PATH}...", file=sys.stderr)

    tmp_db = copy_db_to_tmp()

    try:
        # Parse dates
        since_date = parse_since(args.since) if args.since else None
        until_date = parse_since(args.until) if args.until else None
        today_only = not args.all and not args.since

        rows = query_dictations(
            tmp_db,
            since=since_date,
            until=until_date,
            search=args.search,
            app_filter=args.app,
            include_all=args.all,
            today_only=today_only,
        )

        if args.verbose:
            print(f"Found {len(rows)} dictation(s)", file=sys.stderr)

        # Format output
        if args.stats:
            content = format_stats(rows)
        elif args.format == "json":
            content = format_json(rows)
        elif args.format == "plain":
            content = format_plain(rows)
        else:
            content = format_markdown(rows, group_by_app=args.group_by_app)

        # Write output
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            print(f"Wrote {len(rows)} dictation(s) to {args.output}", file=sys.stderr)
        else:
            print(content)

    finally:
        # Cleanup temp DB
        shutil.rmtree(tmp_db.parent, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
