#!/usr/bin/env python3
"""
Telegram Bot: Session Generator — Pyrogram + Telethon
========================================================

Lets a user generate a session string — for either Pyrogram v2 or
Telethon, user account or bot account — by talking to a Telegram bot
instead of running a local script.

⚠️  SECURITY MODEL — READ BEFORE DEPLOYING
-------------------------------------------
This bot performs the Telegram login on YOUR SERVER on the user's behalf.
That means whoever runs this bot process sees, live, each user's phone
number, login code, 2FA password, and the resulting session string (which
is equivalent to full account access — same as a password). Nothing here
is written to disk or logged, but the operator still sees it in-memory as
it happens. Telegram's own login-code message tells people not to share
that code with anyone, including bots, for exactly this reason.

Use this only for:
    - Generating sessions for your own account(s), or
    - A small, trusted group of people who explicitly understand and
      accept that you (the operator) can see their session string as
      it's generated.

Do NOT deploy this as a public bot for arbitrary strangers — that is
indistinguishable, from the user's side, from an account-theft scam bot.
Set ALLOWED_USER_IDS below to restrict who can use /generate.

Requirements:
    pip install -r requirements.txt

Required environment variables (.env):
    API_ID, API_HASH   — from https://my.telegram.org/apps (powers the bot
                         itself, and is reused for whichever backend a
                         user picks — Pyrogram and Telethon both just need
                         a Telegram "application" api_id/api_hash, not a
                         library-specific one)
    BOT_TOKEN          — from @BotFather, for the bot's own identity
    ALLOWED_USER_IDS   — optional, comma-separated Telegram user IDs.
                         Leave unset to allow anyone (NOT recommended
                         beyond personal/local testing).
    PROXY              — optional, socks5://[user:pass@]host:port, used
                         for the generated sessions' connections.

Run:
    python3 telegram_session_bot.py
"""

import asyncio
import os
import sys
import time

try:
    from pyrogram import Client, filters, idle
    from pyrogram.enums import ChatAction
    from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
except ImportError:
    sys.exit(
        "Pyrogram is not installed. Install dependencies first with:\n"
        "    pip install -r requirements.txt"
    )

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
    parse_proxy,
)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not (API_ID and API_HASH and BOT_TOKEN):
    sys.exit(
        "Missing API_ID / API_HASH / BOT_TOKEN. Set them in a .env file "
        "(see .env.example) or as environment variables."
    )

API_ID = int(API_ID)

_allowed_raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
ALLOWED_USER_IDS = (
    {int(uid.strip()) for uid in _allowed_raw.split(",") if uid.strip()}
    if _allowed_raw
    else None  # None = no restriction (open to anyone who can message the bot)
)

PROXY = None
_proxy_raw = os.environ.get("PROXY", "").strip()
if _proxy_raw:
    try:
        PROXY = parse_proxy(_proxy_raw)
    except ValueError as e:
        sys.exit(f"Invalid PROXY value in .env: {e}")

FLOW_TIMEOUT_SECONDS = 300  # abandon an in-progress login after 5 minutes idle

bot = Client(
    "session_gen_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# Per-user in-progress state. Never written to disk; cleared as soon as a
# flow finishes, errors, is cancelled, or times out.
user_flows: dict[int, dict] = {}

WARNING_TEXT = (
    "⚠️ **Before you continue**\n"
    "Generating a session here means this bot's server performs your login, "
    "so whoever runs this bot sees your phone number, login code, and the "
    "resulting session string while it happens. A session string is "
    "equivalent to your account password. Only continue if you trust this "
    "bot's operator with that level of access to this account.\n"
)


def is_authorized(user_id: int) -> bool:
    return ALLOWED_USER_IDS is None or user_id in ALLOWED_USER_IDS


# ---------------------------------------------------------------------------
# Step animation
# ---------------------------------------------------------------------------
# A small braille spinner edited into a status message while the real
# network call for that step is in flight, so progress feels live rather
# than frozen between a message sent and a reply. It settles to a ✅ line
# on success (or ⚠️ on failure) once the actual result comes back — the
# animation tracks real latency, it isn't a fixed fake delay.

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
SPINNER_INTERVAL = 0.4  # seconds between frames


async def run_with_status(
    reply_text_fn, working_label: str, done_label: str, coro, benign_exceptions=()
):
    """
    Sends a status message reading "⏳ {working_label}", animates a spinner
    in front of that label while awaiting `coro`, then settles the message
    to "✅ {done_label}" once it resolves (or "⚠️ ..." on an unhandled
    error). If `coro` raises one of `benign_exceptions`, the message still
    settles to "✅ {done_label}" before the exception is re-raised — the
    step itself succeeded (e.g. a code that's correct but needs 2FA next).
    """
    status = await reply_text_fn(f"⏳ {working_label}")
    stop = asyncio.Event()

    async def spin():
        i = 0
        while not stop.is_set():
            frame = SPINNER_FRAMES[i % len(SPINNER_FRAMES)]
            try:
                await status.edit_text(f"{frame} {working_label}")
            except Exception:
                pass
            i += 1
            try:
                await asyncio.wait_for(stop.wait(), timeout=SPINNER_INTERVAL)
            except asyncio.TimeoutError:
                pass

    spinner_task = asyncio.create_task(spin())

    async def settle(text: str):
        stop.set()
        await spinner_task
        try:
            await status.edit_text(text)
        except Exception:
            pass

    try:
        result = await coro
    except benign_exceptions:
        await settle(f"✅ {done_label}")
        raise
    except Exception:
        await settle(f"⚠️ {working_label} — that didn't work.")
        raise
    else:
        await settle(f"✅ {done_label}")
        return result


async def abort_flow(user_id: int):
    flow = user_flows.pop(user_id, None)
    if flow and "backend" in flow:
        try:
            await flow["backend"].disconnect()
        except Exception:
            pass


async def cleanup_loop():
    """Disconnects and discards any login flow left idle too long."""
    while True:
        await asyncio.sleep(60)
        now = time.time()
        stale = [
            uid
            for uid, flow in list(user_flows.items())
            if now - flow["last_active"] > FLOW_TIMEOUT_SECONDS
        ]
        for uid in stale:
            await abort_flow(uid)


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

START_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("🚀 Generate Session", callback_data="start_generate")],
        [InlineKeyboardButton("❌ Cancel", callback_data="start_cancel")],
    ]
)

