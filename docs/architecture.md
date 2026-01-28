# Memex AI: Architecture

**Generated:** 2025-12-25
**Total Python Code:** 7,231 lines across 20+ scripts

---

## Executive Summary

### Project Purpose

Memex AI is a **file-based personal relationship management system** that automatically ingests communications from multiple sources (iMessage, Email, Slack, voice transcripts), cross-references them against existing contacts, identifies new relationships, surfaces stale connections, and automates follow-up actions through deep macOS integration.

### Core Value Proposition

1. **Unified Communication Ingestion**: Automatically collects and processes iMessages, emails, Slack messages, and voice transcripts
2. **Intelligent Contact Discovery**: Identifies new people from communications and suggests CRM additions
3. **Relationship Maintenance**: Flags stale contacts and generates follow-up reminders
4. **Automation via Tags**: Embed `@reminder()`, `@calendar()`, `@imessage()` tags in markdown to create Apple Reminders, Calendar events, and send messages
5. **AI-Assisted Workflow**: AI guides users through CRM operations via comprehensive rules and documentation

### Primary Users & Workflows

**Target User**: Solo entrepreneur/consultant managing 100+ relationships across sales leads, projects, and professional network

**Daily Workflow**:
1. Run `./scripts/daily_sync.sh` to collect all recent communications
2. Review generated reports (new people, stale contacts, touchpoints)
3. Update CRM markdown files with new information
4. Add `@reminder()` / `@calendar()` / `@imessage()` tags for automation
5. Execute automation scripts to create tasks, events, and send messages

---

## System Architecture Diagram

```
+---------------------------------------------------------------------+
|                         DATA SOURCES (macOS)                         |
+---------------------------------------------------------------------+
|                                                                       |
|  +--------------+  +--------------+  +--------------+  +---------+   |
|  |   Messages   |  |  Apple Mail  |  |     Slack    |  | Whisper |   |
|  |   chat.db    |  | Envelope.db  |  |   API Token  |  |  ~/mac  |   |
|  +------+-------+  +------+-------+  +------+-------+  +----+----+  |
|         |                  |                  |               |       |
+---------+------------------+------------------+---------------+-------+
          |                  |                  |               |
          v                  v                  v               v
+---------------------------------------------------------------------+
|                      COLLECTION LAYER                                |
|                     (Python Scripts)                                  |
+---------------------------------------------------------------------+
|                                                                       |
|  imessage_recent    email_search.py    slack_dump.py    whisper_      |
|  _threads.py        (SQLite query)     (Slack API)     extract_crm   |
|  (SQLite copy)                                         .py           |
|         |                  |                  |               |      |
|         +------------------+------------------+---------------+      |
|                            |                                         |
|                            v                                         |
|                   +------------------+                               |
|                   |  Raw Exports     |                               |
|                   |  (markdown)      |                               |
|                   |  /tmp/sync_*/    |                               |
|                   +--------+---------+                               |
+--------------------------------------------------------------------+
                             |
                             v
+---------------------------------------------------------------------+
|                      PROCESSING LAYER                                |
|                  process_daily_sync.py                                |
+---------------------------------------------------------------------+
|                                                                       |
|  +--------------------------------------------------------------+   |
|  |  1. Parse raw exports (regex-based markdown parsing)          |   |
|  |  2. Load existing CRM index (people/*.md slugs, names, etc.) |   |
|  |  3. Cross-reference contacts (email/phone matching)           |   |
|  |  4. Resolve phone -> name via macOS Contacts DB               |   |
|  |  5. Generate contact directories & reports                    |   |
|  +--------------------------------------------------------------+   |
|                            |                                         |
|                            v                                         |
|                   +------------------+                               |
|                   |   REPORTS        |                               |
|                   |  (markdown)      |                               |
|                   |  - NEW_PEOPLE    |                               |
|                   |  - TOUCHPOINTS   |                               |
|                   |  - CONTACTS      |                               |
|                   +--------+---------+                               |
+--------------------------------------------------------------------+
                             |
                             v
+---------------------------------------------------------------------+
|                        CRM DATA LAYER                                |
|                   (Markdown File System)                             |
+---------------------------------------------------------------------+
|                                                                       |
|  people/                active_leads/           projects/             |
|  +- contact-a.md       +- lead-one.md          +- project-x.md      |
|  +- contact-b.md       +- lead-two.md          +- project-y.md      |
|  +- [N contacts]       +- [N leads]            +- [N projects]      |
|                                                                       |
|  Each file has structured sections:                                   |
|  +------------------------------------------------------------+     |
|  | # Name                                                      |     |
|  | ## Contact (phone, email, location)                         |     |
|  | ## Background                                               |     |
|  | ## Status (Stage, Next Step, Last Updated)                  |     |
|  | ## Projects / Notes / Reminders                             |     |
|  |                                                             |     |
|  | @reminder(message="...", at="...", list="Work")             |     |
|  | @calendar(message="...", at="...", duration="60m")          |     |
|  | @imessage(to="+1234567890", message="...")                  |     |
|  +------------------------------------------------------------+     |
+---------------------------------------------------------------------+
          |                      |                      |
          v                      v                      v
+---------------------------------------------------------------------+
|                      AUTOMATION LAYER                                |
|                   (AppleScript via Python)                           |
+---------------------------------------------------------------------+
|                                                                       |
|  reminders_cli.py      calendar_cli.py      imessage_send.py        |
|  (parse @reminder)     (parse @calendar)    (parse @imessage)        |
|         |                     |                      |               |
|         v                     v                      v               |
|  Apple Reminders       Apple Calendar          Messages.app          |
|  (via osascript)       (via osascript)        (via osascript)        |
|                                                                       |
|  Idempotency:                                                        |
|  .cursor/sent_reminders.json    .meta/imessage_sent.log             |
+---------------------------------------------------------------------+
```

