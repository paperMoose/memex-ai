#!/usr/bin/env python3
"""
slack_dump.py

Read-only exporter for Slack conversations with filtering.

Setup:
1. Create Slack App at https://api.slack.com/apps
2. Add OAuth scopes: channels:history, groups:history, im:history, mpim:history, 
   users:read, channels:read, groups:read
3. Install app to workspace and get OAuth token
4. Set token in .env file: SLACK_TOKEN=xoxp-your-token-here

Usage examples:
  # Export all messages from a channel
  python3 scripts/slack_dump.py --channels "general"
  
  # Export with date filter
  python3 scripts/slack_dump.py --channels "sales,partnerships" --since "2025-11-01"
  
  # Search for keywords
  python3 scripts/slack_dump.py --channels "general" --contains "proposal,contract"
  
  # Export ALL DMs (including Slack Connect external DMs)
  python3 scripts/slack_dump.py --all-dms
  
  # Export DMs with specific user (by name)
  python3 scripts/slack_dump.py --dms "Stephanie Wiseman"
  
  # Export specific channel/DM by ID (useful for Slack Connect)
  python3 scripts/slack_dump.py --channel-ids "D0A089DAML1,C0A08EF1XAM"
  
  # Save to file
  python3 scripts/slack_dump.py --channels "sales" --output "/tmp/slack_export.md"
  
  # Export as JSON
  python3 scripts/slack_dump.py --channels "general" --format jsonl

Note: For Slack Connect (external) DMs, use --all-dms or --channel-ids since 
external users may not appear in the normal user list.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode


SLACK_API_BASE = "https://slack.com/api"


def load_env_file(env_path: Optional[str] = None) -> None:
    """Load environment variables from .env file."""
    if env_path is None:
        # Look for .env in the repo root (parent of scripts/)
        script_dir = Path(__file__).parent
        env_path = script_dir.parent / ".env"
    else:
        env_path = Path(env_path)
    
    if not env_path.exists():
        return
    
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Parse KEY=VALUE format
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                # Only set if not already in environment
                if key not in os.environ:
                    os.environ[key] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Slack messages (read-only)")
    parser.add_argument(
        "--token",
        help="Slack OAuth token (or set SLACK_TOKEN in .env file or env var)",
    )
    parser.add_argument(
        "--env-file",
        help="Path to .env file (default: looks for .env in repo root)",
    )
    parser.add_argument(
        "--channels",
        help="Comma-separated channel names to export (e.g., 'general,sales')",
    )
    parser.add_argument(
        "--dms",
        help="Comma-separated user emails/IDs for DM export",
    )
    parser.add_argument(
        "--all-channels",
        action="store_true",
        help="Export all public channels you're a member of",
    )
    parser.add_argument(
        "--all-dms",
        action="store_true",
        help="Export all DMs and group DMs (including Slack Connect)",
    )
    parser.add_argument(
        "--channel-ids",
        help="Comma-separated channel/DM IDs to export directly (e.g., 'D0A089DAML1,C0A08EF1XAM')",
    )
    parser.add_argument(
        "--since",
        default="2001-01-01",
        help="'today'|'yesterday'|'last-week'|YYYY-MM-DD (default: 2001-01-01)",
    )
    parser.add_argument(
        "--before",
        help="Optional end date: YYYY-MM-DD",
    )
    parser.add_argument(
        "--contains",
        help="Only include messages containing these keywords (comma-separated, case-insensitive)",
    )
    parser.add_argument(
        "--from-user",
        help="Filter by sender (user email or display name)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max messages per channel (0 = no limit, default: 0)",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "jsonl", "csv"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output to stderr",
    )
    return parser.parse_args()


def slack_api_call(
    method: str,
    token: str,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Make a Slack API call and return JSON response."""
    url = f"{SLACK_API_BASE}/{method}"
    
    if params:
        # Filter out None values
        params = {k: v for k, v in params.items() if v is not None}
        if method in ["conversations.history", "conversations.list", "conversations.info", "users.list", "users.conversations"]:
            # GET request
            if params:
                url = f"{url}?{urlencode(params)}"
            req = Request(url)
        else:
            # POST request
            data = json.dumps(params).encode('utf-8')
            req = Request(url, data=data, headers={"Content-Type": "application/json"})
    else:
        req = Request(url)
    
    req.add_header("Authorization", f"Bearer {token}")
    
    try:
        with urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            if not result.get("ok"):
                error = result.get("error", "unknown_error")
                raise RuntimeError(f"Slack API error: {error}")
            return result
    except HTTPError as e:
        error_body = e.read().decode('utf-8')
        raise RuntimeError(f"HTTP error {e.code}: {error_body}")


