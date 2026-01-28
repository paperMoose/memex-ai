#!/bin/bash
#
# daily_sync.sh
#
# Complete CRM daily sync workflow:
#   1. Collect communications (Slack, iMessage, Email)
#   2. Generate contact directories for each data stream
#   3. Present summaries for CRM enrichment
#   4. Cleanup intermediate files
#
# Usage:
#   ./scripts/daily_sync.sh [timeframe] [--keep-raw]
#
# Arguments:
#   timeframe  - Optional: "today", "yesterday", "last-week" (default: "last-week")
#   --keep-raw - Optional: Keep intermediate raw export files (default: delete)
#
# Example:
#   ./scripts/daily_sync.sh              # Default: last week's activity for full coverage
#   ./scripts/daily_sync.sh today        # Just today's activity
#   ./scripts/daily_sync.sh last-week --keep-raw  # Keep intermediate files

set -e  # Exit on error

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="/tmp/crm_daily_sync_$(date +%Y%m%d_%H%M%S)"

# Parse arguments
# Default to last-week for comprehensive coverage (not just today)
TIMEFRAME="${1:-last-week}"
KEEP_RAW=false

# Check for --keep-raw flag
for arg in "$@"; do
    if [ "$arg" = "--keep-raw" ]; then
        KEEP_RAW=true
    fi
done

# Map timeframe to email_search.py compatible format
# email_search.py accepts: YYYY-MM-DD, today, yesterday, week, month
case "$TIMEFRAME" in
    "last-week") EMAIL_TIMEFRAME="week" ;;
    *) EMAIL_TIMEFRAME="$TIMEFRAME" ;;
esac

DATE_LABEL=$(date +%Y-%m-%d)
RUN_ID="$(basename "$OUTPUT_DIR")"
PERSIST_DIR="$REPO_ROOT/archive/daily_sync_reports/$DATE_LABEL/$RUN_ID"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "=================================="
echo "CRM Daily Sync - $DATE_LABEL"
echo "Timeframe: $TIMEFRAME"
echo "Output: $OUTPUT_DIR"
echo "=================================="
echo ""

# 1. Export Slack conversations
echo "📱 [1/8] Fetching Slack messages..."
if python3 "$SCRIPT_DIR/slack_dump.py" \
    --all-channels \
    --since "$TIMEFRAME" \
    --output "$OUTPUT_DIR/slack.md" \
    --verbose 2>&1 | grep -v "^Fetching"; then
    echo "   ✓ Slack export complete: $OUTPUT_DIR/slack.md"
else
    echo "   ✗ Slack export failed (check SLACK_TOKEN in .env)"
fi
echo ""

# 2. Export recent iMessage threads
echo "💬 [2/8] Fetching iMessage conversations..."
if python3 "$SCRIPT_DIR/imessage_recent_threads.py" \
    --threads 100 \
    --messages-per-thread 50 \
    --output "$OUTPUT_DIR/imessages.md" \
    --verbose 2>&1 | tail -1; then
    echo "   ✓ iMessage export complete: $OUTPUT_DIR/imessages.md"
else
    echo "   ✗ iMessage export failed (check Full Disk Access permissions)"
fi
echo ""

# 3. Export recent emails (received)
echo "📧 [3/8] Fetching received emails..."
if python3 "$SCRIPT_DIR/email_search.py" \
    --since "$EMAIL_TIMEFRAME" \
    --limit 500 \
    --body \
    --body-limit 500 \
    --columns "date,from,subject,body" \
    > "$OUTPUT_DIR/emails_received.txt" 2>/dev/null; then
    
    # Convert to markdown format for easier reading
    {
        echo "# Received Emails - $DATE_LABEL"
        echo "Timeframe: $TIMEFRAME"
        echo ""
        cat "$OUTPUT_DIR/emails_received.txt"
    } > "$OUTPUT_DIR/emails_received.md"
    rm "$OUTPUT_DIR/emails_received.txt"
    
    # Count emails
    EMAIL_COUNT=$(grep -c "^[0-9]" "$OUTPUT_DIR/emails_received.md" || echo "0")
    echo "   ✓ Received emails export complete: $OUTPUT_DIR/emails_received.md ($EMAIL_COUNT emails)"
else
    echo "   ✗ Received emails export failed (check Full Disk Access permissions)"
fi
echo ""

