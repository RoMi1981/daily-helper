"""TLS certificate generation for self-signed mode."""

import ipaddress
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
TLS_DIR = DATA_DIR / "tls"

CA_KEY_PATH = TLS_DIR / "ca.key"
CA_CERT_PATH = TLS_DIR / "ca.crt"
SERVER_KEY_PATH = TLS_DIR / "server.key"
SERVER_CERT_PATH = TLS_DIR / "server.crt"


def parse_sans(text: str) -> tuple[list[str], list[ipaddress.IPv4Address | ipaddress.IPv6Address]]:
    """Parse comma/newline-separated SAN text into (dns_names, ip_addresses)."""
    dns_names: list[str] = []
    ip_addresses = []
    for entry in text.replace(",", "\n").split("\n"):
        entry = entry.strip()
        if not entry:
            continue
        try:
            ip_addresses.append(ipaddress.ip_address(entry))
        except ValueError:
            dns_names.append(entry)
    return dns_names, ip_addresses


def _generate_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def generate_ca_and_server_cert(san_text: str) -> dict:
    """Generate CA + server cert from SAN text. Returns paths and expiry info."""
    TLS_DIR.mkdir(parents=True, exist_ok=True)

    dns_names, ip_addresses = parse_sans(san_text)
    cn = dns_names[0] if dns_names else (str(ip_addresses[0]) if ip_addresses else "localhost")

    now = datetime.now(timezone.utc)

    # ── CA ──────────────────────────────────────────
    ca_key = _generate_rsa_key()
    ca_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Daily Helper CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Daily Helper"),
    ])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    # ── Server cert ──────────────────────────────────
    server_key = _generate_rsa_key()
    san_entries: list[x509.GeneralName] = [x509.DNSName(d) for d in dns_names]
    san_entries += [x509.IPAddress(ip) for ip in ip_addresses]
    if not san_entries:
        san_entries = [x509.DNSName("localhost")]

    server_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    # ── Write files ──────────────────────────────────
    CA_KEY_PATH.write_bytes(ca_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    CA_CERT_PATH.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    SERVER_KEY_PATH.write_bytes(server_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    SERVER_CERT_PATH.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))

    for p in (CA_KEY_PATH, SERVER_KEY_PATH):
        p.chmod(0o600)

    expiry = (now + timedelta(days=365)).strftime("%Y-%m-%d")
    return {"cn": cn, "expiry": expiry, "sans": dns_names + [str(ip) for ip in ip_addresses]}


def get_ca_cert_pem() -> str:
    """Return CA cert PEM if it exists, else empty string."""
    return CA_CERT_PATH.read_text() if CA_CERT_PATH.exists() else ""


def get_cert_expiry() -> str:
    """Return server cert expiry date string, or empty string."""
    if not SERVER_CERT_PATH.exists():
        return ""
    cert = x509.load_pem_x509_certificate(SERVER_CERT_PATH.read_bytes())
    return cert.not_valid_after_utc.strftime("%Y-%m-%d")