---

## High-Level Design Philosophy

**1. Files Over Databases**
- All CRM data stored as human-readable markdown files
- No SQL database required; file system IS the database
- Git-friendly: track all changes, revert mistakes, grep for anything

**2. Scripts Over UI**
- Command-line tools for all operations
- Shell script orchestration (`daily_sync.sh`)
- No GUI application; terminal-first design

**3. macOS Native Integration**
- Deeply integrated with Messages, Mail, Calendar, Reminders, Contacts
- Direct SQLite access to Apple databases (read-only)
- AppleScript automation via `osascript`

**4. AI-Assisted Workflow**
- AI acts as the "interface layer"
- User describes intent; AI suggests correct script invocation

**5. Safety First**
- **Dry-run defaults**: Preview before execution
- **Idempotency**: Track sent messages/reminders to avoid duplicates
- **Read-only DB access**: Copy databases to temp before querying
- **Explicit confirmations**: Require `--yes` for destructive actions

---

## Major Architectural Decisions

### Decision 1: Markdown as Data Format
**Rationale**: Human-readable, git-friendly, AI-parseable, no vendor lock-in

**Trade-offs**:
- Easy to read/edit manually
- Version control built-in
- No schema migrations
- No relational queries
- Regex-based parsing (fragile)
- No referential integrity

### Decision 2: Direct Database Access (SQLite)
**Rationale**: Fast queries, comprehensive data access, no API limitations

**Trade-offs**:
- Much faster than JXA iteration (email_search.py vs JXA approach)
- Full data access, no rate limits
- Requires Full Disk Access permissions
- Database schema changes break scripts
- macOS-only

### Decision 3: Tag-Based Automation
**Rationale**: Embed automation directly in planning documents

**Trade-offs**:
- Automation co-located with context
- Works with any text editor
- Easy to review before execution
- Manual tag syntax
- Requires separate script execution

### Decision 4: Idempotency via Log Files
**Rationale**: Safe to re-run scripts without creating duplicates