# 4. Export recent emails (sent) - search BOTH accounts for full coverage
echo "📤 [4/8] Fetching sent emails..."
{
    # Export from primary email account
    # TODO: Replace with your email address(es)
    python3 "$SCRIPT_DIR/email_search.py" \
        --from "you@gmail.com" \
        --since "$EMAIL_TIMEFRAME" \
        --limit 250 \
        --body \
        --body-limit 500 \
        --columns "date,from,subject,body" 2>/dev/null

    # Export from work account (add more accounts as needed)
    python3 "$SCRIPT_DIR/email_search.py" \
        --from "you@company.com" \
        --since "$EMAIL_TIMEFRAME" \
        --limit 250 \
        --body \
        --body-limit 500 \
        --columns "date,from,subject,body" 2>/dev/null
} > "$OUTPUT_DIR/emails_sent.txt"

if [ -s "$OUTPUT_DIR/emails_sent.txt" ]; then
    # Convert to markdown format for easier reading
    {
        echo "# Sent Emails - $DATE_LABEL"
        echo "Timeframe: $TIMEFRAME"
        echo "Accounts: you@gmail.com, you@company.com"
        echo ""
        cat "$OUTPUT_DIR/emails_sent.txt"
    } > "$OUTPUT_DIR/emails_sent.md"
    rm "$OUTPUT_DIR/emails_sent.txt"
    
    # Count emails
    EMAIL_COUNT=$(grep -c "^[0-9]" "$OUTPUT_DIR/emails_sent.md" || echo "0")
    echo "   ✓ Sent emails export complete: $OUTPUT_DIR/emails_sent.md ($EMAIL_COUNT emails)"
else
    rm -f "$OUTPUT_DIR/emails_sent.txt"
    echo "   ✗ Sent emails export failed (check Full Disk Access permissions)"
fi
echo ""

