# Daily Sync Workflow

## Overview

The daily sync process collects communications from all channels (Slack, iMessage, Email), processes them into comprehensive contact directories, and prepares them for CRM enrichment.

## Workflow Steps

### 1. **Data Collection** (Automated)
Collects raw communications from:
- **Slack:** All channels you're in
- **iMessage:** Last 50 threads (50 messages each)
- **Email:** Last 500 received + 500 sent

### 2. **Contact Directory Generation** (Automated)
Processes raw exports into structured contact directories:
- `IMESSAGE_CONTACTS.md` - All iMessage contacts with recent activity summaries
- `SLACK_CONTACTS.md` - All Slack conversations sorted by message count
- `EMAIL_RECEIVED_CONTACTS.md` - All received email contacts sorted by frequency
- `EMAIL_SENT_CONTACTS.md` - All sent email contacts sorted by frequency

### 3. **CRM Enrichment** (AI-Assisted)
Review contact directories and identify:
- New contacts to add to CRM
- Updates to existing CRM files
- Action items and follow-ups
- Relationship insights

### 4. **Cleanup** (Automated)
Deletes intermediate raw export files, keeping only the contact directories.

---

## Usage

### Basic Usage (Default: Today)
```bash
./scripts/daily_sync.sh
```

### Specify Timeframe
```bash
./scripts/daily_sync.sh today        # Today's activity
./scripts/daily_sync.sh yesterday    # Yesterday's activity
./scripts/daily_sync.sh last-week    # Last week's activity
```

### Keep Raw Files (for debugging)
```bash
./scripts/daily_sync.sh today --keep-raw
```

---

## Output Structure

```
/tmp/crm_daily_sync_YYYYMMDD_HHMMSS/
+-- IMESSAGE_CONTACTS.md          # Review this
+-- SLACK_CONTACTS.md             # Review this
+-- EMAIL_RECEIVED_CONTACTS.md    # Review this
+-- EMAIL_SENT_CONTACTS.md        # Review this
+-- [raw files deleted unless --keep-raw]
```

---

## Contact Directory Format

### iMessage Contacts
```markdown
## Active Contacts (Recent Activity)

### 1. **Contact Name**
- **Phone/ID:** +1234567890
- **Last Message:** 2025-11-17 14:30
- **Total Messages:** 150

**Recent Activity (3 messages):**
- **[2025-11-17] Them:** Message preview text...
- **[2025-11-16] You:** Your response preview...
- **[2025-11-15] Them:** Earlier message...
```

### Slack Contacts
```markdown
## #channel-name
- **Messages:** 45

**Recent Messages:**
- **[2025-11-17 10:30] Alice:** Discussed project status...
- **[2025-11-17 11:15] Bob:** Shared design updates...
```

### Email Contacts
```markdown
## Contact Name
- **Email:** contact@example.com
- **Message Count:** 12
- **Last Contact:** 2025-11-17

**Recent Emails:**
- **[2025-11-17]** Meeting follow-up
- **[2025-11-15]** Project proposal
```

---

## CRM Enrichment Workflow

### 1. Read Contact Directories
```bash
less /tmp/crm_daily_sync_*/IMESSAGE_CONTACTS.md
less /tmp/crm_daily_sync_*/SLACK_CONTACTS.md
less /tmp/crm_daily_sync_*/EMAIL_RECEIVED_CONTACTS.md
```

### 2. Identify Updates
For each contact with significant activity:
- Is this a new person? -> Create `/people/` file
- Is this a new lead? -> Create `/active_leads/` file
- Is this an existing contact? -> Update their file
- Are there action items? -> Add to relevant project/lead file

### 3. Apply Updates (AI-Assisted)
Use AI assistant to:
- Create new CRM files
- Update existing files with interaction notes
- Add action items to appropriate files
- Update status fields (Last Updated, Stage, etc.)

**CRITICAL: Comprehensive Updates Required**
The AI should prioritize thoroughness over token efficiency. Every contact with significant activity MUST get a complete update, including:
- Full timeline entries with dates and context
- All action items identified from conversations
- Status changes on related leads/projects
- Relationship notes extracted from message content