def get_user_map(token: str, verbose: bool = False) -> Dict[str, Dict[str, str]]:
    """
    Fetch all users and create mappings:
    - user_id -> {name, real_name, email}
    - email -> user_id
    """
    if verbose:
        sys.stderr.write("Fetching user list...\n")
    
    user_id_map: Dict[str, Dict[str, str]] = {}
    email_map: Dict[str, str] = {}
    
    cursor = None
    while True:
        result = slack_api_call("users.list", token, {"cursor": cursor, "limit": 200})
        
        for member in result.get("members", []):
            user_id = member.get("id", "")
            profile = member.get("profile", {})
            
            name = member.get("name", "")
            real_name = profile.get("real_name", name)
            email = profile.get("email", "")
            
            user_id_map[user_id] = {
                "name": name,
                "real_name": real_name,
                "email": email
            }
            
            if email:
                email_map[email.lower()] = user_id
        
        cursor = result.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
        
        time.sleep(0.5)  # Rate limiting
    
    if verbose:
        sys.stderr.write(f"Loaded {len(user_id_map)} users\n")
    
    return {"by_id": user_id_map, "by_email": email_map}


def get_channel_list(
    token: str,
    channel_names: Optional[List[str]] = None,
    all_channels: bool = False,
    verbose: bool = False
) -> List[Dict[str, str]]:
    """
    Get list of channels to export.
    Returns list of {id, name, type} dicts.
    """
    if verbose:
        sys.stderr.write("Fetching channel list...\n")
    
    channels = []
    cursor = None
    
    while True:
        result = slack_api_call(
            "conversations.list",
            token,
            {
                "types": "public_channel,private_channel",
                "cursor": cursor,
                "limit": 200,
                "exclude_archived": True
            }
        )
        
        for channel in result.get("channels", []):
            channel_id = channel.get("id", "")
            channel_name = channel.get("name", "")
            is_member = channel.get("is_member", False)
            
            # Only include channels we're a member of
            if not is_member:
                continue
            
            # Filter by name if specified
            if channel_names and channel_name not in channel_names:
                continue
            
            channels.append({
                "id": channel_id,
                "name": channel_name,
                "type": "channel"
            })
        
        cursor = result.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
        
        time.sleep(0.5)  # Rate limiting
    
    if verbose:
        sys.stderr.write(f"Found {len(channels)} channels\n")
    
    return channels