# 5. Extract Granola meeting transcripts
echo "📝 [5/8] Extracting Granola meeting transcripts..."
if python3 "$SCRIPT_DIR/granola_dump.py" \
    --output-dir "$OUTPUT_DIR/granola_transcripts" \
    --format markdown 2>&1 | tail -3; then

    # Count transcripts
    GRANOLA_COUNT=$(ls -1 "$OUTPUT_DIR/granola_transcripts"/*.md 2>/dev/null | wc -l | tr -d ' ')
    echo "   ✓ Granola extraction complete: $GRANOLA_COUNT meeting transcripts"
else
    echo "   ✗ Granola extraction failed (check Granola app)"
fi
echo ""

# 6. Process exports into contact directories
echo "🔄 [6/8] Processing exports into contact directories..."
if python3 "$SCRIPT_DIR/process_daily_sync.py" "$OUTPUT_DIR" 2>&1; then
    echo "   ✓ Contact directories generated"
else
    echo "   ✗ Processing failed"
    exit 1
fi
echo ""

# 7. Search emails for active contacts
echo "🔍 [7/8] Searching emails for active contacts..."
if python3 "$SCRIPT_DIR/search_active_contacts.py" \
    --output "$OUTPUT_DIR/ACTIVE_CONTACT_EMAILS.md" \
    --limit 5 2>&1 | tail -3; then
    echo "   ✓ Active contact emails summary generated"
else
    echo "   ✗ Active contact email search failed"
fi
echo ""

# 8. Generate status report for stale items
echo "📋 [8/8] Generating CRM status report..."
if python3 "$REPO_ROOT/status_reporter.py" > "$OUTPUT_DIR/STATUS_REPORT.txt" 2>/dev/null; then
    # Count stale items
    STALE_COUNT=$(grep -c ">7d old" "$OUTPUT_DIR/STATUS_REPORT.txt" || echo "0")
    echo "   ✓ Status report generated: $OUTPUT_DIR/STATUS_REPORT.txt"
    if [ "$STALE_COUNT" -gt 0 ]; then
        echo "   ⚠️  Found $STALE_COUNT stale items (>7 days old) - review recommended"
    fi
else
    echo "   ✗ Status report failed"
fi
echo ""

# Persist key reports into repo so they don't get lost in /tmp
echo "🗂️  Persisting daily sync reports to repo..."
mkdir -p "$PERSIST_DIR"
for report in IMESSAGE_CONTACTS.md NEW_PEOPLE_CANDIDATES.md RECENT_PEOPLE_TOUCHPOINTS.md OUTREACH_DRAFTS.md SLACK_CONTACTS.md EMAIL_RECEIVED_CONTACTS.md EMAIL_SENT_CONTACTS.md ACTIVE_CONTACT_EMAILS.md STATUS_REPORT.txt; do
    if [ -f "$OUTPUT_DIR/$report" ]; then
        cp "$OUTPUT_DIR/$report" "$PERSIST_DIR/$report"
    fi
done
echo "   ✓ Saved reports to: $PERSIST_DIR"
echo ""

# Summary
echo "=================================="
echo "✓ Daily sync complete!"
echo "=================================="
echo ""
echo "📂 Output location: $OUTPUT_DIR"
echo "🗂️  Saved to repo: $PERSIST_DIR"
echo ""
echo "📊 Generated Contact Directories:"
echo ""

# List generated reports
for report in IMESSAGE_CONTACTS.md NEW_PEOPLE_CANDIDATES.md RECENT_PEOPLE_TOUCHPOINTS.md OUTREACH_DRAFTS.md SLACK_CONTACTS.md EMAIL_RECEIVED_CONTACTS.md EMAIL_SENT_CONTACTS.md ACTIVE_CONTACT_EMAILS.md STATUS_REPORT.txt; do
    if [ -f "$OUTPUT_DIR/$report" ]; then
        echo "  ✓ $report"
    fi
done

# List Whisper transcripts if any
if [ -d "$OUTPUT_DIR/whisper_transcripts" ]; then
    WHISPER_COUNT=$(ls -1 "$OUTPUT_DIR/whisper_transcripts"/*.md 2>/dev/null | wc -l | tr -d ' ')
    if [ "$WHISPER_COUNT" -gt 0 ]; then
        echo "  ✓ whisper_transcripts/ ($WHISPER_COUNT transcripts)"
    fi
fi

echo ""
echo "Next steps:"
echo "  1. Review contact directories in: $OUTPUT_DIR"
echo "  2. Use AI to identify CRM updates needed"
echo "  3. Enrich CRM files with relevant information"
echo ""
echo "Quick review commands:"
echo "  # View iMessage contacts"
echo "  less $OUTPUT_DIR/IMESSAGE_CONTACTS.md"
echo ""
echo "  # View new people candidates (from texts)"
echo "  less $OUTPUT_DIR/NEW_PEOPLE_CANDIDATES.md"
echo ""
echo "  # View follow-up cues for recently updated people"
echo "  less $OUTPUT_DIR/RECENT_PEOPLE_TOUCHPOINTS.md"
echo ""
echo "  # View outreach drafts (review-only)"
echo "  less $OUTPUT_DIR/OUTREACH_DRAFTS.md"
echo ""
echo "  # View Slack conversations"
echo "  less $OUTPUT_DIR/SLACK_CONTACTS.md"
echo ""
echo "  # View received email contacts"
echo "  less $OUTPUT_DIR/EMAIL_RECEIVED_CONTACTS.md"
echo ""
echo "  # View sent email contacts"
echo "  less $OUTPUT_DIR/EMAIL_SENT_CONTACTS.md"
echo ""
echo "  # View Whisper transcripts"
echo "  ls $OUTPUT_DIR/whisper_transcripts/"
echo "  less $OUTPUT_DIR/whisper_transcripts/[filename].md"
echo ""
echo "  # Search for specific person/company"
echo "  grep -i 'david' $OUTPUT_DIR/*CONTACTS.md"
echo "  grep -i 'david' $OUTPUT_DIR/whisper_transcripts/*.md"
echo ""
echo "  # View emails from active CRM contacts"
echo "  less $OUTPUT_DIR/ACTIVE_CONTACT_EMAILS.md"
echo ""
echo "  # View CRM status report (stale items)"
echo "  less $OUTPUT_DIR/STATUS_REPORT.txt"
echo "  grep '>7d old' $OUTPUT_DIR/STATUS_REPORT.txt"
echo ""

# Cleanup intermediate files
if [ "$KEEP_RAW" = false ]; then
    echo "🗑️  Cleaning up intermediate files..."
    rm -f "$OUTPUT_DIR/slack.md"
    rm -f "$OUTPUT_DIR/imessages.md"
    rm -f "$OUTPUT_DIR/emails_received.md"
    rm -f "$OUTPUT_DIR/emails_sent.md"
    echo "   ✓ Deleted raw export files (keeping contact directories)"
    echo "   Use --keep-raw flag to preserve intermediate files"
    echo ""
else
    echo "📁 Keeping raw export files (--keep-raw flag set)"
    echo ""
fi

