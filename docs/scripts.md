# Script Reference

All scripts are in the `scripts/` directory. They require macOS and use only Python standard library.

---

## Quick Reference

| Script | Purpose | Key Flags |
|--------|---------|-----------|
| `reminders_cli.py` | Create Apple Reminders from `@reminder()` tags | `--dry-run`, `--report-day` |
| `calendar_cli.py` | Create Calendar events from `@calendar()` tags | `--dry-run`, `--verbose` |
| `imessage_send.py` | Send iMessages from `@imessage()` tags | `--yes` (required to send) |
| `imessage_dump.py` | Export iMessage conversations | `--contacts`, `--since` |
| `imessage_recent_threads.py` | Export N most recent threads | `--threads`, `--output-dir` |
| `imessage_ingest.py` | Extract tasks from iMessages | `--since`, `--dry-run` |
| `email_search.py` | Fast SQLite email search | `--from`, `--subject`, `--json` |
| `targeted_cleanup.py` | Delete unwanted emails | `--delete --yes` |
| `slack_dump.py` | Export Slack conversations | `--channels`, `--since` |
| `whisper_extract_crm.py` | Extract MacWhisper transcripts | `--source-dir`, `--format` |
| `granola_dump.py` | Extract Granola meeting transcripts | `--since`, `--search` |
| `wispr_dump.py` | Extract Wispr Flow dictations | `--since`, `--app` |
| `person_dump.py` | Dump all data for one person | `"Name"` (positional) |
| `new_contacts.py` | Find recently added contacts | `--days`, `--event` |
| `action_items_report.py` | Extract action items from CRM | `--priority`, `--format` |
| `daily_sync.sh` | Master workflow orchestrator | `today`, `yesterday`, `last-week` |
| `focus_timer.sh` | Pomodoro-style focus timer | `"task" minutes interval` |
| `standardize_action_items.py` | Standardize action item format | |
| `search_active_contacts.py` | Find emails from CRM contacts | `--output` |
| `process_daily_sync.py` | Process raw exports into reports | `<sync_dir>` |
| `automated_daily_sync.sh` | Automated sync (launchd) | |

---

## Automation Scripts

### Apple Reminders (`reminders_cli.py`)

Scans markdown files for `@reminder(...)` tags and creates Apple Reminders via AppleScript. Idempotent by design.

**Tag Format:**
```markdown
@reminder(message="Task name", at="2025-08-16 09:30", list="Work", note="optional note", priority=1, flagged=true, id="unique-id")
```

**Parameters:**
- `message` (required): Reminder title
- `at` (required): Trigger time - absolute (`YYYY-MM-DD HH:MM`), relative (`today HH:MM`, `tomorrow HH:MM`), or offset (`+30m`, `+2h`, `+1d`)
- `list` (optional): Apple Reminders list name
- `note` (optional): Additional context
- `priority` (optional): 1 (high), 5 (medium), 9 (low)
- `flagged` (optional): `true` or `false`
- `id` (optional): Stable identifier for idempotency

**Usage:**
```bash
python3 scripts/reminders_cli.py --file "weeks/week of 2025-08-18.md" --dry-run --verbose
python3 scripts/reminders_cli.py --file "weeks/week of 2025-08-18.md" --verbose
python3 scripts/reminders_cli.py --report-day today
python3 scripts/reminders_cli.py --file "weeks/week of 2025-08-18.md" --reset-log
```

---

### Apple Calendar (`calendar_cli.py`)

Creates Calendar events from `@calendar(...)` tags.

**Tag Format:**
```markdown
@calendar(message="Focus block: Draft PRD", at="2025-08-16 10:00", duration="90m", calendar="Work", location="Desk", note="context.md")
```

**Parameters:**
- `message` (required): Event title
- `at` (required): Start time (same formats as reminders)
- `duration` (optional): `30m`, `1h`, `90m` (default: `60m`)
- `calendar` (optional): Calendar name
- `location`, `note` (optional)