def get_all_conversations(
    token: str,
    user_map: Dict[str, Any],
    types: str = "im,mpim",
    verbose: bool = False
) -> List[Dict[str, str]]:
    """
    Get all conversations using users.conversations API.
    
    Tries each conversation type separately to handle missing scopes gracefully.
    Returns list of {id, name, type} dicts.
    """
    conversations = []
    
    # Split types and try each separately (handles missing scope errors gracefully)
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    
    for conv_type in type_list:
        if verbose:
            sys.stderr.write(f"Fetching {conv_type} conversations...\n")
        
        cursor = None
        type_count = 0
        
        while True:
            try:
                result = slack_api_call(
                    "users.conversations",
                    token,
                    {
                        "types": conv_type,
                        "cursor": cursor,
                        "limit": 200,
                        "exclude_archived": True
                    }
                )
            except RuntimeError as e:
                if "missing_scope" in str(e):
                    if verbose:
                        sys.stderr.write(f"  Skipping {conv_type} (missing scope)\n")
                    break
                raise
            
            for conv in result.get("channels", []):
                conv_id = conv.get("id", "")
                conv_name = conv.get("name", "")
                is_im = conv.get("is_im", False)
                is_mpim = conv.get("is_mpim", False)
                is_ext_shared = conv.get("is_ext_shared", False)
                
                # Determine conversation name
                if is_im:
                    # Single DM - get user name from user_map or user_profile
                    user_id = conv.get("user", "")
                    user_info = user_map["by_id"].get(user_id, {})
                    display_name = user_info.get("real_name") or user_info.get("name") or ""
                    
                    # For external users, try to get name via users.info or the most recent message
                    if not display_name and is_ext_shared:
                        try:
                            # Try users.info first
                            user_result = slack_api_call("users.info", token, {"user": user_id})
                            ext_profile = user_result.get("user", {}).get("profile", {})
                            display_name = ext_profile.get("real_name") or ext_profile.get("display_name") or ""
                        except:
                            pass
                        
                        if not display_name:
                            # Try to get from conversation history (first message from them)
                            try:
                                hist_result = slack_api_call("conversations.history", token, {"channel": conv_id, "limit": 10})
                                for msg in hist_result.get("messages", []):
                                    if msg.get("user") == user_id:
                                        profile = msg.get("user_profile", {})
                                        display_name = profile.get("real_name") or profile.get("display_name") or ""
                                        if display_name:
                                            break
                            except:
                                pass
                        
                        if not display_name:
                            display_name = f"External ({user_id[:8]})"
                    
                    if not display_name:
                        display_name = user_id
                    
                    name = f"DM: {display_name}"
                    ctype = "dm"
                elif is_mpim:
                    # Group DM
                    name = conv_name or f"Group DM ({conv_id})"
                    if not conv_name and conv.get("purpose", {}).get("value"):
                        name = f"Group DM: {conv['purpose']['value'][:50]}"
                    ctype = "mpim"
                else:
                    name = conv_name or conv_id
                    ctype = "channel"
                
                # Add external indicator for Slack Connect
                if is_ext_shared:
                    name = f"{name} (external)"
                
                conversations.append({
                    "id": conv_id,
                    "name": name,
                    "type": ctype,
                    "is_external": is_ext_shared
                })
                type_count += 1
            
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
            
            time.sleep(0.5)  # Rate limiting
        
        if verbose and type_count > 0:
            sys.stderr.write(f"  Found {type_count} {conv_type} conversations\n")
    
    if verbose:
        sys.stderr.write(f"Total: {len(conversations)} conversations\n")
    
    return conversations


def get_dm_list(
    token: str,
    user_map: Dict[str, Any],
    dm_filters: Optional[List[str]] = None,
    all_dms: bool = False,
    verbose: bool = False
) -> List[Dict[str, str]]:
    """
    Get list of DM conversations.
    Returns list of {id, name, type} dicts.
    
    Uses users.conversations API which works with im:history scope
    (doesn't require im:read).
    """
    if verbose:
        sys.stderr.write("Fetching DM list...\n")
    
    # First try users.conversations (works with im:history)
    all_convos = get_all_conversations(token, user_map, types="im,mpim", verbose=verbose)
    
    if not all_convos:
        # Fallback to conversations.list (requires im:read)
        if verbose:
            sys.stderr.write("Trying conversations.list fallback...\n")
        
        dms = []
        cursor = None
        
        try:
            while True:
                result = slack_api_call(
                    "conversations.list",
                    token,
                    {
                        "types": "im,mpim",
                        "cursor": cursor,
                        "limit": 200,
                        "exclude_archived": True
                    }
                )
                
                for conv in result.get("channels", []):
                    conv_id = conv.get("id", "")
                    user_id = conv.get("user", "")
                    
                    user_info = user_map["by_id"].get(user_id, {})
                    user_name = user_info.get("real_name") or user_info.get("name") or user_id
                    
                    dms.append({
                        "id": conv_id,
                        "name": f"DM: {user_name}",
                        "type": "dm"
                    })
                
                cursor = result.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
                
                time.sleep(0.5)
            
            all_convos = dms
        except RuntimeError as e:
            if "missing_scope" in str(e):
                sys.stderr.write("\nError: Cannot list DMs - missing required scopes.\n")
                sys.stderr.write("Your token has im:history (can read messages) but needs im:read (to list DMs).\n")
                sys.stderr.write("\nOptions:\n")
                sys.stderr.write("  1. Add im:read scope to your Slack app and reinstall\n")
                sys.stderr.write("  2. Use --all-dms to auto-discover DMs via users.conversations\n")
                sys.stderr.write("  3. Provide channel IDs directly with --channel-ids\n")
                sys.stderr.write("\nSee: https://api.slack.com/apps\n")
                sys.exit(1)
            raise
    
    # If all_dms, return everything
    if all_dms and not dm_filters:
        return all_convos
    
    # Apply filters if specified
    if dm_filters:
        # Convert filters to user IDs and names
        target_user_ids = set()
        target_names = set()
        
        for filter_term in dm_filters:
            filter_lower = filter_term.lower()
            # Check if it's an email
            if "@" in filter_term and filter_lower in user_map["by_email"]:
                target_user_ids.add(user_map["by_email"][filter_lower])
            # Check if it's a user ID
            elif filter_term in user_map["by_id"]:
                target_user_ids.add(filter_term)
            # Add as name filter
            target_names.add(filter_lower)
            
            # Also search user map by name
            for user_id, user_info in user_map["by_id"].items():
                if (filter_lower in user_info["name"].lower() or
                    filter_lower in user_info["real_name"].lower()):
                    target_user_ids.add(user_id)
        
        # Filter conversations
        filtered = []
        for conv in all_convos:
            conv_name_lower = conv["name"].lower()
            # Match by name in conversation title
            if any(name in conv_name_lower for name in target_names):
                filtered.append(conv)
        
        if verbose:
            sys.stderr.write(f"Filtered to {len(filtered)} DMs matching: {dm_filters}\n")
        
        return filtered
    
    return all_convos