LIBRARY_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("🔷 Pyrogram", callback_data="lib_pyrogram")],
        [InlineKeyboardButton("🔶 Telethon", callback_data="lib_telethon")],
    ]
)

ACCOUNT_TYPE_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("👤 User account", callback_data="acct_user")],
        [InlineKeyboardButton("🤖 Bot account", callback_data="acct_bot")],
    ]
)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------


@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    if not is_authorized(message.from_user.id):
        await message.reply_text("This bot is private. You're not on the allowed list.")
        return

    name = message.from_user.first_name or "there"
    await message.reply_text(
        f"👋 Hey {name}, welcome to **Exon101 — Session Generator Bot**!\n\n"
        "I turn a quick chat into a ready-to-use session string for "
        "**Pyrogram v2** or **Telethon**, for a user or bot account — no "
        "local setup needed.\n\n"
        "**How it works:**\n"
        "1️⃣ Send /generate\n"
        "2️⃣ Pick a library and account type\n"
        "3️⃣ Share a phone number (or bot token)\n"
        "4️⃣ Enter the login code, and 2FA password if set\n"
        "5️⃣ Get your session string back, ready to copy\n\n"
        + WARNING_TEXT
        + "\nTap a button below or use /generate and /cancel anytime.",
        reply_markup=START_KEYBOARD,
    )


# ---------------------------------------------------------------------------
# Flow: generate / cancel entry points
# ---------------------------------------------------------------------------


async def begin_generate_flow(user_id: int, reply_text):
    """Starts a new flow by asking which library to use. reply_text is any
    async(str, **kwargs) -> Message sender, so a /generate command or an
    inline button can both call this."""
    if not is_authorized(user_id):
        await reply_text("This bot is private. You're not on the allowed list.")
        return

    if user_id in user_flows:
        await reply_text(
            "You already have a generation in progress. Send /cancel to abort it first."
        )
        return

    user_flows[user_id] = {"step": "choose_library", "last_active": time.time()}
    await reply_text(
        "Which client library do you need the session for?",
        reply_markup=LIBRARY_KEYBOARD,
    )


async def do_cancel(user_id: int, reply_text):
    if user_id in user_flows:
        await abort_flow(user_id)
        await reply_text("Cancelled. Nothing was saved.")
    else:
        await reply_text("Nothing in progress.")


@bot.on_message(filters.command("generate") & filters.private)
async def generate_handler(client, message: Message):
    await begin_generate_flow(message.from_user.id, message.reply_text)


@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_handler(client, message: Message):
    await do_cancel(message.from_user.id, message.reply_text)


@bot.on_callback_query(filters.regex("^start_generate$"))
async def generate_callback(client, callback_query: CallbackQuery):
    await callback_query.answer()
    await begin_generate_flow(callback_query.from_user.id, callback_query.message.reply_text)


@bot.on_callback_query(filters.regex("^start_cancel$"))
async def cancel_callback(client, callback_query: CallbackQuery):
    await callback_query.answer()
    await do_cancel(callback_query.from_user.id, callback_query.message.reply_text)


# ---------------------------------------------------------------------------
# Flow: library + account type selection
# ---------------------------------------------------------------------------


