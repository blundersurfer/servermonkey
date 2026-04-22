# Matrix Server + Robot Bot

Deploys a Continuwuity Matrix homeserver with Caddy TLS and a Robot chat bot on a Ubuntu LXC container.

## Architecture

```
Element Desktop → Caddy (:443) → Continuwuity (:6167)
                                 ↑
                  Robot Bot (matrix-nio → Claude API)
```

## Quick Start

### 1. Provision LXC container via ServerMonkey MCP

```
create_container: Ubuntu, 2 cores, 1GB RAM, 64GB disk
start_guest
run_script: bootstrap-ubuntu
```

### 2. Install Matrix server

```bash
# Via ServerMonkey run_script or guest_exec:
bash /path/to/install-matrix.sh
```

This installs Continuwuity + Caddy + ufw. Save the registration token from the output.

### 3. Create accounts

```bash
# Your account
curl -X POST http://localhost:6167/_matrix/client/v3/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"me","password":"CHANGEME","auth":{"type":"m.login.registration_token","token":"TOKEN"}}'

# Robot bot account
curl -X POST http://localhost:6167/_matrix/client/v3/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"robot","password":"CHANGEME","auth":{"type":"m.login.registration_token","token":"TOKEN"}}'
```

Then disable registration in `/etc/conduwuit/conduwuit.toml` and restart.

### 4. Install Robot bot

```bash
ANTHROPIC_API_KEY=sk-ant-... ROBOT_BOT_PASSWORD=... bash install-robot-bot.sh
```

### 5. Connect

Install Element Desktop, sign in to `https://matrix.example.com`, join `#robot-chat`.

## Files

| Script | Purpose |
|--------|---------|
| `install-matrix.sh` | Continuwuity + Caddy + firewall |
| `install-robot-bot.sh` | Python bot (matrix-nio + Claude API) |

## Services

```bash
service conduwuit status|start|stop|restart
service caddy status|start|stop|restart|reload
service robot-bot status|start|stop|restart
```