**Usage:**
```bash
python3 scripts/calendar_cli.py --file "weeks/week of 2025-08-18.md" --dry-run --verbose
python3 scripts/calendar_cli.py --file "weeks/week of 2025-08-18.md" --verbose
```

---

### iMessage Send (`imessage_send.py`)

Sends iMessages from `@imessage(...)` tags. **Dry-run by default.**

**Tag Format:**
```markdown
@imessage(to="+14155551234", message="Hey, quick question about the project")
@imessage(to="user@example.com", message="Thanks for the intro!")
```

**Usage:**
```bash
python3 scripts/imessage_send.py --file "weeks/week of 2025-08-18.md"           # dry-run
python3 scripts/imessage_send.py --file "weeks/week of 2025-08-18.md" --yes     # actually send
```

---

## Collection Scripts

### iMessage Dump (`imessage_dump.py`)

Read-only export of iMessage conversations.

```bash
python3 scripts/imessage_dump.py --contacts "john smith" --since 2024-01-01 --output /tmp/john.md
python3 scripts/imessage_dump.py --contacts "+14155551234,user@example.com" --since yesterday
python3 scripts/imessage_dump.py --contacts "sarah" --since today --format jsonl
```

---

### iMessage Recent Threads (`imessage_recent_threads.py`)

Fetches N most recent conversation threads automatically.

```bash
python3 scripts/imessage_recent_threads.py --threads 30 --output /tmp/recent.md
python3 scripts/imessage_recent_threads.py --threads 30 --output-dir /tmp/recent/
python3 scripts/imessage_recent_threads.py --threads 30 --messages-per-thread 100
```

---

### iMessage Ingest (`imessage_ingest.py`)

Scans iMessages for task cues ("todo:", "task:") and generates automation tags.

```bash
python3 scripts/imessage_ingest.py --since today --dry-run
python3 scripts/imessage_ingest.py --since "2025-08-15" --output-file "weeks/week of 2025-08-18.md"
python3 scripts/imessage_ingest.py --since today --add-calendar --contacts "david,sean" --dry-run
```

---

### Email Search (`email_search.py`)

Fast email search using Mail's SQLite database directly.

```bash
python3 scripts/email_search.py --from "john@example.com"
python3 scripts/email_search.py --subject "project update" --limit 500
python3 scripts/email_search.py --sent --body --body-limit 500
python3 scripts/email_search.py --from "support@" --json > results.json
```

---

### Email Cleanup (`targeted_cleanup.py`)

Deletes unwanted emails (marketing, notifications) while preserving important senders.

```bash
python3 scripts/email_search.py --from "newsletter" --limit 500 --json | \
  python3 scripts/targeted_cleanup.py --dry-run

python3 scripts/email_search.py --from "marketing@" --limit 500 --json | \
  python3 scripts/targeted_cleanup.py --delete --yes
```

---

### Slack Export (`slack_dump.py`)

Read-only Slack conversation export. Requires `SLACK_TOKEN` environment variable.

```bash
python3 scripts/slack_dump.py --channels "general,sales" --since "2025-11-01"
python3 scripts/slack_dump.py --all-channels --since "last-week"
python3 scripts/slack_dump.py --dms "user@example.com"
python3 scripts/slack_dump.py --channels "general" --contains "proposal,contract"
```

---

### Whisper Transcript Extractor (`whisper_extract_crm.py`)

Extracts transcripts from MacWhisper `.whisper` files.

```bash
python3 scripts/whisper_extract_crm.py                                    # default ~/macwhisper
python3 scripts/whisper_extract_crm.py --file ~/macwhisper/recording.whisper
python3 scripts/whisper_extract_crm.py --format json --output-dir /tmp/transcripts
```

---

### Granola Meeting Transcripts (`granola_dump.py`)

Extracts meeting transcripts from Granola's local cache.

```bash
python3 scripts/granola_dump.py                                # today's meetings
python3 scripts/granola_dump.py --last-n 5
python3 scripts/granola_dump.py --search "standup" --all
python3 scripts/granola_dump.py --all --output-dir /tmp/granola
```

---

