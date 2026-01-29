# Memex AI

A local-first, AI-powered personal CRM that lives in markdown files. You talk to an AI assistant, it manages your contacts, leads, projects, and follow-ups.

## Why this exists

Most CRMs are built for teams. If you're a solo founder, consultant, or freelancer, you don't need Salesforce — you need a system that:

- **Captures context from where you already communicate** (iMessage, Slack, Email, voice calls)
- **Stays out of your way** — no forms, no UI, no browser tabs
- **Keeps everything local** — your relationship data never leaves your machine
- **Works with AI natively** — the AI *is* the interface

Memex AI stores everything as markdown files in a git repo. You talk to your AI assistant in [Cursor](https://cursor.sh) or [Claude Code](https://docs.anthropic.com/en/docs/claude-code), and it manages the files for you.

## What a session looks like

```
You:  I just had coffee with Lisa Chen from Dataflow. They're looking for
      help building an eval framework for their LLM product. She said to
      follow up next week with a rough proposal.

AI:   I'll create a contact file and a lead. [creates people/lisa-chen.md
      and active_leads/dataflow-eval-framework.md with status, notes, and
      next steps]

      Want me to set a reminder to follow up?

You:  Yeah, Tuesday morning.

AI:   Added @reminder tag. Run `python3 scripts/reminders_cli.py --file
      weeks/week\ of\ 2025-01-27.md` to create it in Apple Reminders.
```

After a few weeks of use, your repo looks like this:

```
people/
  lisa-chen.md            # Background, contact info, interaction history
  marcus-wright.md
  sarah-kim.md
  ...

active_leads/
  dataflow-eval-framework.md    # Stage: Proposal Sent, next steps, notes
  acme-ai-consulting.md

projects/
  client-mvp-build.md          # Status: In Progress, action items, timeline
  projects/done/
    community-workshop.md       # Completed projects move here

weeks/
  week of 2025-01-27.md        # Daily habits, tasks, @reminder/@calendar tags
```

Each file is plain markdown with structured status blocks that scripts can parse:

```markdown
# Dataflow Eval Framework

## Status
- **Stage:** Proposal Sent
- **Next Step:** Follow up if no response by Friday
- **Last Updated:** 2025-01-28

## Background
Lisa Chen (CTO) is building an LLM product and needs an evaluation framework...

## Action Items
- [ ] **HIGH:** Send proposal draft by Wednesday *(added 2025-01-28)*
- [ ] **MEDIUM:** Research their existing test suite *(added 2025-01-28)*

## Timeline
- **2025-01-27:** Coffee meeting. Lisa described their current eval gaps...
```

## Quick Start

### 1. Clone and open

```bash
git clone https://github.com/paperMoose/memex-ai.git
cd memex-ai
```

Open in Cursor, or use Claude Code from the terminal (it reads `CLAUDE.md` automatically).

### 2. Create your data directories

```bash
mkdir -p people active_leads projects outreach weeks archive
```

### 3. Grant macOS permissions

Your terminal app needs these in **System Settings > Privacy & Security**:

| Permission | Why |
|-----------|-----|
| **Full Disk Access** | Read iMessage and Mail databases |
| **Accessibility** | Send iMessages via AppleScript |

Automation permissions (Reminders, Calendar, Mail, Messages) are prompted automatically on first use.

### 4. Configure for your accounts

Edit `scripts/daily_sync.sh` — replace the placeholder email addresses with yours:

```bash
# Line ~121: your personal email
python3 "$SCRIPT_DIR/email_search.py" --from "you@gmail.com" ...

# Line ~130: your work email
python3 "$SCRIPT_DIR/email_search.py" --from "you@company.com" ...
```

For Slack integration, create a `.env` file:

```bash
echo "SLACK_TOKEN=xoxp-your-token" > .env
```

(See [docs/setup.md](docs/setup.md) for Slack app setup instructions.)

### 5. Start using it

Talk to your AI assistant:

- *"I just met John from Acme Corp at a conference"*
- *"Run a daily sync for yesterday"*
- *"What's stale? Anything I should follow up on?"*
- *"Set a reminder to email Lisa on Tuesday"*

## Daily Sync

The daily sync collects all your communications and surfaces what needs attention:

```bash
./scripts/daily_sync.sh yesterday
```

This exports your Slack messages, iMessage threads, and emails into `/tmp/crm_daily_sync_*/`, then processes them into contact directories. Your AI assistant reviews the output and updates your CRM files.

Run it every morning, or automate it with launchd (see `scripts/automated_daily_sync.sh`).

## Tag-Based Automation

Embed automation tags in any markdown file:

```markdown
## Automations

### Reminders
@reminder(message="Follow up with Lisa", at="2025-01-30 09:00", list="Work", id="lisa-followup")

### Calendar
@calendar(message="Focus: Write proposal", at="2025-01-29 14:00", duration="90m")

### iMessages
@imessage(to="+14155551234", message="Hey, just sent over the proposal!")
```

Then run the corresponding script:

```bash
python3 scripts/reminders_cli.py --file weeks/week\ of\ 2025-01-27.md --verbose
python3 scripts/calendar_cli.py --file weeks/week\ of\ 2025-01-27.md --verbose
python3 scripts/imessage_send.py --file weeks/week\ of\ 2025-01-27.md --yes
```

All scripts default to `--dry-run` (preview mode). Add `--yes` for destructive actions. Tags are idempotent — re-running won't create duplicates.

## Scripts

20+ automation scripts, all Python standard library (no pip installs). Here are the ones you'll use most:

| Script | What it does |
|--------|-------------|
| `daily_sync.sh` | Collect Slack, iMessage, Email into contact reports |
| `reminders_cli.py` | Create Apple Reminders from `@reminder()` tags |
| `calendar_cli.py` | Create Calendar events from `@calendar()` tags |
| `imessage_send.py` | Send iMessages from `@imessage()` tags |
| `imessage_dump.py` | Export iMessage conversations for a contact |
| `email_search.py` | Fast email search (SQLite, not JXA) |
| `person_dump.py` | Dump all data (messages, emails, transcripts) for one person |
| `action_items_report.py` | Extract action items across all CRM files |
| `status_reporter.py` | Status overview of all leads and projects |
| `new_contacts.py` | Find recently-added macOS contacts, draft follow-ups |

Full reference with all flags: **[docs/scripts.md](docs/scripts.md)**

## How it works

```
macOS Sources                     CRM Files                    Apple Apps
(iMessage, Mail, Slack,    →     (markdown in git)       →    (Reminders, Calendar,
 Whisper, Granola, Wispr)        people/, leads/, projects/    Messages)

     Collection scripts               AI assistant              Automation scripts
     (read-only, safe)            (creates & updates files)    (@reminder, @calendar,
                                                                @imessage tags)
```

**Collection** scripts read macOS databases (copying to temp first — never modifying originals) and export to markdown.

**Processing** cross-references exports against existing CRM files, identifies new contacts, flags stale relationships.

**Automation** scripts parse tags from markdown and execute via AppleScript. Idempotency is tracked in `.cursor/sent_reminders.json` and `.meta/imessage_sent.log`.

## Documentation

- **[Setup Guide](docs/setup.md)** — Permissions, environment, troubleshooting
- **[Script Reference](docs/scripts.md)** — All scripts with usage examples
- **[Daily Sync Workflow](docs/daily-sync.md)** — How the sync pipeline works
- **[Action Items System](docs/action-items.md)** — Task tracking format and priorities
- **[Architecture](docs/architecture.md)** — System design and key decisions

## AI Agent Support

- **Cursor** — Uses `.cursor/rules/*.mdc` files (loaded automatically)
- **Claude Code** — Uses `CLAUDE.md` (imports the cursor rules via `@` references)
- **Other agents** (Codex, etc.) — Uses `AGENT.md` (self-contained, no imports)

## Requirements

- **macOS** (required — deeply integrated with Apple APIs)
- **Python 3** (standard library only)
- **Cursor** or **Claude Code** (or any AI coding assistant that reads instruction files)

## License

MIT
