# Memex AI

> *"Consider a future device... in which an individual stores all his books, records, and communications, and which is mechanized so that it may be consulted with exceeding speed and flexibility. It is an enlarged intimate supplement to his memory."*
>
> — Vannevar Bush, "As We May Think" (1945)

---

In 1945, the war had just ended. Vannevar Bush, the engineer who coordinated 6,000 scientists in the American war effort, turned his attention to a different problem: how do we manage the explosion of human knowledge?

His answer was the **Memex** — a hypothetical device where a person could store everything they read, write, and think. Not just storage, but *trails* through information. Personal paths of association that would let you retrace your steps, make new connections, and build on your own thinking.

Bush imagined it as a desk with screens and levers. He was describing the personal computer 30 years early.

## The problem hasn't changed

Today we have more tools than Bush could have imagined. And yet the fundamental problem remains: **our knowledge is scattered across dozens of apps, and our relationships slip through the cracks.**

We meet people at conferences and lose their context within days. We have threads across iMessage, Slack, and email with no unified view. We make commitments in conversations that we forget to follow up on. The tools we have are built for teams, not individuals. They require constant manual data entry. They don't connect to where our actual communication happens.

## What if we built the Memex for relationships?

This project is an experiment in that direction.

**Memex AI** is a personal CRM that lives in markdown files and talks to you through AI. There's no UI to learn, no forms to fill out. You just... talk to it. Tell it about your day, paste in meeting notes, forward email threads. It organizes everything into structured files, tracks your commitments, and connects to macOS to create reminders, calendar events, and even send messages.

Everything stays local. Your data never leaves your machine. It's just text files in a git repo — the same way we've been managing code for decades.

## How it works

```
You:  I just had coffee with Lisa Chen from Dataflow. They're looking for
      help building an eval framework for their LLM product. She mentioned
      following up next week with a rough proposal.

AI:   Created people/lisa-chen.md and active_leads/dataflow-eval-framework.md
      with the context from your meeting. Want me to set a reminder to follow up?

You:  Yeah, Tuesday morning.

AI:   Added a reminder tag. Run the reminders script when you're ready to sync.
```

After a few weeks, your repo looks like this:

```
people/                          # One file per contact
  lisa-chen.md
  marcus-wright.md

active_leads/                    # Pipeline opportunities
  dataflow-eval-framework.md
  acme-consulting.md

projects/                        # Active work
  client-mvp-build.md
  projects/done/                 # Completed work

weeks/                           # Planning files with automation tags
  week of 2025-01-27.md
```

Each file is plain markdown. Structured enough for scripts to parse, human enough to read directly. Your AI assistant manages them through conversation.

## The daily sync

The real power comes from connecting this to your actual communication channels. The daily sync script collects:

- **iMessage** conversations
- **Email** threads (Apple Mail)
- **Slack** messages
- **Voice transcripts** (Granola, Wispr Flow, MacWhisper)

It exports everything into contact-organized reports. Your AI reviews them, identifies new contacts, flags stale relationships, and updates your CRM files. Run it every morning:

```bash
./scripts/daily_sync.sh yesterday
```

This is the "trails" that Bush imagined — but automatic, across all your communication.

## Tag-based automation

Embed tags in any markdown file:

```markdown
@reminder(message="Follow up with Lisa", at="Tuesday 09:00", list="Work")
@calendar(message="Focus: Write proposal", at="tomorrow 14:00", duration="90m")
@imessage(to="+14155551234", message="Hey, just sent over the proposal!")
```

Then run the corresponding script to execute them. All scripts default to dry-run mode. Everything is idempotent — running twice won't create duplicates.

## Why markdown? Why local?

Three reasons:

1. **Longevity.** Markdown files will be readable in 50 years. Your CRM SaaS might not exist in 5.

2. **AI-native.** Language models work with text. Markdown is the perfect format for AI to read, write, and reason about.

3. **Ownership.** Your relationships are yours. They shouldn't live on someone else's server, subject to their pricing changes and privacy policies.

Git gives you version history, backup, and sync across machines — all without any cloud service.

## Getting started

1. Clone this repo
2. Open in [Cursor](https://cursor.sh) or use [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
3. Start talking: *"I just met Sarah from TechCorp at a conference..."*

For macOS permissions, Slack setup, and troubleshooting: **[docs/setup.md](docs/setup.md)**

Full script reference: **[docs/scripts.md](docs/scripts.md)**

## Requirements

- **macOS** (required — deeply integrated with Apple APIs)
- **Python 3** (standard library only, no pip installs)
- **Cursor** or **Claude Code** (or any AI assistant that reads instruction files)

## Documentation

- [Setup Guide](docs/setup.md) — Permissions, environment, troubleshooting
- [Script Reference](docs/scripts.md) — All 20+ scripts with usage examples
- [Daily Sync Workflow](docs/daily-sync.md) — How the sync pipeline works
- [Architecture](docs/architecture.md) — System design decisions

---

*Bush's Memex was never built. But he was right about what we needed. Eighty years later, we finally have the technology to build it — language models that can understand natural language, APIs into our communication tools, and markdown files that will outlast any app.*

*This is one attempt at that vision.*

---

MIT License
