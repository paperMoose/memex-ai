#!/bin/bash
#
# automated_daily_sync.sh
#
# Runs daily CRM sync automatically using headless Claude Code.
# Designed to be run via cron or launchd.
#
# Usage:
#   ./scripts/automated_daily_sync.sh              # Default: yesterday's activity
#   ./scripts/automated_daily_sync.sh today        # Today's activity
#   ./scripts/automated_daily_sync.sh last-week    # Last week's activity
#
# Cron example (run daily at 9 AM):
#   0 9 * * * /path/to/memex-ai/scripts/automated_daily_sync.sh
#
# Requirements:
#   - Claude Code CLI installed and authenticated
#   - ANTHROPIC_API_KEY set (or authenticated via `claude auth`)
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$REPO_ROOT/logs"
TIMEFRAME="${1:-yesterday}"
DATE_LABEL=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/daily_sync_${DATE_LABEL}.log"
LOCK_FILE="$LOG_DIR/.daily_sync_${DATE_LABEL}.done"
FORCE="${2:-}"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Check if already ran today (skip if --force passed)
if [ -f "$LOCK_FILE" ] && [ "$FORCE" != "--force" ]; then
    echo "Daily sync already completed today. Use --force to run again."
    echo "Lock file: $LOCK_FILE"
    exit 0
fi

# Start logging
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Automated Daily Sync - $DATE_LABEL"
echo "Timeframe: $TIMEFRAME"
echo "Started: $(date)"
echo "=========================================="
echo ""

# Change to repo directory
cd "$REPO_ROOT"

# Step 1: Run the data collection script
echo "📥 Step 1: Collecting communications data..."
if ./scripts/daily_sync.sh "$TIMEFRAME" 2>&1; then
    echo "✅ Data collection complete"
else
    echo "❌ Data collection failed"
    exit 1
fi

echo ""
echo "🤖 Step 2: Running Claude Code to enrich CRM..."
echo ""

# Find the most recent daily sync output directory
LATEST_SYNC_DIR=$(ls -td /tmp/crm_daily_sync_* 2>/dev/null | head -1)

if [ -z "$LATEST_SYNC_DIR" ]; then
    echo "❌ No daily sync output found in /tmp"
    exit 1
fi

echo "Using sync data from: $LATEST_SYNC_DIR"
echo ""

# Step 2: Run Claude Code in headless mode to enrich CRM
# Using --allowedTools to auto-approve necessary tools
claude -p "
I just ran daily_sync.sh and the output is in $LATEST_SYNC_DIR

Please enrich my CRM with today's communications:

## Step 1: Read the sync data
- IMESSAGE_CONTACTS.md, SLACK_CONTACTS.md, EMAIL_RECEIVED_CONTACTS.md, EMAIL_SENT_CONTACTS.md
- NEW_PEOPLE_CANDIDATES.md, RECENT_PEOPLE_TOUCHPOINTS.md, ACTIVE_CONTACT_EMAILS.md
- STATUS_REPORT.txt (check for stale items)

## Step 2: For EACH meaningful conversation, update the CRM
Look up existing files in /people/, /active_leads/, /projects/ and ADD a '### Recent Activity' section with:

**For planned meetups/calls:**
- Date and context of the plan
- Specific days/times proposed (e.g., 'Tue/Thu next week')
- Status: 'Planning meetup' or 'Confirmed for [date]'
- Next Step: What needs to happen next

**For interview processes:**
- Stage of interview (applied, scheduling, completed)
- Key contacts and their roles
- What was requested (statements of work, availability, etc.)
- Status and next steps

**For intros/referrals offered:**
- Who is offering the intro
- Who they're connecting you to and why it's relevant
- Status: pending, intro made, meeting scheduled

**For follow-ups needed:**
- What's being followed up on
- Original context
- Next action required

## Step 3: Create new files for new people worth tracking
Only for business contacts with meaningful interaction potential.

## Step 4: Create Todoist tasks for action items
For each action item discovered, create a Todoist task using the MCP:

**Create tasks for:**
- Meetings/calls to schedule (e.g., "Schedule coffee with Jane - Tue/Thu next week")
- Follow-ups needed (e.g., "Follow up with John on mentorship program")
- Intros to request or make (e.g., "Get reliability intro from Jane")
- Interview next steps (e.g., "Submit statements of work to client")
- Responses needed (e.g., "Reply to Bob about project custom domain")

**Task format:**
- Clear action verb (Schedule, Follow up, Reply, Submit, etc.)
- Person's name
- Context in brief
- Set due date if mentioned or implied (e.g., "next week" = due in 7 days)
- Priority: p1 for time-sensitive, p2 for important, p3 for normal

## Step 5: Summary
List:
1. Each CRM file updated with what was added
2. Each Todoist task created

IMPORTANT: Actually update the files AND create the tasks. Don't just report what could be done - do it. Skip spam, newsletters, and automated messages.
" \
  --allowedTools "Read,Edit,Write,Glob,Grep,mcp__dooist__*" \
  --max-turns 50 \
  --max-budget-usd 5.00

CLAUDE_EXIT=$?

echo ""
echo "=========================================="
if [ $CLAUDE_EXIT -eq 0 ]; then
    echo "✅ Automated daily sync complete!"
    # Create lock file to prevent running again today
    touch "$LOCK_FILE"
else
    echo "⚠️  Claude Code exited with code $CLAUDE_EXIT"
fi
echo "Finished: $(date)"
echo "Log saved to: $LOG_FILE"
echo "=========================================="
