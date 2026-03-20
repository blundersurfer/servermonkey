# Matrix Server + Shuri Bot

Deploys a Continuwuity Matrix homeserver with Caddy TLS and a Shuri chat bot on a Ubuntu LXC container.

## Architecture

```
Element Desktop → Caddy (:443) → Continuwuity (:6167)
                                 ↑
                  Shuri Bot (matrix-nio → Claude API)
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

# Shuri bot account
curl -X POST http://localhost:6167/_matrix/client/v3/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"shuri","password":"CHANGEME","auth":{"type":"m.login.registration_token","token":"TOKEN"}}'
```

Then disable registration in `/etc/conduwuit/conduwuit.toml` and restart.

### 4. Install Shuri bot

```bash
ANTHROPIC_API_KEY=sk-ant-... SHURI_BOT_PASSWORD=... bash install-shuri-bot.sh
```

### 5. Connect

Install Element Desktop, sign in to `https://matrix.nelsor.net`, join `#shuri-chat`.

## Files

| Script | Purpose |
|--------|---------|
| `install-matrix.sh` | Continuwuity + Caddy + firewall |
| `install-shuri-bot.sh` | Python bot (matrix-nio + Claude API) |

## Services

```bash
service conduwuit status|start|stop|restart
service caddy status|start|stop|restart|reload
service shuri-bot status|start|stop|restart
```
