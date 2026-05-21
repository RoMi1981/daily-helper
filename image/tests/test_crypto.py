"""Tests for core/crypto.py — password-based export encryption."""

import json
import os
import sys

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

import pytest
from core.crypto import encrypt_export, decrypt_export, is_encrypted


def test_encrypt_returns_bytes():
    result = encrypt_export('{"key": "value"}', "mypassword")
    assert isinstance(result, bytes)
    assert result.startswith(b"DHBK")


def test_is_encrypted_true():
    data = encrypt_export('{"x": 1}', "pw")
    assert is_encrypted(data) is True


def test_is_encrypted_false_for_json():
    assert is_encrypted(b'{"key": "value"}') is False


def test_is_encrypted_false_for_random():
    assert is_encrypted(b"\x00\x01\x02\x03") is False


def test_roundtrip():
    payload = json.dumps({"repos": [], "setting": "value", "nested": {"a": 1}})
    encrypted = encrypt_export(payload, "secret123")
    decrypted = decrypt_export(encrypted, "secret123")
    assert json.loads(decrypted) == json.loads(payload)


def test_wrong_password_raises():
    encrypted = encrypt_export('{"x": 1}', "correct")
    with pytest.raises(ValueError, match="[Ww]rong password"):
        decrypt_export(encrypted, "wrong")


def test_corrupted_data_raises():
    encrypted = bytearray(encrypt_export('{"x": 1}', "pw"))
    encrypted[20] ^= 0xFF  # flip a byte in the token
    with pytest.raises(ValueError):
        decrypt_export(bytes(encrypted), "pw")


def test_bad_magic_raises():
    with pytest.raises(ValueError, match="Not an encrypted"):
        decrypt_export(b'{"plain": "json"}', "pw")


def test_each_export_has_unique_salt():
    """Two exports with the same password produce different ciphertext."""
    a = encrypt_export('{"x": 1}', "pw")
    b = encrypt_export('{"x": 1}', "pw")
    assert a != b
    # But both decrypt correctly
    assert decrypt_export(a, "pw") == decrypt_export(b, "pw")


def test_empty_json():
    payload = "{}"
    assert json.loads(decrypt_export(encrypt_export(payload, "pw"), "pw")) == {}


def test_unicode_content():
    payload = json.dumps({"name": "Ärger mit Ö", "emoji": "🔑"})
    assert decrypt_export(encrypt_export(payload, "pw"), "pw") == payload
