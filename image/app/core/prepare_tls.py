"""Called by entrypoint.sh before starting uvicorn.
Decrypts and writes TLS files to /data/tls/, prints the active TLS mode to stdout.
"""

import json
import os
import sys
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
SETTINGS = DATA_DIR / "settings.json"
TLS_DIR = DATA_DIR / "tls"
KEY_PATH = DATA_DIR / ".secret_key"

ENC_PREFIX = "enc:"


def _get_fernet():
    from cryptography.fernet import Fernet
    raw = os.environ.get("SECRET_KEY", "").strip()
    if raw:
        return Fernet(raw.encode())
    if KEY_PATH.exists():
        return Fernet(KEY_PATH.read_bytes().strip())
    return None


def _decrypt(value: str, f) -> str:
    if not value or not value.startswith(ENC_PREFIX) or f is None:
        return value
    return f.decrypt(value[len(ENC_PREFIX):].encode()).decode()


def main():
    TLS_DIR.mkdir(parents=True, exist_ok=True)

    if not SETTINGS.exists():
        print("http")
        return

    try:
        raw = json.loads(SETTINGS.read_text())
    except Exception:
        print("http")
        return

    mode = raw.get("tls_mode", "http")

    if mode == "selfsigned":
        if not (TLS_DIR / "server.crt").exists():
            # Cert not generated yet — fall back to http
            print("http")
        else:
            print("selfsigned")

    elif mode == "custom":
        f = _get_fernet()
        crt = _decrypt(raw.get("tls_custom_crt", ""), f)
        key = _decrypt(raw.get("tls_custom_key", ""), f)
        if crt.strip() and key.strip():
            crt_path = TLS_DIR / "custom.crt"
            key_path = TLS_DIR / "custom.key"
            crt_path.write_text(crt)
            key_path.write_text(key)
            key_path.chmod(0o600)
            print("custom")
        else:
            print("http")

    else:
        print("http")


main()
