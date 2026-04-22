#!/bin/bash
# install-robot-bot.sh — Install Robot Matrix bot (Claude API bridge)
#
# Usage: Run inside the Matrix LXC container after install-matrix.sh:
#   ANTHROPIC_API_KEY=sk-ant-... bash install-robot-bot.sh
#
# Requires:
#   - Continuwuity running (install-matrix.sh completed)
#   - Robot bot account already created on the homeserver
#   - ANTHROPIC_API_KEY environment variable set
#
# What it does:
#   1. Creates robot-bot system user
#   2. Sets up Python venv with matrix-nio + anthropic
#   3. Writes bot script and config
#   4. Creates init.d service
#   5. Starts bot

set -euo pipefail

# --- Configuration ---
BOT_DIR="/opt/robot-bot"
BOT_USER="robot-bot"
HOMESERVER_URL="http://127.0.0.1:6167"
SERVER_NAME="${MATRIX_SERVER_NAME:-matrix.example.com}"
BOT_USERNAME="robot"
BOT_PASSWORD="${ROBOT_BOT_PASSWORD:-}"
API_KEY="${ANTHROPIC_API_KEY:-}"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()  { echo -e "\n${GREEN}━━━ Step $1: $2 ━━━${NC}"; }

# --- Preflight ---
if [ "$(id -u)" -ne 0 ]; then
    error "Must run as root"
    exit 1
fi

if [ -z "$API_KEY" ]; then
    error "ANTHROPIC_API_KEY not set. Run: ANTHROPIC_API_KEY=sk-ant-... bash install-robot-bot.sh"
    exit 1
fi

if [ -z "$BOT_PASSWORD" ]; then
    error "ROBOT_BOT_PASSWORD not set. Run: ROBOT_BOT_PASSWORD=... ANTHROPIC_API_KEY=... bash install-robot-bot.sh"
    exit 1
fi

# --- Step 1: System user ---
step 1 "Creating bot system user"

if id "$BOT_USER" &>/dev/null; then
    info "User '$BOT_USER' already exists"
else
    adduser --system --group --no-create-home --home "$BOT_DIR" "$BOT_USER"
    info "Created system user '$BOT_USER'"
fi

# --- Step 2: Python venv ---
step 2 "Setting up Python environment"

export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq python3 python3-pip python3-venv >/dev/null 2>&1

install -d -m 750 -o "$BOT_USER" -g "$BOT_USER" "$BOT_DIR"
install -d -m 750 -o "$BOT_USER" -g "$BOT_USER" /var/log/robot-bot

if [ -d "$BOT_DIR/venv" ]; then
    info "Python venv already exists"
else
    python3 -m venv "$BOT_DIR/venv"
    "$BOT_DIR/venv/bin/pip" install --quiet matrix-nio anthropic aiohttp pyyaml
    chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR/venv"
    info "Python venv created with matrix-nio + anthropic"
fi

# --- Step 3: Bot config ---
step 3 "Writing bot configuration"

if [ -f "$BOT_DIR/config.yaml" ]; then
    warn "config.yaml already exists — skipping (delete to regenerate)"
else
    cat > "$BOT_DIR/config.yaml" << EOF
# Robot Matrix Bot Configuration
homeserver_url: "${HOMESERVER_URL}"
server_name: "${SERVER_NAME}"
bot_username: "${BOT_USERNAME}"
bot_password: "${BOT_PASSWORD}"
anthropic_api_key: "${API_KEY}"

# Claude model configuration
model: "claude-sonnet-4-6"
max_tokens: 4096
system_prompt: |
  You are Robot, a personal AI assistant. You are helpful, direct, and conversational.
  Keep responses concise but thorough. Use markdown formatting when it aids clarity.
  You are chatting via Matrix, so messages should feel natural and conversational.

# Room configuration
auto_join: true
room_alias: "#robot-chat:${SERVER_NAME}"

# Conversation memory (messages to keep in context)
context_window: 20
EOF
    chown "$BOT_USER:$BOT_USER" "$BOT_DIR/config.yaml"
    chmod 600 "$BOT_DIR/config.yaml"
    info "Wrote $BOT_DIR/config.yaml (permissions: 600)"
