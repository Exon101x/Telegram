#!/usr/bin/env python3
"""
Telegram Session String Generator — Pyrogram + Telethon
==========================================================

Generates a session string for a Telegram user account or bot account,
using either Pyrogram v2 or Telethon as the underlying library. The
session string lets you reuse a login without re-entering phone/OTP/2FA
every time — useful for deploying bots/userbots to servers, Docker
containers, CI pipelines, etc.

Requirements:
    pip install -r requirements.txt

Credentials resolve in this order:
    1. Command-line arguments (--api-id, --api-hash, --bot-token)
    2. A .env file in the current directory (see .env.example)
    3. Interactive prompts (fallback if nothing else is set)

Usage:
    Interactive (asks which library, user/bot, etc.):
        python3 generate_session.py

    Non-interactive bot session, Telethon backend:
        python3 generate_session.py --lib telethon --bot \\
            --api-id 123456 --api-hash abcdef... --bot-token 123:ABC...

    User session, Pyrogram backend, saved as a .env-style line:
        python3 generate_session.py --lib pyrogram --user \\
            --output session_string.txt --format env

    Through a proxy:
        python3 generate_session.py --proxy socks5://user:pass@host:1080

IMPORTANT SECURITY NOTE:
    A session string grants full access to the account it was generated
    for. Treat it like a password — never share it, never commit it to
    git, and store it in an environment variable or secrets manager, not
    in plain source code.
"""

import argparse
import asyncio
import os
import sys

from session_backends import (
    BackendError,
    ConfigError,
    ExpiredCode,
    InvalidBotToken,
    InvalidCode,
    InvalidPassword,
    InvalidPhone,
    NeedsPassword,
    RateLimited,
    SessionGenError,
    get_backend,
    mask_session_string,
    parse_proxy,
)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def prompt(text: str) -> str:
    return input(text).strip()


def prompt_int(text: str) -> int:
    while True:
        val = prompt(text)
        if val.isdigit():
            return int(val)
        print("Please enter a numeric value.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a Pyrogram or Telethon session string for a user or bot account."
    )
    parser.add_argument(
        "--lib",
        choices=["pyrogram", "telethon"],
        default=None,
        help="Client library the session is for. Prompted if omitted.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--user", action="store_true", help="Generate a user-account session.")
    mode.add_argument("--bot", action="store_true", help="Generate a bot-account session.")
    parser.add_argument(
        "--api-id", type=int, default=None, help="Telegram api_id (overrides .env / prompt)."
    )
    parser.add_argument(
        "--api-hash", type=str, default=None, help="Telegram api_hash (overrides .env / prompt)."
    )
    parser.add_argument(
        "--bot-token", type=str, default=None, help="Bot token from @BotFather (bot mode only)."
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="socks5://[user:pass@]host:port (falls back to PROXY in .env).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to save the session string to, e.g. session_string.txt.",
    )
    parser.add_argument(
        "--format",
        choices=["raw", "env"],
        default="raw",
        help="raw: just the string. env: 'SESSION_STRING=<string>' line.",
    )
    parser.add_argument(
        "--mask",
        action="store_true",
        help="Only print a redacted version of the string; pair with --output to still save it.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress the save-to-file prompt.")
    return parser.parse_args()


def resolve_credentials(args):
    api_id = args.api_id or (int(os.environ["API_ID"]) if os.environ.get("API_ID") else None)
    if not api_id:
        api_id = prompt_int("API ID: ")

    api_hash = args.api_hash or os.environ.get("API_HASH")
    if not api_hash:
        api_hash = prompt("API Hash: ")

    return api_id, api_hash


def resolve_bot_token(args):
    bot_token = args.bot_token or os.environ.get("BOT_TOKEN")
    if not bot_token:
        bot_token = prompt("Bot Token: ")
    return bot_token


def choose_library(args) -> str:
    if args.lib:
        return args.lib
    print("\nWhich client library is this session for?")
    print("  1) Pyrogram (v2)")
    print("  2) Telethon")
    choice = prompt("Choose [1/2]: ").strip()
    return "telethon" if choice == "2" else "pyrogram"


