# Memex AI — Agent Instructions

A local-first, AI-powered personal CRM and productivity system that lives in markdown files.

For the vision behind this project, see [README.md](README.md).

For setup help (macOS permissions, Slack tokens, troubleshooting): [docs/setup.md](docs/setup.md)

For the full script reference, see [docs/scripts.md](docs/scripts.md).

---

## Project Overview

This project is a conversational CRM. The user talks naturally and the AI manages markdown files: creating contacts, updating leads, scheduling reminders, and running automation scripts.

### Directory Structure

- `/people/` — One markdown file per contact (background, interactions, relationships)
- `/active_leads/` — Pipeline opportunities with status tracking
- `/projects/` — Active confirmed work
- `/outreach/` — Cold outreach tracking
- `/weeks/` — Weekly planning files
- `/scripts/` — 20+ Python/bash automation scripts (macOS only)
- `target-profiles.md` — Ideal customer profile definitions

---

## Core Behavior

### 1. Proactive File Management

When the user shares information (meeting notes, call summaries, casual remarks):

1. **Search first** — Always check if a file exists before creating one
2. **Update if found** — Add new information to existing files
3. **Offer to create if not found** — Ask before creating new files
4. **Infer status changes** — "Proposal sent" → update the lead's Stage field
5. **Always update dates** — Set `Last Updated` to today (use `date +%F`)

### 2. File Standards

#### Lead Files (`/active_leads/*.md`)
```markdown
## Status
- **Stage:** Qualification | Proposal Sent | Negotiation | Needs Follow-up
- **Next Step:** [Specific action]
- **Last Updated:** YYYY-MM-DD
```

#### Project Files (`/projects/*.md`)
```markdown
## Status
- **Current Status:** Planning | In Progress | On Hold | Blocked | Done
- **Next Milestone:** [Description]
- **Due Date:** YYYY-MM-DD
- **Last Updated:** YYYY-MM-DD
```

#### People Files (`/people/*.md`)
Relationship documentation only. **Never place action items in people files.**

### 3. Action Items

Action items belong ONLY in `/active_leads/` and `/projects/` files.

**Required format:**
```markdown
- [ ] **PRIORITY:** Task description *(added YYYY-MM-DD)*
```

Priority levels: `**URGENT:**` (24h), `**HIGH:**` (within week), `**MEDIUM:**` (default), `**LOW:**` (when time permits)

### 4. Archiving & Completion

- **Archive leads:** `mv active_leads/file.md active_leads/archive/` — update Stage to "Archived"
- **Complete projects:** `mv projects/file.md projects/done/` — update Status to "Done" with completion date

---

## Automation Tags

Embed these in markdown files, then run the corresponding script to execute.

### Reminders
```markdown
@reminder(message="Follow up with client", at="2025-08-16 09:30", list="Work", priority=1, id="unique-id")
```
Run: `python3 scripts/reminders_cli.py --file "path/to/file.md" --verbose`

**CRITICAL: Reminders are opt-in only.** Never create `@reminder()` tags unless the user explicitly asks.

### Calendar Events
```markdown
@calendar(message="Focus: Write proposal", at="2025-08-16 10:00", duration="90m", calendar="Work")
```
Run: `python3 scripts/calendar_cli.py --file "path/to/file.md" --verbose`

### iMessages
```markdown
@imessage(to="+14155551234", message="Thanks for the intro!")
```
Run: `python3 scripts/imessage_send.py --file "path/to/file.md" --yes`

**Time formats** (shared across all tags): `YYYY-MM-DD HH:MM`, `today HH:MM`, `tomorrow HH:MM`, `+30m`, `+2h`, `+1d`

---

## Key Scripts

### Daily Sync
```bash
./scripts/daily_sync.sh yesterday    # Collect Slack, iMessage, Email from yesterday
./scripts/daily_sync.sh today        # Today's activity
./scripts/daily_sync.sh last-week    # Past week
```

### Status & Reporting
```bash
python3 status_reporter.py                              # Status table of all leads/projects
python3 status_reporter.py --dump-content leads         # Full content dump for analysis
python3 scripts/action_items_report.py --priority URGENT  # Urgent action items
```

### Communication Export
```bash
python3 scripts/imessage_dump.py --contacts "john smith" --since 2024-01-01
python3 scripts/email_search.py --from "john@example.com" --limit 100
python3 scripts/slack_dump.py --channels "general" --since last-week
python3 scripts/person_dump.py "Jane Doe"               # All data for one person
```

### Utilities
```bash
python3 scripts/reminders_cli.py --report-day today     # Check today's reminder load
./scripts/focus_timer.sh "Deep work" 90 15              # Focus timer with check-ins
./scripts/focus_timer.sh "Deep work" 90 15              # Focus timer with check-ins
```

All scripts support `--dry-run` for preview. Destructive actions require `--yes`.

---

## Daily Enrichment Workflow

When the user asks for a daily sync or CRM enrichment:

1. Run `./scripts/daily_sync.sh yesterday` to collect communications
2. Review exported contact directories in `/tmp/crm_daily_sync_*/`
3. Identify new contacts, status changes, and action items
4. Create/update CRM files accordingly
5. Update `Last Updated` dates on all modified files
6. Summarize what was changed

See [docs/daily-sync.md](docs/daily-sync.md) for the full workflow.

---

## Stale Item Management

When reviewing CRM status (via `python3 status_reporter.py`):
- Items not updated in 7+ days are flagged as stale
- Proactively ask the user if stale items need updating, archiving, or completing
- Always update the `Last Updated` field when touching a file

---

## Safety Rules

- **Dry-run by default** for reminders, calendar, iMessage send, and email cleanup
- **Read-only database access** — scripts copy macOS databases to temp before querying
- **Idempotent** — `.cursor/sent_reminders.json` and `.meta/imessage_sent.log` prevent duplicates
- **Never modify Apple databases directly**