def parse_since_expr(expr: str) -> dt.datetime:
    """Parse --since argument into datetime."""
    now = dt.datetime.now()
    s = expr.strip().lower()
    
    if s in ("all", "*"):
        return dt.datetime(2001, 1, 1, 0, 0, 0)
    if s == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if s == "yesterday":
        y = now - dt.timedelta(days=1)
        return y.replace(hour=0, minute=0, second=0, microsecond=0)
    if s == "last-week":
        w = now - dt.timedelta(days=7)
        return w.replace(hour=0, minute=0, second=0, microsecond=0)
    
    try:
        return dt.datetime.strptime(expr, "%Y-%m-%d").replace(hour=0, minute=0)
    except ValueError:
        raise ValueError("--since must be today|yesterday|last-week|YYYY-MM-DD")


def fetch_messages(
    token: str,
    channel_id: str,
    user_map: Dict[str, Any],
    since_ts: Optional[float] = None,
    before_ts: Optional[float] = None,
    limit: int = 0,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """Fetch all messages from a channel/DM."""
    messages = []
    cursor = None
    
    while True:
        params = {
            "channel": channel_id,
            "cursor": cursor,
            "limit": 200,  # Max per request
        }
        
        if since_ts:
            params["oldest"] = str(since_ts)
        if before_ts:
            params["latest"] = str(before_ts)
        
        result = slack_api_call("conversations.history", token, params)
        
        for msg in result.get("messages", []):
            ts = msg.get("ts", "")
            user_id = msg.get("user", "")
            text = msg.get("text", "")
            
            # Get user info - check message's user_profile first (for external users)
            msg_profile = msg.get("user_profile", {})
            user_info = user_map["by_id"].get(user_id, {})
            sender_name = (
                msg_profile.get("real_name") or 
                msg_profile.get("display_name") or
                user_info.get("real_name") or 
                user_info.get("name") or 
                user_id
            )
            
            # Convert timestamp to readable format
            try:
                dt_obj = dt.datetime.fromtimestamp(float(ts))
                sent_ts = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                sent_ts = ts
            
            messages.append({
                "ts": ts,
                "sent_ts": sent_ts,
                "user_id": user_id,
                "sender": sender_name,
                "text": text
            })
        
        cursor = result.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
        
        # Apply limit if specified
        if limit > 0 and len(messages) >= limit:
            messages = messages[:limit]
            break
        
        time.sleep(0.5)  # Rate limiting
    
    # Sort by timestamp (oldest first)
    messages.sort(key=lambda m: float(m["ts"]))
    
    return messages


def filter_messages(
    messages: List[Dict[str, Any]],
    keyword_filters: Optional[List[str]] = None,
    user_filter: Optional[str] = None,
    user_map: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Apply post-fetch filters to messages."""
    filtered = messages
    
    # Keyword filter
    if keyword_filters:
        keywords_lower = [k.lower() for k in keyword_filters]
        filtered = [
            msg for msg in filtered
            if any(kw in msg["text"].lower() for kw in keywords_lower)
        ]
    
    # User filter
    if user_filter and user_map:
        user_lower = user_filter.lower()
        target_user_ids = set()
        
        # Check email
        if "@" in user_filter and user_lower in user_map["by_email"]:
            target_user_ids.add(user_map["by_email"][user_lower])
        
        # Check by ID
        if user_filter in user_map["by_id"]:
            target_user_ids.add(user_filter)
        
        # Check by name
        for user_id, user_info in user_map["by_id"].items():
            if (user_lower in user_info["name"].lower() or
                user_lower in user_info["real_name"].lower()):
                target_user_ids.add(user_id)
        
        filtered = [msg for msg in filtered if msg["user_id"] in target_user_ids]
    
    return filtered


def write_markdown(
    conversations: List[tuple],
    output_path: Optional[str],
    verbose: bool = False
) -> None:
    """Write conversations to markdown format."""
    lines = [
        f"# Slack Export",
        f"Exported: {dt.datetime.now():%Y-%m-%d %H:%M}",
        f"Conversations: {len(conversations)}",
        ""
    ]
    
    for channel_name, messages in conversations:
        lines.append(f"## {channel_name}")
        lines.append(f"Messages: {len(messages)}")
        lines.append("")
        
        for msg in messages:
            lines.append(f"**{msg['sender']}** [{msg['sent_ts']}]")
            lines.append(f"> {msg['text']}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
    
    content = "\n".join(lines)
    
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        if verbose:
            sys.stderr.write(f"Wrote to {output_path}\n")
    else:
        sys.stdout.write(content)


def write_jsonl(
    conversations: List[tuple],
    output_path: Optional[str],
    verbose: bool = False
) -> None:
    """Write conversations to JSONL format."""
    lines = []
    
    for channel_name, messages in conversations:
        for msg in messages:
            obj = {
                "channel": channel_name,
                "ts": msg["ts"],
                "sent_ts": msg["sent_ts"],
                "sender": msg["sender"],
                "text": msg["text"]
            }
            lines.append(json.dumps(obj, ensure_ascii=False))
    
    content = "\n".join(lines) + "\n"
    
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        if verbose:
            sys.stderr.write(f"Wrote {len(lines)} messages to {output_path}\n")
    else:
        sys.stdout.write(content)


def write_csv(
    conversations: List[tuple],
    output_path: Optional[str],
    verbose: bool = False
) -> None:
    """Write conversations to CSV format."""
    import csv
    
    fieldnames = ["channel", "ts", "sent_ts", "sender", "text"]
    
    if output_path:
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for channel_name, messages in conversations:
                for msg in messages:
                    writer.writerow({
                        "channel": channel_name,
                        "ts": msg["ts"],
                        "sent_ts": msg["sent_ts"],
                        "sender": msg["sender"],
                        "text": msg["text"]
                    })
        
        if verbose:
            sys.stderr.write(f"Wrote CSV to {output_path}\n")
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        
        for channel_name, messages in conversations:
            for msg in messages:
                writer.writerow({
                    "channel": channel_name,
                    "ts": msg["ts"],
                    "sent_ts": msg["sent_ts"],
                    "sender": msg["sender"],
                    "text": msg["text"]
                })


def main() -> None:
    args = parse_args()
    
    # Load .env file if it exists
    load_env_file(args.env_file)
    
    # Get token from args or environment
    token = args.token or os.environ.get("SLACK_TOKEN")
    
    # Validate token
    if not token:
        sys.stderr.write("Error: Slack token required.\n")
        sys.stderr.write("Options:\n")
        sys.stderr.write("  1. Create a .env file in repo root with: SLACK_TOKEN=xoxb-your-token\n")
        sys.stderr.write("  2. Set environment variable: export SLACK_TOKEN=xoxb-your-token\n")
        sys.stderr.write("  3. Use --token flag: --token xoxb-your-token\n")
        sys.stderr.write("\nGet token at: https://api.slack.com/apps\n")
        sys.exit(1)
    
    # Parse filters
    keyword_filters = None
    if args.contains:
        keyword_filters = [k.strip() for k in args.contains.split(",") if k.strip()]
    
    channel_names = None
    if args.channels:
        channel_names = [c.strip() for c in args.channels.split(",") if c.strip()]
    
    dm_filters = None
    if args.dms:
        dm_filters = [d.strip() for d in args.dms.split(",") if d.strip()]
    
    channel_ids = None
    if args.channel_ids:
        channel_ids = [c.strip() for c in args.channel_ids.split(",") if c.strip()]
    
    if not (args.channels or args.dms or args.all_channels or args.all_dms or channel_ids):
        sys.stderr.write("Error: Specify --channels, --dms, --all-channels, --all-dms, or --channel-ids\n")
        sys.exit(1)
    
    # Parse date range
    since_dt = parse_since_expr(args.since)
    since_ts = since_dt.timestamp()
    
    before_ts = None
    if args.before:
        before_dt = parse_since_expr(args.before)
        before_ts = before_dt.timestamp()
    
    # Fetch user map
    user_map = get_user_map(token, verbose=args.verbose)
    
    # Get conversations to export
    conversations_to_export = []
    
    # Direct channel IDs (bypass discovery)
    if channel_ids:
        if args.verbose:
            sys.stderr.write(f"Using {len(channel_ids)} direct channel IDs\n")
        for cid in channel_ids:
            # Try to get channel info for better naming
            try:
                result = slack_api_call("conversations.info", token, {"channel": cid})
                channel_info = result.get("channel", {})
                name = channel_info.get("name", "")
                is_im = channel_info.get("is_im", False)
                is_mpim = channel_info.get("is_mpim", False)
                
                if is_im:
                    user_id = channel_info.get("user", "")
                    user_info = user_map["by_id"].get(user_id, {})
                    name = f"DM: {user_info.get('real_name') or user_info.get('name') or user_id}"
                elif is_mpim:
                    # For group DMs, try to get member names
                    purpose = channel_info.get("purpose", {}).get("value", "")
                    name = f"Group DM: {purpose[:50]}" if purpose else f"Group DM ({cid})"
                elif not name:
                    name = cid
                
                conversations_to_export.append({
                    "id": cid,
                    "name": name,
                    "type": "im" if is_im else "mpim" if is_mpim else "channel"
                })
            except RuntimeError:
                # If we can't get info, still try to fetch messages
                conversations_to_export.append({
                    "id": cid,
                    "name": cid,
                    "type": "unknown"
                })
    
    if args.channels or args.all_channels:
        channels = get_channel_list(
            token,
            channel_names=channel_names,
            all_channels=args.all_channels,
            verbose=args.verbose
        )
        conversations_to_export.extend(channels)
    
    if args.dms or args.all_dms:
        dms = get_dm_list(
            token,
            user_map,
            dm_filters=dm_filters,
            all_dms=args.all_dms,
            verbose=args.verbose
        )
        conversations_to_export.extend(dms)
    
    if not conversations_to_export:
        sys.stderr.write("No conversations found matching filters\n")
        sys.exit(0)
    
    # Fetch and filter messages
    all_conversations = []
    
    for conv in conversations_to_export:
        if args.verbose:
            sys.stderr.write(f"Fetching messages from {conv['name']}...\n")
        
        messages = fetch_messages(
            token,
            conv["id"],
            user_map,
            since_ts=since_ts,
            before_ts=before_ts,
            limit=args.limit,
            verbose=args.verbose
        )
        
        # Apply filters
        filtered_messages = filter_messages(
            messages,
            keyword_filters=keyword_filters,
            user_filter=args.from_user,
            user_map=user_map
        )
        
        if filtered_messages:
            all_conversations.append((conv["name"], filtered_messages))
            if args.verbose:
                sys.stderr.write(f"  Found {len(filtered_messages)} messages\n")
    
    # Write output
    if args.format == "markdown":
        write_markdown(all_conversations, args.output, verbose=args.verbose)
    elif args.format == "jsonl":
        write_jsonl(all_conversations, args.output, verbose=args.verbose)
    else:
        write_csv(all_conversations, args.output, verbose=args.verbose)
    
    if args.verbose:
        total_messages = sum(len(msgs) for _, msgs in all_conversations)
        sys.stderr.write(f"\n✓ Exported {total_messages} messages from {len(all_conversations)} conversations\n")


if __name__ == "__main__":
    main()

