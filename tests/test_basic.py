"""
Lightweight, network-free sanity checks: no real Telegram credentials are
required to run this suite. It checks the pure-Python helpers in
session_backends.py and confirms every script still parses/compiles.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from session_backends import get_backend, mask_session_string, parse_proxy


def test_mask_session_string_short_input_fully_redacted():
    assert mask_session_string("abc") == "***"


def test_mask_session_string_keeps_shape_and_edges():
    s = "A" * 30
    masked = mask_session_string(s, visible=4)
    assert masked.startswith("AAAA")
    assert masked.endswith("AAAA")
    assert "*" in masked
    assert len(masked) == len(s)


def test_parse_proxy_valid_socks5_url():
    proxy = parse_proxy("socks5://user:pass@1.2.3.4:1080")
    assert proxy == {
        "scheme": "socks5",
        "hostname": "1.2.3.4",
        "port": 1080,
        "username": "user",
        "password": "pass",
    }


def test_parse_proxy_rejects_garbage():
    with pytest.raises(ValueError):
        parse_proxy("not-a-proxy-url")


def test_get_backend_rejects_unknown_library():
    with pytest.raises(ValueError):
        get_backend("not-a-real-library", 123, "hash")


def test_get_backend_accepts_known_libraries():
    # Construction only — no network connect() here, so no real
    # credentials are needed for this check.
    pyrogram_backend = get_backend("pyrogram", 123, "hash")
    telethon_backend = get_backend("telethon", 123, "hash")
    assert pyrogram_backend.library == "pyrogram"
    assert telethon_backend.library == "telethon"


@pytest.mark.parametrize(
    "script",
    [
        "session_backends.py",
        "generate_session.py",
        "validate_session.py",
        "telegram_session_bot.py",
    ],
)
def test_script_compiles(script):
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(repo_root, script)
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", path],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