### Wispr Flow Dictations (`wispr_dump.py`)

Extracts voice dictation history from Wispr Flow's SQLite database.

```bash
python3 scripts/wispr_dump.py                         # today's dictations
python3 scripts/wispr_dump.py --since 7d
python3 scripts/wispr_dump.py --search "pipeline" --all
python3 scripts/wispr_dump.py --app slack --since 7d
python3 scripts/wispr_dump.py --format plain --since 7d    # pipe to AI
python3 scripts/wispr_dump.py --stats --all
```

---

## Reporting & Analysis Scripts

### Person Data Dump (`person_dump.py`)

Dumps ALL data for a specific contact: iMessages, emails, and Whisper transcripts.

```bash
python3 scripts/person_dump.py "Jane Doe"
python3 scripts/person_dump.py "Jane Doe" > /tmp/jane_dump.txt
python3 scripts/person_dump.py --file people/jane-doe.md
```

---

### New Contacts (`new_contacts.py`)

Finds contacts recently added to macOS Contacts and generates follow-up drafts.

```bash
python3 scripts/new_contacts.py --event "Tech Conference"
python3 scripts/new_contacts.py --days 3 --event "Networking Week"
python3 scripts/new_contacts.py --days 1
```

---

### Action Items Report (`action_items_report.py`)

Scans all CRM files for unchecked action items and generates prioritized reports.

```bash
python3 scripts/action_items_report.py
python3 scripts/action_items_report.py --priority URGENT
python3 scripts/action_items_report.py --since 2025-11-06
python3 scripts/action_items_report.py --format markdown --output tasks.md
```

---

### Status Reporter (`status_reporter.py`)

Generates status report of all leads and projects.

```bash
python3 status_reporter.py                          # status table
python3 status_reporter.py --dump-content leads     # full content dump
python3 status_reporter.py --dump-content projects
python3 status_reporter.py --dump-content people
```

---

## Orchestration

### Daily Sync (`daily_sync.sh`)

Master workflow that runs collection, processing, analysis, and persistence.

```bash
./scripts/daily_sync.sh              # default timeframe
./scripts/daily_sync.sh today        # today only
./scripts/daily_sync.sh yesterday    # yesterday
./scripts/daily_sync.sh last-week    # past week
./scripts/daily_sync.sh today --keep-raw  # keep intermediate files
```

### Automated Daily Sync (`automated_daily_sync.sh`)

Wrapper for running daily sync via macOS launchd (scheduled automation).

### Focus Timer (`focus_timer.sh`)

Pomodoro-style timer with system notifications and sounds.

```bash
./scripts/focus_timer.sh "Draft PRD" 90 15     # 90 min, check every 15
./scripts/focus_timer.sh "Code review" 25 25    # Pomodoro
./scripts/focus_timer.sh "Deep work" 120 30     # 2 hours, 30 min intervals
```

---

## Utility Scripts

### Audit Tasks (`audit_tasks.sh`)

Finds incomplete tasks across weekly plan files, color-coded by move count.

```bash
./audit_tasks.sh
```

### Filter Tasks (`filter_tasks.sh`)

Groups task context files by status (Complete, In Progress, Not Started, Blocked).

```bash
./filter_tasks.sh
```

---

## Common Flags

| Flag | Scripts | Effect |
|------|---------|--------|
| `--dry-run` | reminders, calendar, imessage_send, imessage_ingest, targeted_cleanup | Preview without executing |
| `--verbose` | reminders, calendar, imessage_send, whisper_extract_crm, slack_dump | Detailed logging |
| `--file` | reminders, calendar, imessage_send | Input markdown file |
| `--yes` | imessage_send, targeted_cleanup | Confirm destructive action |
| `--timeout` | reminders, calendar | AppleScript timeout (default: 12s) |
| `--format` | imessage_dump, slack_dump, whisper, granola, wispr, action_items | Output format |
| `--output` | Most scripts | Output file path |
| `--since` | email_search, slack_dump, daily_sync, wispr_dump, granola_dump | Date filter |
