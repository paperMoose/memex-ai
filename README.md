# Memex AI

> A local-first, AI-powered personal CRM and productivity system that lives in markdown files.

## What is this?

Memex AI is a conversational CRM where your AI assistant manages everything. Instead of clicking through a UI, you just talk:

- **"I just met Sarah from TechCorp"** -- creates contact and lead files
- **"What's the status of my projects?"** -- runs status reports
- **"Set a reminder to follow up Thursday"** -- creates Apple Reminders
- **"Run daily sync"** -- collects all your Slack, iMessage, and email activity

All data stays local. All files are markdown. Zero external dependencies.

### Key Features

- **Conversational CRM**: Talk to your AI assistant, it manages everything
- **Deep macOS integration**: Apple Reminders, Calendar, iMessage, Mail
- **Daily sync pipeline**: Slack, iMessage, Email, voice transcripts
- **Tag-based automation**: `@reminder()`, `@calendar()`, `@imessage()` tags in markdown
- **Idempotent by design**: Safe to re-run any script without duplicates

## Quick Start

1. Clone this repo
2. Open in [Cursor](https://cursor.sh) (recommended) or use with [Claude Code](https://claude.ai/claude-code) via `CLAUDE.md`
3. Start talking: *"I just met Sarah from TechCorp..."*

## System Requirements

- **macOS** (required for Apple integrations)
- **Python 3** (standard library only -- no pip installs)
- **Cursor AI editor** (recommended) or **Claude Code CLI**

## Permissions Setup

Grant your terminal app these permissions in **System Settings > Privacy & Security**:

| Permission | Required For |
|-----------|-------------|
| **Full Disk Access** | iMessage, Email database access |
| **Accessibility** | Sending iMessages via AppleScript |
| **Automation** | Reminders, Calendar, Mail, Messages (auto-prompted) |

## Project Structure

```
memex-ai/
+-- people/              # Contact profiles (one markdown file per person)
+-- active_leads/        # Sales pipeline / opportunities
+-- projects/            # Active work
+-- outreach/            # Cold outreach tracking
+-- weeks/               # Weekly planning files
+-- archive/             # Historical data
+-- scripts/             # 20+ automation scripts
|   +-- daily_sync.sh           # Master sync workflow
|   +-- reminders_cli.py        # Apple Reminders automation
|   +-- calendar_cli.py         # Apple Calendar automation
|   +-- imessage_send.py        # iMessage sending
|   +-- imessage_dump.py        # iMessage export
|   +-- email_search.py         # Fast email search
|   +-- slack_dump.py           # Slack export
|   +-- person_dump.py          # Full person data dump
|   +-- action_items_report.py  # Task extraction
|   +-- ...and more
+-- .cursor/rules/       # AI assistant rules
+-- docs/                # Detailed documentation
+-- status_reporter.py   # CRM status overview
+-- CLAUDE.md            # Claude Code instructions
```

## Documentation

- **[Architecture](docs/architecture.md)** -- System design, data flow, key decisions
- **[Script Reference](docs/scripts.md)** -- All 20+ scripts with usage examples
- **[Daily Sync Workflow](docs/daily-sync.md)** -- How the sync pipeline works
- **[Action Items System](docs/action-items.md)** -- Task tracking standards
- **[Setup Guide](docs/setup.md)** -- Permissions, environment, troubleshooting

## How It Works

### Data Flow

```
macOS Sources (iMessage, Mail, Slack, Whisper)
    |
    v
Collection Scripts (Python, read-only)
    |
    v
Processing (cross-reference, dedup, reports)
    |
    v
CRM Files (markdown in git)
    |
    v
Automation Tags (@reminder, @calendar, @imessage)
    |
    v
Apple Apps (Reminders, Calendar, Messages)
```

### Tag-Based Automation

Embed automation directly in your markdown files:

```markdown
@reminder(message="Follow up with client", at="tomorrow 10:00", list="Work")
@calendar(message="Focus: Write proposal", at="2025-01-20 14:00", duration="90m")
@imessage(to="+14155551234", message="Thanks for the intro!")
```

Then run the corresponding script to execute. All scripts support `--dry-run` for preview.

## License

MIT