fi

# --- Step 4: Bot script ---
step 4 "Writing bot script"

cat > "$BOT_DIR/bot.py" << 'BOTEOF'
#!/usr/bin/env python3
"""Robot Matrix Bot — bridges Matrix chat to Claude API."""

import asyncio
import logging
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml
from nio import (
    AsyncClient,
    InviteMemberEvent,
    LoginResponse,
    MatrixRoom,
    RoomMessageText,
)

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("/var/log/robot-bot/bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("robot-bot")


def load_config() -> dict:
    """Load bot configuration from config.yaml."""
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        log.error("config.yaml not found at %s", config_path)
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


class RobotBotState:
    """Manages conversation history per room."""

    def __init__(self, context_window: int = 20):
        self.conversations: dict[str, list[dict]] = defaultdict(list)
        self.context_window = context_window
        self.start_time = time.time()

    def add_message(self, room_id: str, role: str, content: str):
        self.conversations[room_id].append({"role": role, "content": content})
        # Trim to context window
        if len(self.conversations[room_id]) > self.context_window:
            self.conversations[room_id] = self.conversations[room_id][
                -self.context_window :
            ]

    def get_history(self, room_id: str) -> list[dict]:
        return list(self.conversations[room_id])


async def run_bot():
    """Main bot loop."""
    config = load_config()
    state = RobotBotState(context_window=config.get("context_window", 20))

    # Initialize Claude client
    claude = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    model = config.get("model", "claude-sonnet-4-6")
    max_tokens = config.get("max_tokens", 4096)
    system_prompt = config.get("system_prompt", "You are Robot, a helpful AI assistant.")

    # Initialize Matrix client
    client = AsyncClient(
        config["homeserver_url"],
        f"@{config['bot_username']}:{config['server_name']}",
    )

    # Login
    log.info("Logging in as @%s:%s", config["bot_username"], config["server_name"])
    resp = await client.login(config["bot_password"])
    if not isinstance(resp, LoginResponse):
        log.error("Login failed: %s", resp)
        await client.close()
        sys.exit(1)
    log.info("Logged in successfully")

    # Auto-join handler
    async def on_invite(room: MatrixRoom, event: InviteMemberEvent):
        if event.membership == "invite":
            log.info("Invited to %s — joining", room.room_id)
            await client.join(room.room_id)

    # Message handler
    async def on_message(room: MatrixRoom, event: RoomMessageText):
        # Ignore own messages
        if event.sender == client.user_id:
            return

        # Ignore messages from before bot started (avoid replaying history)
        if event.server_timestamp / 1000 < state.start_time:
            return

        user_msg = event.body
        log.info("[%s] %s: %s", room.display_name, event.sender, user_msg[:100])

        # Add to conversation history
        state.add_message(room.room_id, "user", user_msg)

        try:
            # Call Claude API
            response = claude.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=state.get_history(room.room_id),
            )
            reply = response.content[0].text

            # Add response to history
            state.add_message(room.room_id, "assistant", reply)

            # Send to Matrix room
            await client.room_send(
                room.room_id,
                "m.room.message",
                {
                    "msgtype": "m.text",
                    "body": reply,
                    "format": "org.matrix.custom.html",
                    "formatted_body": reply,
                },
            )
            log.info("[%s] Robot replied (%d chars)", room.display_name, len(reply))

        except anthropic.APIError as e:
            log.error("Claude API error: %s", e)
            await client.room_send(
                room.room_id,
                "m.room.message",
                {
                    "msgtype": "m.notice",
                    "body": f"API error: {e.message}",
                },
            )

    # Register callbacks
    client.add_event_callback(on_invite, InviteMemberEvent)
    client.add_event_callback(on_message, RoomMessageText)

    # Create/join default room
    room_alias = config.get("room_alias", f"#robot-chat:{config['server_name']}")
    log.info("Checking for room: %s", room_alias)
    try:
        room_resp = await client.room_resolve_alias(room_alias)
        if hasattr(room_resp, "room_id"):
            await client.join(room_resp.room_id)
            log.info("Joined existing room: %s", room_alias)
        else:
            # Room doesn't exist — create it
            create_resp = await client.room_create(
                alias=room_alias.split(":")[0].lstrip("#"),
                name="Robot Chat",
                topic="Chat with Robot — your personal AI assistant",
                is_direct=False,
            )
            log.info("Created room: %s", room_alias)
    except Exception as e:
        log.warning("Room setup issue (non-fatal): %s", e)

    # Start sync loop
    log.info("Bot ready — listening for messages...")
    await client.sync_forever(timeout=30000, full_state=True)


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        log.info("Bot stopped by user")
    except Exception as e:
        log.error("Bot crashed: %s", e, exc_info=True)
        sys.exit(1)