### 4. Verify Changes
```bash
git status
git diff
```

---

## Best Practices

### Frequency
- **Daily:** Run every morning to catch overnight activity
- **Weekly:** Run with `last-week` on Monday mornings for comprehensive review

### Review Order
1. **Slack first:** Business discussions and project updates
2. **iMessage second:** Quick personal/business check-ins
3. **Email last:** Formal communications and longer threads

### Prioritization
Focus on contacts with:
- **High message frequency** in short time period
- **Business context** (project names, money, deadlines)
- **Action items** (explicit next steps, requests)
- **New connections** (first-time contacts)

### Lead/Project Status Tracking
After each daily sync:
1. Run `python3 status_reporter.py` to see all lead/project statuses
2. Review any items marked stale (>7 days)
3. Cross-reference sync output with lead/project files
4. Update `Stage` and `Next Step` fields based on new interactions
5. Archive leads that have been won/lost
6. Complete projects that are finished

### CRM File Placement
- **People files** (`/people/`) - For relationship documentation only
- **Active leads** (`/active_leads/`) - For potential opportunities with action items
- **Projects** (`/projects/`) - For confirmed work with action items
- **Action items** - ONLY in leads/projects, NEVER in people files

---

## Example Complete Workflow

```bash
# 1. Run daily sync
cd ~/git/memex-ai
./scripts/daily_sync.sh today

# 2. Review output location
# Output: /tmp/crm_daily_sync_20251117_083000

# 3. Open in AI assistant (Cursor or Claude Code)
# Attach the contact directory files for review

# 4. AI assistant identifies updates:
#    - New contact: Jane Smith (sent eval leads)
#    - Update: Project Alpha (110 emails sent)
#    - Action: Follow up with John Doe

# 5. AI applies updates to CRM files

# 6. Review changes
git status
git diff

# 7. Commit if satisfied
git add .
git commit -m "Daily sync: Nov 17 - Added new contacts, updated projects"
```

---

## Troubleshooting

### No Slack Data
- Check `SLACK_TOKEN` in `.env` file
- Verify OAuth token has required scopes
- Run: `export SLACK_TOKEN="xoxb-your-token"`

### No iMessage Data
- Grant **Full Disk Access** to Terminal/iTerm
- System Settings > Privacy & Security > Full Disk Access
- Restart terminal after granting access

### No Email Data
- Grant **Full Disk Access** to Terminal/iTerm
- Verify Mail app is running
- Check that Mail has downloaded recent messages

### Processing Fails
- Check Python 3 is installed: `python3 --version`
- Verify script exists: `ls scripts/process_daily_sync.py`
- Run processing manually: `python3 scripts/process_daily_sync.py /tmp/crm_daily_sync_*/`
- Keep raw files for debugging: `./scripts/daily_sync.sh --keep-raw`

---

## AI Enrichment Philosophy

### Comprehensive > Efficient
When processing daily sync output, the AI should:
- **Update ALL contacts with new activity**, not just the most active ones
- **Include full context** from message threads, not summaries
- **Extract every actionable item**, even minor ones
- **Cross-link people, leads, and projects** when relationships are identified

### Lead/Project Status Discipline
- **Every lead must have a Stage:** Qualification, Proposal Sent, Negotiation, Awaiting Response, Archived
- **Every project must have a Status:** Planning, In Progress, On Hold, Awaiting Feedback, Blocked, Done
- **Every file must have Last Updated:** If syncing, update it to today

### Never Skip, Always Track
Even if a contact only has 1-2 messages:
- Still create a timeline entry if it's business-relevant
- Still note the interaction in relationship context
- Still flag any implied action items

The CRM is only valuable if it's complete.

---

## Related Scripts

- `scripts/person_dump.py` - Comprehensive single-person enrichment
- `scripts/action_items_report.py` - Extract all pending action items
- `status_reporter.py` - Get overview of all leads/projects
- `scripts/reminders_cli.py` - Create Apple Reminders from markdown
