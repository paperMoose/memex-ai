# Setup Guide

## System Requirements

- **macOS** (required for Apple ecosystem integrations)
- **Python 3** (uses only standard library - no pip installs required)
- **Cursor AI editor** (recommended) or **Claude Code CLI**
- **Git** (for version control)

## Installation

### 1. Clone the repository
```bash
git clone <repo-url> memex-ai
cd memex-ai
```

### 2. Optional Python dependency
```bash
# Only needed for some iMessage attributedBody decoding on older macOS
pip3 install biplist
```

### 3. Create data directories
```bash
mkdir -p people active_leads projects outreach weeks archive
```

## macOS Permissions

### Full Disk Access (Required)
**System Settings > Privacy & Security > Full Disk Access**

Add your terminal app (Terminal.app, iTerm2, Warp, etc.)

Required for:
- `imessage_dump.py`, `imessage_recent_threads.py` (Messages DB)
- `email_search.py` (Mail DB)
- `imessage_ingest.py` (Messages DB)

### Accessibility (Required for iMessage sending)
**System Settings > Privacy & Security > Accessibility**

Add your terminal app.

Required for:
- `imessage_send.py` (sending iMessages via AppleScript)

### Automation
AppleScript access to the following apps is granted automatically on first use:
- **Mail.app** (email scripts)
- **Calendar.app** (calendar_cli.py)
- **Reminders.app** (reminders_cli.py)
- **Messages.app** (iMessage scripts)

## Environment Setup

### Slack Integration (Optional)
1. Create a Slack App at https://api.slack.com/apps
2. Add OAuth scopes: `channels:history`, `groups:history`, `im:history`, `mpim:history`, `users:read`, `channels:read`
3. Install app to workspace and get OAuth token
4. Create `.env` file:
```bash
echo "SLACK_TOKEN=xoxp-your-token-here" > .env
```

### Focus Timer (Optional)
Set environment variables for custom behavior:
```bash
export FOCUS_SOUND_FILE=/System/Library/Sounds/Submarine.aiff
export FOCUS_FORCE_SOUND=1
export FOCUS_MIN_VOLUME=50
```

## Verify Installation

### Test iMessage access
```bash
python3 scripts/imessage_recent_threads.py --threads 5 --verbose
```

### Test email access
```bash
python3 scripts/email_search.py --from "your-email" --limit 10
```

### Test reminders
```bash
python3 scripts/reminders_cli.py --report-day today
```

### Run first sync
```bash
./scripts/daily_sync.sh today
```

## Database Locations

These are the macOS databases accessed by the scripts:

| Database | Location | Script |
|----------|----------|--------|
| **Contacts** | `~/Library/Application Support/AddressBook/AddressBook-v22.abcddb` | `new_contacts.py`, `imessage_recent_threads.py` |
| **iMessage** | `~/Library/Messages/chat.db` | `imessage_dump.py`, `imessage_recent_threads.py`, `imessage_ingest.py` |
| **Apple Mail** | `~/Library/Mail/V*/MailData/Envelope Index` | `email_search.py` |
| **Wispr Flow** | `~/Library/Application Support/Wispr Flow/flow.sqlite` | `wispr_dump.py` |
| **Granola** | `~/Library/Application Support/Granola/cache-v3.json` | `granola_dump.py` |

## Troubleshooting

### "osascript failed" or permission errors
- Grant Full Disk Access or Accessibility permissions
- Check System Settings > Privacy & Security

### "File not found" for Messages database
- Ensure Full Disk Access is granted
- Default path: `~/Library/Messages/chat.db`

### Reminders/Calendar not creating
- Check that AppleScript can control the app
- Try increasing `--timeout` value
- Verify list/calendar names exist

### iMessages not sending
- Verify Messages app is signed into iMessage
- Check contact identifiers (phone/email format)
- Ensure Accessibility permission granted

### No Slack data
- Check `SLACK_TOKEN` in `.env` file
- Verify OAuth token has required scopes

### No email data
- Grant Full Disk Access to terminal
- Verify Mail app is running and has downloaded messages

## Customization

### Email Accounts
Edit `daily_sync.sh` to add your email accounts for sent email export:
```bash
python3 "$SCRIPT_DIR/email_search.py" \
    --from "your-email@domain.com" \
    --since "$EMAIL_TIMEFRAME" \
    --limit 250 \
    > "$OUTPUT_DIR/emails_sent_account.txt"
```

### Stale Threshold
Edit `status_reporter.py` to change the staleness threshold:
```python
STALE_THRESHOLD_DAYS = 7  # Adjust as needed
```

### Collection Limits
Edit `daily_sync.sh` to adjust:
```bash
--threads 100              # iMessage threads
--messages-per-thread 50   # Messages per thread
--limit 500                # Received emails
--limit 250                # Sent emails per account
```
