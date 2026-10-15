# Contributing

Thanks for considering a contribution! This is a small, focused toolkit, so
the bar is simple: keep it readable, keep it honest about what it does, and
keep the security warnings intact.

## Getting set up

```bash
git clone <this repo>
cd <repo>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # fill in your own test credentials
```

## Before opening a PR

```bash
black .
ruff check .
pytest
```

All three should pass cleanly — CI runs the same checks on every PR.

## Guidelines

- **Don't weaken the security warnings.** The README and bot copy about
  session strings being equivalent to a password, and about the bot
  operator's visibility into the login flow, are load-bearing — please
  don't soften or remove them.
- **Keep the two backends symmetric.** `session_backends.py` normalizes
  Pyrogram and Telethon behind one interface (`AuthBackend`). If you add a
  feature to one backend, add it to the other too, or explain in the PR
  why it doesn't apply.
- **No telemetry, no silent logging of secrets.** Nothing in this repo
  should write phone numbers, codes, passwords, or session strings to
  disk, logs, or any third-party service.
- **Small, focused PRs** are easier to review than large ones — if you're
  planning a big change, open an issue first to discuss the approach.

## Reporting bugs

Open an issue with: what you ran, what you expected, what happened
instead, and your Python version. Redact any phone numbers, codes, or
session strings from logs/screenshots before posting them.

## Security issues

Please don't open a public issue for a security vulnerability — see
[SECURITY.md](SECURITY.md) instead.
