#!/usr/bin/env python3
"""
Session String Validator — Pyrogram + Telethon
=================================================

Quick sanity check that a session string actually logs in, for either
backend. Connects, prints basic account info and a recent-chats count,
then disconnects. Useful right after generating a session, or before
deploying it somewhere, to confirm it hasn't expired or been revoked.

Usage:
    python3 validate_session.py --lib pyrogram --session "AgD..."
    python3 validate_session.py --lib telethon --file session_string.txt
    python3 validate_session.py --lib pyrogram   # reads SESSION_STRING from .env/env
"""

import argparse
import asyncio
import os
import sys

from session_backends import (
    BackendError,
    ConfigError,
    SessionGenError,
    get_backend,
)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def parse_args():
    parser = argparse.ArgumentParser(description="Validate a Pyrogram or Telethon session string.")
    parser.add_argument(
        "--lib",
        choices=["pyrogram", "telethon"],
        required=True,
        help="Which library generated this session string.",
    )
    parser.add_argument(
        "--session", type=str, default=None, help="Session string (overrides file/env)."
    )
    parser.add_argument(
        "--file", type=str, default=None, help="Path to a file containing the session string."
    )
    parser.add_argument(
        "--api-id", type=int, default=None, help="Telegram api_id (falls back to .env)."
    )
    parser.add_argument(
        "--api-hash", type=str, default=None, help="Telegram api_hash (falls back to .env)."
    )
    return parser.parse_args()


def resolve_session_string(args) -> str:
    raw = None
    if args.session:
        raw = args.session.strip()
    elif args.file:
        with open(args.file) as f:
            raw = f.read().strip()
    elif os.environ.get("SESSION_STRING"):
        raw = os.environ["SESSION_STRING"].strip()

    if not raw:
        sys.exit(
            "No session string provided. Pass --session, --file, or set "
            "SESSION_STRING in your environment/.env."
        )

    # Tolerate a string saved via generate_session.py --format env
    if raw.startswith("SESSION_STRING="):
        raw = raw.split("=", 1)[1].strip()
    return raw


async def validate(library: str, api_id: int, api_hash: str, session_string: str):
    backend = get_backend(library, api_id, api_hash, session_string=session_string)
    await backend.connect()
    try:
        me = await backend.get_me()
        print("Session is valid.\n")
        print(f"  Library: {library}")
        print(f"  Account: {me.first_name} {me.last_name or ''}".rstrip())
        print(f"  Username: @{me.username}" if me.username else "  Username: (none)")
        print(f"  User ID: {me.user_id}")
        print(f"  Is bot: {me.is_bot}")
        print(f"  Phone: {me.phone}" if me.phone else "  Phone: (hidden or bot account)")

        count = await backend.count_chats(limit=50)
        suffix = "+" if count == 50 else ""
        print(f"  Visible chats (first 50 checked): {count}{suffix}")
    finally:
        await backend.disconnect()


def main():
    args = parse_args()

    api_id = args.api_id or (int(os.environ["API_ID"]) if os.environ.get("API_ID") else None)
    api_hash = args.api_hash or os.environ.get("API_HASH")

    if not api_id or not api_hash:
        sys.exit(
            "api_id / api_hash not found. Pass --api-id/--api-hash or set "
            "API_ID/API_HASH in your environment/.env."
        )

    session_string = resolve_session_string(args)

    try:
        asyncio.run(validate(args.lib, api_id, api_hash, session_string))
    except ConfigError as e:
        sys.exit(f"\nConfiguration error: {e}")
    except BackendError as e:
        sys.exit(
            f"\nTelegram API error: {e}\n"
            "The session may be revoked or expired — generate a new one."
        )
    except SessionGenError as e:
        sys.exit(f"\nError: {e}")


if __name__ == "__main__":
    main()