@bot.on_callback_query(filters.regex("^lib_(pyrogram|telethon)$"))
async def library_callback(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    flow = user_flows.get(user_id)
    if not flow or flow.get("step") != "choose_library":
        await callback_query.message.reply_text("Send /generate to start.")
        return

    library = callback_query.data.split("_", 1)[1]
    flow["library"] = library
    flow["last_active"] = time.time()

    backend = get_backend(library, API_ID, API_HASH, proxy=PROXY)
    try:
        await backend.connect()
    except ConfigError as e:
        await callback_query.message.reply_text(
            f"Server misconfiguration: {e} Contact the bot operator."
        )
        user_flows.pop(user_id, None)
        return

    flow["backend"] = backend
    flow["step"] = "choose_account_type"
    await callback_query.message.reply_text(
        f"Library: **{library.capitalize()}**. What are we generating a session for?",
        reply_markup=ACCOUNT_TYPE_KEYBOARD,
    )


@bot.on_callback_query(filters.regex("^acct_(user|bot)$"))
async def account_type_callback(client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    flow = user_flows.get(user_id)
    if not flow or flow.get("step") != "choose_account_type":
        await callback_query.message.reply_text("Send /generate to start.")
        return

    flow["last_active"] = time.time()
    account_type = callback_query.data.split("_", 1)[1]

    if account_type == "bot":
        flow["step"] = "bot_token"
        await callback_query.message.reply_text("Send the bot token from @BotFather.")
    else:
        flow["step"] = "phone"
        await callback_query.message.reply_text(
            "Send your phone number in international format, e.g. `+14155552671`.\n\n"
            + WARNING_TEXT
        )


# ---------------------------------------------------------------------------
# Flow: the actual login steps
# ---------------------------------------------------------------------------


@bot.on_message(filters.private & filters.text & ~filters.command(["start", "generate", "cancel"]))
async def flow_handler(client, message: Message):
    user_id = message.from_user.id
    flow = user_flows.get(user_id)
    if not flow or "backend" not in flow:
        await message.reply_text("Send /generate to start.")
        return

    flow["last_active"] = time.time()
    backend = flow["backend"]
    text = message.text.strip()
    step = flow["step"]

    try:
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    except Exception:
        pass

    try:
        if step == "bot_token":
            await run_with_status(
                message.reply_text,
                "Logging in with the bot token...",
                "Bot token accepted!",
                backend.start_as_bot(text),
            )
            await finish_flow(message, user_id, backend, flow)

        elif step == "phone":
            await run_with_status(
                message.reply_text,
                "Requesting a login code from Telegram...",
                "Code sent! Check your Telegram app.",
                backend.send_code(text),
            )
            flow["step"] = "code"
            await message.reply_text(
                "Send the login code here.\n\n"
                "⚠️ Telegram itself warns you not to share this code with anyone, "
                "including bots — only continue if you trust this bot's operator."
            )

        elif step == "code":
            try:
                await run_with_status(
                    message.reply_text,
                    "Verifying your login code...",
                    "Code verified!",
                    backend.sign_in_code(text),
                    benign_exceptions=(NeedsPassword,),
                )
                await finish_flow(message, user_id, backend, flow)
            except NeedsPassword:
                flow["step"] = "password"
                await message.reply_text(
                    "Two-step verification is enabled on this account. Send your 2FA password."
                )

        elif step == "password":
            await run_with_status(
                message.reply_text,
                "Verifying your 2FA password...",
                "Password verified!",
                backend.sign_in_password(text),
            )
            await finish_flow(message, user_id, backend, flow)

    except InvalidPhone:
        await message.reply_text(
            "That phone number looks invalid — include the country code, e.g. "
            "+14155552671. Try again or /cancel."
        )
    except InvalidCode:
        await message.reply_text("Wrong code. Try again or /cancel.")
    except ExpiredCode:
        await message.reply_text("That code expired. Send /cancel, then /generate to start over.")
    except InvalidPassword:
        await message.reply_text("Wrong password. Try again or /cancel.")
    except InvalidBotToken:
        await message.reply_text(
            "That bot token looks invalid or revoked — get a fresh one from "
            "@BotFather and /generate again."
        )
        await abort_flow(user_id)
    except RateLimited as e:
        await message.reply_text(
            f"Telegram is rate-limiting this. Wait {e.seconds} seconds, then /generate again."
        )
        await abort_flow(user_id)
    except (ConfigError, BackendError, SessionGenError) as e:
        await message.reply_text(f"Something went wrong: {e}\nSend /cancel and try again.")
        await abort_flow(user_id)


async def finish_flow(message: Message, user_id: int, backend, flow: dict):
    session_string = await run_with_status(
        message.reply_text,
        "Finalizing your session...",
        "Session ready!",
        backend.export_session_string(),
    )
    library = flow.get("library", "unknown")
    user_flows.pop(user_id, None)
    try:
        await backend.disconnect()
    except Exception:
        pass

    await message.reply_text(
        f"✅ **{library.capitalize()} session generated.**\n\n"
        f"`{session_string}`\n\n"
        "Nothing is stored on this server — copy it now. Treat it like a "
        "password: keep it in an env var or secret manager, never commit it "
        "to git, and never send it to anyone else."
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def main():
    await bot.start()
    asyncio.create_task(cleanup_loop())
    me = await bot.get_me()
    print(
        f"Bot started as @{me.username}. "
        f"Allowed users: {ALLOWED_USER_IDS or 'ANYONE (not restricted)'}"
    )
    await idle()
    await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
