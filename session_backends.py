"""
session_backends.py
=====================

Shared authentication backend for the session-generator toolkit. Both
Pyrogram and Telethon speak MTProto but have different Python APIs and
different exception classes for the same underlying errors ("wrong code",
"needs 2FA password", "rate limited", etc).

This module normalizes both libraries behind one small interface
(`AuthBackend`) with one set of exceptions (`SessionGenError` and its
subclasses), so the CLI script, the validator, and the Telegram bot can
all drive either library through identical calling code. Add a feature
here once and every entry point gets it for both libraries.

Nothing in this module writes anything to disk, logs, or any network
endpoint other than Telegram's own API.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Normalized exceptions
# ---------------------------------------------------------------------------
# Every backend method below catches its own library's specific exceptions
# and re-raises one of these, so calling code never needs to know which
# library is underneath.


class SessionGenError(Exception):
    """Base class for every normalized error this module raises."""


class ConfigError(SessionGenError):
    """api_id / api_hash / library misconfiguration, or a missing dependency."""


class InvalidPhone(SessionGenError):
    """The phone number was rejected by Telegram."""


class InvalidCode(SessionGenError):
    """The login code was wrong."""


class ExpiredCode(SessionGenError):
    """The login code expired before it was used."""


class NeedsPassword(SessionGenError):
    """The code was correct, but the account has 2FA enabled."""


class InvalidPassword(SessionGenError):
    """The 2FA password was wrong."""


class InvalidBotToken(SessionGenError):
    """The bot token was wrong, mistyped, or revoked."""


class RateLimited(SessionGenError):
    """Telegram is flood-waiting this operation."""

    def __init__(self, seconds: int):
        self.seconds = seconds
        super().__init__(f"Rate limited for {seconds}s")


class BackendError(SessionGenError):
    """Any other backend-specific error, wrapped with its original message."""


# ---------------------------------------------------------------------------
# Shared value types
# ---------------------------------------------------------------------------


@dataclass
class AccountInfo:
    first_name: str
    last_name: str | None
    username: str | None
    user_id: int
    is_bot: bool
    phone: str | None


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------


def parse_proxy(proxy_url: str) -> dict:
    """
    Parses "socks5://[user:pass@]host:port" (or socks4/http) into the dict
    shape both backends expect: {scheme, hostname, port, username, password}.
    """
    parsed = urlparse(proxy_url)
    if not parsed.scheme or not parsed.hostname or not parsed.port:
        raise ValueError("Proxy URL must look like socks5://[user:pass@]host:port")
    return {
        "scheme": parsed.scheme,
        "hostname": parsed.hostname,
        "port": parsed.port,
        "username": parsed.username,
        "password": parsed.password,
    }


def mask_session_string(session_string: str, visible: int = 6) -> str:
    """
    Returns a partially redacted session string — safe to show on a screen
    share or in a screenshot while still confirming its shape/length,
    without exposing enough of it to be usable.
    """
    if len(session_string) <= visible * 2:
        return "*" * len(session_string)
    middle = "*" * (len(session_string) - visible * 2)
    return f"{session_string[:visible]}{middle}{session_string[-visible:]}"


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------


class AuthBackend:
    """Common interface implemented by PyrogramBackend and TelethonBackend."""

    library: str = "base"

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        *,
        proxy: dict | None = None,
        session_string: str | None = None,
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.proxy = proxy
        self.session_string = session_string
        self._phone: str | None = None
        self._phone_code_hash: str | None = None

    async def connect(self):
        raise NotImplementedError

    async def disconnect(self):
        raise NotImplementedError

    async def send_code(self, phone: str):
        raise NotImplementedError

    async def sign_in_code(self, code: str):
        raise NotImplementedError

    async def sign_in_password(self, password: str):
        raise NotImplementedError

    async def start_as_bot(self, bot_token: str):
        raise NotImplementedError

    async def export_session_string(self) -> str:
        raise NotImplementedError

    async def get_me(self) -> AccountInfo:
        raise NotImplementedError

    async def count_chats(self, limit: int = 50) -> int:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Pyrogram backend
# ---------------------------------------------------------------------------


class PyrogramBackend(AuthBackend):
    library = "pyrogram"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from pyrogram import Client
        except ImportError as e:
            raise ConfigError(
                "Pyrogram is not installed. Run: pip install pyrogram tgcrypto"
            ) from e
        self._Client = Client
        self._client = self._build_client(bot_token=None)

    def _build_client(self, bot_token: str | None):
        proxy_kwargs = {"proxy": self.proxy} if self.proxy else {}
        kwargs = dict(api_id=self.api_id, api_hash=self.api_hash, in_memory=True, **proxy_kwargs)
        if self.session_string:
            kwargs["session_string"] = self.session_string
            name = "pyrogram_validator"
        elif bot_token:
            kwargs["bot_token"] = bot_token
            name = "pyrogram_gen_bot"
        else:
            name = "pyrogram_gen_user"
        return self._Client(name, **kwargs)

    async def connect(self):
        from pyrogram.errors import ApiIdInvalid

        try:
            await self._client.connect()
        except ApiIdInvalid as e:
            raise ConfigError("api_id/api_hash is invalid.") from e

    async def disconnect(self):
        try:
            await self._client.disconnect()
        except Exception:
            pass

    async def send_code(self, phone: str):
        from pyrogram.errors import FloodWait, PhoneNumberInvalid, RPCError

        self._phone = phone
        try:
            sent = await self._client.send_code(phone)
            self._phone_code_hash = sent.phone_code_hash
        except PhoneNumberInvalid as e:
            raise InvalidPhone(str(e)) from e
        except FloodWait as e:
            raise RateLimited(e.value) from e
        except RPCError as e:
            raise BackendError(str(e)) from e

    async def sign_in_code(self, code: str):
        from pyrogram.errors import (
            FloodWait,
            PhoneCodeExpired,
            PhoneCodeInvalid,
            RPCError,
            SessionPasswordNeeded,
        )

        try:
            await self._client.sign_in(self._phone, self._phone_code_hash, code)
        except SessionPasswordNeeded as e:
            raise NeedsPassword() from e
        except PhoneCodeInvalid as e:
            raise InvalidCode(str(e)) from e
        except PhoneCodeExpired as e:
            raise ExpiredCode(str(e)) from e
        except FloodWait as e:
            raise RateLimited(e.value) from e
        except RPCError as e:
            raise BackendError(str(e)) from e

    async def sign_in_password(self, password: str):
        from pyrogram.errors import FloodWait, PasswordHashInvalid, RPCError

        try:
            await self._client.check_password(password)
        except PasswordHashInvalid as e:
            raise InvalidPassword(str(e)) from e
        except FloodWait as e:
            raise RateLimited(e.value) from e
        except RPCError as e:
            raise BackendError(str(e)) from e

    async def start_as_bot(self, bot_token: str):
        from pyrogram.errors import AccessTokenInvalid

        try:
            await self._client.disconnect()
        except Exception:
            pass
        self._client = self._build_client(bot_token=bot_token)
        try:
            await self._client.connect()
            await self._client.sign_in_bot(bot_token)
        except AccessTokenInvalid as e:
            raise InvalidBotToken(str(e)) from e
        except Exception as e:
            raise BackendError(str(e)) from e

    async def export_session_string(self) -> str:
        return await self._client.export_session_string()

    async def get_me(self) -> AccountInfo:
        me = await self._client.get_me()
        return AccountInfo(
            first_name=me.first_name or "",
            last_name=me.last_name,
            username=me.username,
            user_id=me.id,
            is_bot=bool(me.is_bot),
            phone=getattr(me, "phone_number", None),
        )

    async def count_chats(self, limit: int = 50) -> int:
        count = 0
        async for _ in self._client.get_dialogs(limit=limit):
            count += 1
        return count


# ---------------------------------------------------------------------------
# Telethon backend
# ---------------------------------------------------------------------------


class TelethonBackend(AuthBackend):
    library = "telethon"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
        except ImportError as e:
            raise ConfigError(
                "Telethon is not installed. Run: pip install telethon python-socks"
            ) from e
        proxy = self._convert_proxy(self.proxy) if self.proxy else None
        session = StringSession(self.session_string) if self.session_string else StringSession()
        self._client = TelegramClient(session, self.api_id, self.api_hash, proxy=proxy)

    @staticmethod
    def _convert_proxy(proxy: dict):
        # Telethon (via python-socks) expects (proxy_type, host, port, rdns, user, pass).
        scheme_map = {"socks5": 2, "socks4": 1, "http": 3}
        return (
            scheme_map.get(proxy.get("scheme", "socks5"), 2),
            proxy["hostname"],
            proxy["port"],
            True,
            proxy.get("username"),
            proxy.get("password"),
        )

    async def connect(self):
        from telethon.errors import ApiIdInvalidError

        try:
            await self._client.connect()
        except ApiIdInvalidError as e:
            raise ConfigError("api_id/api_hash is invalid.") from e

    async def disconnect(self):
        try:
            await self._client.disconnect()
        except Exception:
            pass

    async def send_code(self, phone: str):
        from telethon.errors import FloodWaitError, PhoneNumberInvalidError

        self._phone = phone
        try:
            sent = await self._client.send_code_request(phone)
            self._phone_code_hash = sent.phone_code_hash
        except PhoneNumberInvalidError as e:
            raise InvalidPhone(str(e)) from e
        except FloodWaitError as e:
            raise RateLimited(e.seconds) from e
        except Exception as e:
            raise BackendError(str(e)) from e

    async def sign_in_code(self, code: str):
        from telethon.errors import (
            FloodWaitError,
            PhoneCodeExpiredError,
            PhoneCodeInvalidError,
            SessionPasswordNeededError,
        )

        try:
            await self._client.sign_in(self._phone, code, phone_code_hash=self._phone_code_hash)
        except SessionPasswordNeededError as e:
            raise NeedsPassword() from e
        except PhoneCodeInvalidError as e:
            raise InvalidCode(str(e)) from e
        except PhoneCodeExpiredError as e:
            raise ExpiredCode(str(e)) from e
        except FloodWaitError as e:
            raise RateLimited(e.seconds) from e
        except Exception as e:
            raise BackendError(str(e)) from e

    async def sign_in_password(self, password: str):
        from telethon.errors import FloodWaitError, PasswordHashInvalidError

        try:
            await self._client.sign_in(password=password)
        except PasswordHashInvalidError as e:
            raise InvalidPassword(str(e)) from e
        except FloodWaitError as e:
            raise RateLimited(e.seconds) from e
        except Exception as e:
            raise BackendError(str(e)) from e

    async def start_as_bot(self, bot_token: str):
        from telethon.errors import AccessTokenInvalidError

        try:
            await self._client.sign_in(bot_token=bot_token)
        except AccessTokenInvalidError as e:
            raise InvalidBotToken(str(e)) from e
        except Exception as e:
            raise BackendError(str(e)) from e

    async def export_session_string(self) -> str:
        return self._client.session.save()

    async def get_me(self) -> AccountInfo:
        me = await self._client.get_me()
        return AccountInfo(
            first_name=me.first_name or "",
            last_name=me.last_name,
            username=me.username,
            user_id=me.id,
            is_bot=bool(getattr(me, "bot", False)),
            phone=getattr(me, "phone", None),
        )

    async def count_chats(self, limit: int = 50) -> int:
        count = 0
        async for _ in self._client.iter_dialogs(limit=limit):
            count += 1
        return count


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_backend(
    library: str,
    api_id: int,
    api_hash: str,
    *,
    proxy: dict | None = None,
    session_string: str | None = None,
) -> AuthBackend:
    library = library.lower().strip()
    if library == "pyrogram":
        return PyrogramBackend(api_id, api_hash, proxy=proxy, session_string=session_string)
    if library == "telethon":
        return TelethonBackend(api_id, api_hash, proxy=proxy, session_string=session_string)
    raise ValueError(f"Unknown library {library!r} (expected 'pyrogram' or 'telethon')")