**Implementation**:
- `.cursor/sent_reminders.json`: Maps file+line+tag to sent status
- `.meta/imessage_sent.log`: Tracks sent message IDs
- Scripts check logs before creating items

---

## Component Deep Dives

### Component 1: Data Collection Layer

Extracts communications from multiple sources into consistent markdown format.

**Key Scripts**:
- `imessage_recent_threads.py` (670 lines) - Export N most recent iMessage threads
- `email_search.py` (358 lines) - Fast SQLite email search
- `slack_dump.py` (808 lines) - Export Slack conversations via API
- `whisper_extract_crm.py` (264 lines) - Extract voice transcripts

All collection scripts output to `/tmp/crm_daily_sync_*/` with consistent markdown format.

### Component 2: Processing Layer

Parse raw exports, cross-reference against existing CRM data, generate insights.

**Key Script**: `process_daily_sync.py` (1,241 lines)

**Data Transformations**:
1. **Contact Normalization**: Phone/email normalization
2. **Contact Resolution**: Phone number to real name via macOS Contacts
3. **Deduplication**: Check against existing `/people/*.md`
4. **Filtering**: Exclude newsletters, marketing, system messages

**Reports Generated**:
- `NEW_PEOPLE_CANDIDATES.md` - People not yet in CRM
- `RECENT_PEOPLE_TOUCHPOINTS.md` - Recent activity for follow-ups
- `IMESSAGE_CONTACTS.md`, `SLACK_CONTACTS.md`, `EMAIL_*_CONTACTS.md` - Contact directories
- `OUTREACH_DRAFTS.md` - Suggested follow-up messages

### Component 3: CRM Data Layer (Markdown Files)

See `docs/scripts.md` for file templates and standards.

### Component 4: Automation Layer

Parse automation tags from markdown and execute actions via AppleScript.

**Tag Types**: `@reminder()`, `@calendar()`, `@imessage()`

All automation scripts support idempotency via source markers and log files.

### Component 5: Orchestration

`daily_sync.sh` orchestrates the entire workflow:
1. Setup output directories
2. Collection (Slack, iMessage, Email, Whisper)
3. Processing into contact directories
4. Analysis (active contacts, status report)
5. Persistence to repo archive
6. Cleanup

---

## Key Design Patterns

### Pattern 1: "DB Copy Before Query"
All SQLite-accessing scripts copy the database to a temp location before querying, preventing locks and ensuring read-only access.

### Pattern 2: "Tags as Structured Data in Unstructured Text"
`@reminder()`, `@calendar()`, `@imessage()` tags embed automation in human-readable planning documents.

### Pattern 3: "Idempotency via Source Markers"
Calendar events embed source location in description. Reminders tracked in JSON log. Messages tracked in simple log file.

### Pattern 4: "Regex-Based Markdown Parsing"
Simple, fast, no dependencies, but fragile if format changes.

---

## Constraints & Limitations

- **macOS-only**: Deep integration with macOS APIs and databases
- **Permissions-dependent**: Requires Full Disk Access + Accessibility
- **Schema fragility**: Apple updates can break scripts
- **No real-time updates**: Manual sync workflow by design
- **Single-user system**: Not designed for team use
- **No external dependencies**: Python stdlib only (plus optional biplist)

---

## Configuration

### Environment Variables
```bash
# .env
SLACK_TOKEN=xoxp-...

# Focus timer (optional)
FOCUS_SOUND_FILE=/System/Library/Sounds/Submarine.aiff
FOCUS_FORCE_SOUND=1
FOCUS_MIN_VOLUME=50
```

### Database Locations
- **Contacts**: `~/Library/Application Support/AddressBook/AddressBook-v22.abcddb`
- **iMessage**: `~/Library/Messages/chat.db`
- **Apple Mail**: `~/Library/Mail/V*/MailData/Envelope Index` (auto-discovered)
