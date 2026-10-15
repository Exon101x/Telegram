<div align="center">

# 🔐 Telegram Session Generator — Pyrogram & Telethon

**Maintained by Exon101x**

<!-- TODO: replace the # below with your actual GitHub repo/profile URL -->
[![GitHub](https://img.shields.io/badge/GitHub-Exon101x-181717?style=for-the-badge&logo=github&logoColor=white)](#)
<!-- TODO: replace the # below with your actual GitLab repo/profile URL -->
[![GitLab](https://img.shields.io/badge/GitLab-Exon101-FC6D26?style=for-the-badge&logo=gitlab&logoColor=white)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](#requirements)

</div>

---

A toolkit for generating Telegram **session strings** — for either
**Pyrogram v2** or **Telethon** — so you don't have to re-enter your phone
number, OTP, and 2FA password every time you deploy a bot or userbot.
Comes with a CLI generator, a validator, and an optional Telegram bot
front-end, all sharing one backend abstraction so both libraries get the
same features.

## Contents

- [Features](#features)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Usage](#usage)
  - [CLI generator](#cli-generator-generate_sessionpy)
  - [Validator](#validator-validate_sessionpy)
  - [Telegram bot](#telegram-bot-telegram_session_botpy)
- [Deployment](#deployment)
- [Configuration reference](#configuration-reference)
- [Using the session string in your own code](#using-the-session-string-in-your-own-code)
- [Architecture](#architecture)
- [Security notes](#security-notes)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- 🔷 **Pyrogram v2** and 🔶 **Telethon** support, side by side, behind one
  shared interface (`session_backends.py`) — no duplicated login logic.
- 👤 **User-account** and 🤖 **bot-account** session generation.
- 💬 **Three ways in**: a local interactive/CLI script, a one-shot
  validator, and a Telegram bot with inline buttons and a live step
  animation.
- 🌐 Optional **SOCKS5/SOCKS4/HTTP proxy** support for restricted networks.
- 🔒 **Masked display** mode (`--mask`) so you can generate a session on a
  screen you're sharing without exposing the raw string.
- 📄 Output as a **raw string** or a ready-to-paste **`SESSION_STRING=...`**
  `.env` line.
- 🧹 **Nothing is logged or persisted** by this code beyond what you
  explicitly ask it to save to a file.
- ✅ Tested, linted (ruff), formatted (black), and wired up with GitHub
  Actions CI.

## Repository layout

```
.
├── session_backends.py         # Shared Pyrogram/Telethon backend abstraction
├── generate_session.py         # CLI session generator (both libraries)
├── validate_session.py         # CLI session validator (both libraries)
├── telegram_session_bot.py     # Telegram bot front-end
├── run.sh / run.bat            # Cross-platform convenience launchers
├── Dockerfile / .dockerignore  # Run anywhere Docker runs
├── docker-compose.yml          # `docker compose up -d`
├── Procfile                    # For Railway / Render / Heroku-style platforms
├── deploy/
│   └── telegram-session-bot.service   # systemd unit for a VPS
├── requirements.txt            # Runtime dependencies
├── requirements-dev.txt        # Lint/test dependencies
├── pyproject.toml              # black/ruff configuration
├── .env.example                # Credential template — copy to .env
├── .gitignore
├── LICENSE                     # MIT
├── CONTRIBUTING.md
├── SECURITY.md
├── CODE_OF_CONDUCT.md
├── tests/
│   └── test_basic.py           # Network-free unit tests
└── .github/workflows/ci.yml    # Lint + test on every push/PR
```

## Requirements

- Python 3.10 or newer
- A Telegram `api_id` and `api_hash` from https://my.telegram.org/apps
  (the same pair works for both Pyrogram and Telethon — it identifies a
  Telegram *application*, not a library)
- For a **user session**: the account's phone number, access to its OTP
  code, and its 2FA password if one is set
- For a **bot session**: a bot token from [@BotFather](https://t.me/BotFather)

## Installation

Pick **one**. A virtual environment is recommended if you'll keep working
with this project; the other options are faster for a one-off run.

**Virtual environment (recommended):**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Install directly (override PEP 668's externally-managed-environment
protection):**
```bash
pip install -r requirements.txt --break-system-packages
```

**pipx** is not a good fit here — these are libraries you `import`, not a
standalone CLI tool to isolate.

## Quick start

```bash
cp .env.example .env
# fill in API_ID and API_HASH at minimum
python3 generate_session.py
```

You'll be asked which library, whether it's a user or bot account, and
then walked through the rest.

## Usage

### CLI generator (`generate_session.py`)

Interactive:
```bash
python3 generate_session.py
```

Fully non-interactive (useful in scripts/CI):
```bash
python3 generate_session.py \
  --lib telethon --bot \
  --api-id 123456 --api-hash your_api_hash \
  --bot-token 123456789:AAExampleTokenString \
  --output session_string.txt --format env --quiet
```

Through a proxy, masking the printed string:
```bash
python3 generate_session.py --proxy socks5://user:pass@host:1080 --mask --output session_string.txt
```

| Flag | Description |
|---|---|
| `--lib {pyrogram,telethon}` | Which backend to generate for. Prompted if omitted. |
| `--user` / `--bot` | Account type. Prompted if neither is passed. |
| `--api-id`, `--api-hash` | Overrides `.env` / interactive prompt. |
| `--bot-token` | Bot mode only; overrides `.env` / prompt. |
| `--proxy URL` | `socks5://[user:pass@]host:port` (also via `PROXY` in `.env`). |
| `--output PATH` | Save the session string to a file. |
| `--format {raw,env}` | `raw`: just the string. `env`: `SESSION_STRING=...` line. |
| `--mask` | Only print a redacted string; pair with `--output` to still save the real one. |
| `--quiet` | Skip the "save to file?" prompt. |

### Validator (`validate_session.py`)

Confirms a session string still works — handy right after generating one,
or periodically to check it hasn't been revoked.

```bash
python3 validate_session.py --lib pyrogram --session "AgD...your_string..."
python3 validate_session.py --lib telethon --file session_string.txt
python3 validate_session.py --lib pyrogram   # reads SESSION_STRING from .env
```

It logs in, prints the account name/ID/username, and counts visible chats
as a basic health check.

### Telegram bot (`telegram_session_bot.py`)

Lets people generate a session by chatting with a bot instead of running
anything locally: `/generate` → pick Pyrogram or Telethon → pick user or
bot account → phone/token → code → 2FA if needed → session string, each
step shown with a live spinner tied to the real network call.

#### ⚠️ Read this before deploying

Running this bot means **your server performs the login on the user's
behalf**. The operator sees, live, each user's phone number, login code,
2FA password, and resulting session string — equivalent to full account
access. Nothing is written to disk or logged by this script, but the
operator still sees it in memory as it happens. Telegram's own login-code
message warns people not to share that code with anyone, including bots,
for exactly this reason.

**Only use this for:**
- Generating sessions for your own account(s), or
- A small group of people who explicitly trust you with that access.

**Do not** deploy it as a public bot for strangers — from their side,
that's indistinguishable from an account-theft scam bot. Set
`ALLOWED_USER_IDS` in `.env` to restrict who can use `/generate`.

#### Setup

```bash
cp .env.example .env
# fill in API_ID, API_HASH, BOT_TOKEN, and (strongly recommended)
# ALLOWED_USER_IDS=123456789,987654321
pip install -r requirements.txt
python3 telegram_session_bot.py
```

#### Commands

| Command | What it does |
|---|---|
| `/start` | Welcome message, feature overview, security notice |
| `/generate` | Starts a new flow: library → account type → login |
| `/cancel` | Aborts the current flow and discards everything in progress |

In-progress flows idle for more than 5 minutes are automatically
disconnected and discarded. Finding a user's numeric ID for
`ALLOWED_USER_IDS`: have them message
[@userinfobot](https://t.me/userinfobot).

## Deployment

Everything here is plain Python + asyncio, so it runs the same way on
Windows, macOS, Linux, a VPS, a Raspberry Pi, or most "deploy from a repo"
hosting platforms. Pick whichever fits where you're putting it:

### Local machine (any OS)

```bash
./run.sh                 # Linux/macOS — runs telegram_session_bot.py
run.bat                   # Windows (cmd or PowerShell)

./run.sh generate_session.py --lib telethon   # or run any other script
```

Both scripts activate a local `.venv` automatically if one exists.

### VPS (systemd — keeps it running after you log out / on reboot)

```bash
# one-time setup
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
sudo cp deploy/telegram-session-bot.service /etc/systemd/system/
# edit the copied unit file's WorkingDirectory/ExecStart/User to match your path and user
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-session-bot

# logs
journalctl -u telegram-session-bot -f
```

### Docker (any machine with Docker — including most VPS and cloud hosts)

```bash
cp .env.example .env   # fill it in first
docker compose up -d --build
docker compose logs -f
```

Or without compose:
```bash
docker build -t session-bot .
docker run -d --env-file .env --restart unless-stopped session-bot
```

To run the CLI generator or validator inside the same image instead of the
bot:
```bash
docker run --rm -it --env-file .env session-bot python3 generate_session.py
```

### PaaS / "deploy from GitHub" hosts (Railway, Render, Fly.io, etc.)

Most of these platforms build straight from the `Dockerfile` if one's
present, or read the `Procfile` (`worker: python3 telegram_session_bot.py`)
for buildpack-based platforms. In either case:

1. Connect the repo.
2. Set `API_ID`, `API_HASH`, `BOT_TOKEN`, and `ALLOWED_USER_IDS` as
   environment variables in that platform's dashboard (not in `.env` —
   most platforms inject these directly and ignore committed `.env` files,
   which is correct since `.env` is gitignored anyway).
3. Deploy as a **worker/background process**, not a web service — this
   bot doesn't listen on a port.

This covers Railway, Render, and Fly.io directly; platforms without
background-worker support (most plain static/shared web hosting) aren't a
fit for a long-running bot process regardless of language — use a VPS or
one of the above instead.

### A note on `tgcrypto` across architectures

`tgcrypto` ships prebuilt wheels for common platforms; on less common
ones (some ARM boards, certain VPS images) pip falls back to compiling it,
which needs a C compiler. The Dockerfile already installs
`build-essential` for this; for a bare VPS/Pi, see the
[`tgcrypto` fails to build](#tgcrypto-fails-to-build) entry below. It's
optional either way — Pyrogram works without it, just slower.

## Configuration reference

All variables live in `.env` (see `.env.example`):

| Variable | Required for | Notes |
|---|---|---|
| `API_ID`, `API_HASH` | everything | From https://my.telegram.org/apps |
| `BOT_TOKEN` | bot-account sessions, the Telegram bot | From @BotFather |
| `ALLOWED_USER_IDS` | the Telegram bot | Comma-separated user IDs; blank = open to anyone |
| `PROXY` | optional | `socks5://[user:pass@]host:port`, used if `--proxy` isn't passed |

## Using the session string in your own code

**Pyrogram:**
```python
import os
from pyrogram import Client

app = Client(
    name="my_bot",
    api_id=YOUR_API_ID,
    api_hash="YOUR_API_HASH",
    session_string=os.environ["SESSION_STRING"],
    in_memory=True,
)

with app:
    app.send_message("me", "Session restored, no login needed!")
```

**Telethon:**
```python
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

client = TelegramClient(
    StringSession(os.environ["SESSION_STRING"]),
    YOUR_API_ID,
    "YOUR_API_HASH",
)

with client:
    client.send_message("me", "Session restored, no login needed!")
```

Load the string from an environment variable, `.env`, or a secrets
manager — never hardcode it in source.

## Architecture

`session_backends.py` defines one `AuthBackend` interface
(`connect`, `send_code`, `sign_in_code`, `sign_in_password`,
`start_as_bot`, `export_session_string`, `get_me`, `count_chats`,
`disconnect`) with two implementations, `PyrogramBackend` and
`TelethonBackend`. Each wraps its library's own exceptions into one
normalized set (`InvalidPhone`, `InvalidCode`, `ExpiredCode`,
`NeedsPassword`, `InvalidPassword`, `InvalidBotToken`, `RateLimited`,
`BackendError`, `ConfigError`), so `generate_session.py`,
`validate_session.py`, and `telegram_session_bot.py` all drive either
library through identical calling code and identical error handling. A
feature or fix added to the shared layer benefits both libraries and all
three entry points at once — see [CONTRIBUTING.md](CONTRIBUTING.md) if
you're extending it.

## Security notes

- A session string is equivalent to a **password** for the account it
  came from. Anyone holding it can read and send messages as that account.
- Never commit `session_string.txt`, `.env`, or any `*.session` file —
  `.gitignore` already excludes them.
- Regenerate (and revoke the old one via **Telegram Settings → Devices**)
  if you ever suspect a string has leaked.
- Prefer bot sessions over user sessions when possible — a compromised
  bot token has a smaller blast radius than a compromised personal account.
- See [SECURITY.md](SECURITY.md) for the vulnerability-reporting policy
  and what's in/out of scope.

## Troubleshooting

### `externally-managed-environment`
Recent Debian/Ubuntu block system-wide `pip install` (PEP 668). Use a
virtual environment, or `pip install -r requirements.txt --break-system-packages`.

### `python: command not found`
Use `python3 ...`, or `sudo apt install python-is-python3`, or activate a
venv (where `python` resolves automatically).

### `ModuleNotFoundError: No module named 'pyrogram'` / `'telethon'`
The library isn't installed in the environment you're running with.
Check `which python3` / `which pip3`, confirm your venv is activated, and
reinstall with `pip install -r requirements.txt`.

### `tgcrypto` fails to build
```bash
sudo apt update && sudo apt install build-essential python3-dev
pip install tgcrypto --break-system-packages
```
It's optional — Pyrogram works without it, just slower. Drop it from
`requirements.txt` if it keeps failing.

### `ApiIdInvalid` / `ApiIdInvalidError` / "Configuration error: api_id/api_hash is invalid"
Re-copy both values fresh from https://my.telegram.org/apps. No quotes,
no extra spaces.

### `PhoneNumberInvalid` / `PhoneNumberInvalidError`
Always include the country code with a leading `+`, no spaces or dashes:
`+14155552671`, not `4155552671`.

### `PhoneCodeInvalid` / `PhoneCodeExpired` (and the `...Error` Telethon equivalents)
Re-run and enter the code promptly — codes expire within a couple of
minutes. Make sure you're reading it from the Telegram app itself.

### "Two-step verification is enabled" / `NeedsPassword`
Expected — just send your 2FA password when asked. Forgot it? Reset it
under **Telegram Settings → Privacy and Security → Two-Step Verification**.

### `FloodWait` / `FloodWaitError` / `RateLimited`
Telegram is rate-limiting login attempts. Wait the stated number of
seconds before retrying; avoid repeatedly cancelling and restarting.

### `AccessTokenInvalid` / `AccessTokenInvalidError` (bot mode)
The bot token was mistyped or revoked. Get a fresh one via @BotFather →
`/mybots` → your bot → **API Token**.

### Connection/timeout errors on a VPS
Some providers/regions throttle or block Telegram's data centers.
```bash
curl -v https://api.telegram.org
```
If blocked, use `--proxy` (or the bot's `PROXY` env var).

### Bot replies "This bot is private. You're not on the allowed list."
Intended behavior of the `ALLOWED_USER_IDS` allowlist — add the user's
numeric ID (via [@userinfobot](https://t.me/userinfobot)) and restart.

### Bot never responds
Confirm the process is running and printed `Bot started as @yourbotname`;
have the user press **Start** in the bot's chat first; check `BOT_TOKEN`.

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
black .
ruff check .
pytest -q
```

CI (`.github/workflows/ci.yml`) runs the same three checks on every push
and PR, across Python 3.10–3.12. The test suite is network-free — it
checks `session_backends.py`'s pure-Python helpers and that every script
compiles, without needing real Telegram credentials.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, guidelines, and the PR
checklist. Please keep the security warnings intact and the two backends
symmetric — see [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

[MIT](LICENSE) © 2026 Exon101