def format_output(session_string: str, fmt: str) -> str:
    return f"SESSION_STRING={session_string}" if fmt == "env" else session_string


async def run_user_login(backend):
    phone = prompt("Phone number (international format, e.g. +14155552671): ")
    await backend.send_code(phone)
    code = prompt("Login code: ")
    try:
        await backend.sign_in_code(code)
    except NeedsPassword:
        password = prompt("Two-step verification password: ")
        await backend.sign_in_password(password)


def main():
    args = parse_args()

    print("=" * 64)
    print(" Telegram Session String Generator — Pyrogram + Telethon")
    print("=" * 64)
    print("\nGet api_id / api_hash from https://my.telegram.org/apps\n")

    api_id, api_hash = resolve_credentials(args)
    library = choose_library(args)

    proxy_url = args.proxy or os.environ.get("PROXY")
    proxy = None
    if proxy_url:
        try:
            proxy = parse_proxy(proxy_url)
        except ValueError as e:
            sys.exit(f"Invalid proxy value: {e}")

    is_bot = args.bot
    if not args.bot and not args.user:
        print("\nSession type:")
        print("  1) User account (personal/userbot session)")
        print("  2) Bot account (via BotFather token)")
        is_bot = prompt("Choose [1/2]: ").strip() == "2"

    async def run():
        backend = get_backend(library, api_id, api_hash, proxy=proxy)
        await backend.connect()
        try:
            if is_bot:
                bot_token = resolve_bot_token(args)
                await backend.start_as_bot(bot_token)
            else:
                await run_user_login(backend)
            me = await backend.get_me()
            session_string = await backend.export_session_string()
            return me, session_string
        finally:
            await backend.disconnect()

    try:
        me, session_string = asyncio.run(run())
    except ConfigError as e:
        sys.exit(f"\nConfiguration error: {e}")
    except InvalidPhone:
        sys.exit(
            "\nError: invalid phone number — include the country code with a "
            "leading '+', no spaces (e.g. +14155552671)."
        )
    except InvalidCode:
        sys.exit("\nError: wrong login code.")
    except ExpiredCode:
        sys.exit("\nError: that code expired — run the command again.")
    except InvalidPassword:
        sys.exit("\nError: wrong 2FA password.")
    except InvalidBotToken:
        sys.exit(
            "\nError: bot token was mistyped or revoked. Get a fresh one from "
            "@BotFather -> /mybots -> API Token."
        )
    except RateLimited as e:
        sys.exit(f"\nError: rate-limited by Telegram — wait {e.seconds} seconds and try again.")
    except BackendError as e:
        sys.exit(
            f"\nTelegram API error: {e}\nSee https://core.telegram.org/api/errors for details."
        )
    except SessionGenError as e:
        sys.exit(f"\nError: {e}")

    print(
        f"\nLogged in as: {me.first_name} (@{me.username or 'no-username'}, id={me.user_id}) via {library}"
    )
    print("\n" + "=" * 64)
    print(" SESSION STRING GENERATED")
    print("=" * 64)

    print(mask_session_string(session_string) if args.mask else session_string)
    print("=" * 64)
    print(
        "\nStore this securely (e.g. as an environment variable "
        "SESSION_STRING). Anyone with this string has full access "
        "to the account.\n"
    )

    if args.mask and not args.output:
        print(
            "Note: --mask was set with no --output, so the full string was "
            "never written anywhere — re-run with --output to actually save it."
        )

    output_path = args.output
    if not output_path and not args.quiet and not args.mask:
        save = prompt("Save to session_string.txt? [y/N]: ").lower()
        if save == "y":
            output_path = "session_string.txt"

    if output_path:
        with open(output_path, "w") as f:
            f.write(format_output(session_string, args.format))
        print(f"Saved to {output_path} — make sure it's listed in .gitignore.")


if __name__ == "__main__":
    main()