BOTEOF

chown "$BOT_USER:$BOT_USER" "$BOT_DIR/bot.py"
chmod 755 "$BOT_DIR/bot.py"
info "Wrote $BOT_DIR/bot.py"

# --- Step 5: Init.d service ---
step 5 "Creating bot init.d service"

cat > /etc/init.d/robot-bot << INITEOF
#!/bin/sh
### BEGIN INIT INFO
# Provides:          robot-bot
# Required-Start:    \$local_fs \$network conduwuit
# Required-Stop:     \$local_fs \$network
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Robot Matrix bot
# Description:       Robot — Matrix bot bridging chat to Claude API
### END INIT INFO

DAEMON=${BOT_DIR}/venv/bin/python3
DAEMON_ARGS="${BOT_DIR}/bot.py"
NAME=robot-bot
PIDFILE=/var/run/robot-bot.pid
USER=${BOT_USER}
GROUP=${BOT_USER}
WORKDIR=${BOT_DIR}
LOGFILE=/var/log/robot-bot/bot.log

do_start() {
    if [ -f "\$PIDFILE" ] && kill -0 "\$(cat "\$PIDFILE")" 2>/dev/null; then
        echo "\$NAME is already running"
        return 0
    fi
    echo "Starting \$NAME..."
    start-stop-daemon --start --quiet --background \\
        --make-pidfile --pidfile "\$PIDFILE" \\
        --chuid "\$USER:\$GROUP" --chdir "\$WORKDIR" \\
        --exec "\$DAEMON" -- \$DAEMON_ARGS
}

do_stop() {
    if [ ! -f "\$PIDFILE" ] || ! kill -0 "\$(cat "\$PIDFILE")" 2>/dev/null; then
        echo "\$NAME is not running"
        return 0
    fi
    echo "Stopping \$NAME..."
    start-stop-daemon --stop --quiet --pidfile "\$PIDFILE" --retry=TERM/10/KILL/5
    rm -f "\$PIDFILE"
}

do_status() {
    if [ -f "\$PIDFILE" ] && kill -0 "\$(cat "\$PIDFILE")" 2>/dev/null; then
        echo "\$NAME is running (PID \$(cat "\$PIDFILE"))"
        return 0
    else
        echo "\$NAME is not running"
        return 1
    fi
}

case "\$1" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_stop; sleep 1; do_start ;;
    status)  do_status ;;
    *)       echo "Usage: \$0 {start|stop|restart|status}"; exit 1 ;;
esac
INITEOF

chmod 755 /etc/init.d/robot-bot
update-rc.d robot-bot defaults
info "Robot bot init.d service created and enabled"

# --- Step 6: Start bot ---
step 6 "Starting Robot bot"

service robot-bot start
sleep 3

if service robot-bot status >/dev/null 2>&1; then
    info "Robot bot is running"
else
    warn "Robot bot may still be starting — check: cat /var/log/robot-bot/bot.log"
fi

# --- Summary ---
echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Robot Matrix Bot installed successfully${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
echo "  Bot user:    @${BOT_USERNAME}:${SERVER_NAME}"
echo "  Room:        #robot-chat:${SERVER_NAME}"
echo "  Config:      ${BOT_DIR}/config.yaml"
echo "  Logs:        /var/log/robot-bot/bot.log"
echo "  Service:     service robot-bot status"
echo ""
echo "  Open Element Desktop → join #robot-chat → start chatting!"
echo ""
