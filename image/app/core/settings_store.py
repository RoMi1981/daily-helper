"""Persistent settings with Fernet encryption for sensitive fields."""

import base64
import copy
import json
import os
import uuid
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
SETTINGS_PATH = DATA_DIR / "settings.json"
KEY_PATH = DATA_DIR / ".secret_key"

ENCRYPTED_FIELDS = {"ssh_key", "pat", "ca_cert", "basic_password", "gpg_key", "gpg_passphrase"}
TOP_LEVEL_ENCRYPTED_FIELDS = {"tls_custom_crt", "tls_custom_key"}
ENC_PREFIX = "enc:"

DEFAULTS: dict = {
    "repos": [],
    "templates": [],
    "ics_profiles": [],
    "appointment_ics_profiles": [],
    "holiday_ics_profiles": [],
    "git_user_name": "Daily Helper",
    "git_user_email": "daily@helper.local",
    "tls_mode": "http",
    "tls_san": "localhost, 127.0.0.1",
    "tls_custom_crt": "",
    "tls_custom_key": "",
    "metrics_enabled": False,
    "modules_enabled": {
        "knowledge": True,
        "tasks": True,
        "vacations": True,
        "mail_templates": True,
        "ticket_templates": True,
        "notes": True,
        "links": True,
        "runbooks": True,
        "appointments": True,
        "snippets": True,
        "motd": True,
        "potd": True,
        "memes": True,
        "rss": True,
    },
    "module_repos": {
        "knowledge": {"repos": [], "primary": ""},
        "tasks": {"repos": [], "primary": ""},
        "vacations": {"repos": [], "primary": ""},
        "mail_templates": {"repos": [], "primary": ""},
        "ticket_templates": {"repos": [], "primary": ""},
        "notes": {"repos": [], "primary": ""},
        "links": {"repos": [], "primary": ""},
        "runbooks": {"repos": [], "primary": ""},
        "appointments": {"repos": [], "primary": ""},
        "snippets": {"repos": [], "primary": ""},
        "motd": {"repos": [], "primary": ""},
        "potd": {"repos": [], "primary": ""},
        "memes": {"repos": [], "primary": ""},
        "rss": {"repos": [], "primary": ""},
    },
    "notes_scroll_position": "end",
    "notes_line_numbers": False,
    "vacation_state": "BY",
    "vacation_days_per_year": 30,
    "vacation_carryover": 0,
    "holiday_language": "de",
    "vacation_mail_to": "",
    "vacation_mail_cc": "",
    "vacation_mail_subject": "",
    "vacation_mail_body": "",
    "link_sections": [],
    "calendar_show_weekends": True,
    "sprint_anchor_date": "",
    "sprint_name_prefix": "PFM Sprint",
    "sprint_duration_weeks": 3,
    "sprint_blocked_appointment_types": ["training", "conference", "business_trip"],
    "theme_mode": "auto",
    "language": "en",
    "cache_max_file_mb": 10,
    "rss_home_limit": 3,
}

REPO_DEFAULTS: dict = {
    "id": "",
    "name": "",
    "url": "",
    "platform": "gitea",
    "auth_mode": "none",
    "enabled": True,
    "ssh_key": "",
    "pat": "",
    "ca_cert": "",
    "basic_user": "",
    "basic_password": "",
    "gpg_key": "",
    "gpg_passphrase": "",
    "git_user_name": "",
    "git_user_email": "",
    "permissions": {"read": False, "write": False},
    "last_checked": "",
    "push_retry_count": 1,
}


def get_fernet() -> Fernet:
    return _get_fernet()


def encrypt_value(value: str) -> str:
    return _encrypt(value, _get_fernet())


def decrypt_value(value: str) -> str:
    return _decrypt(value, _get_fernet())


def _get_fernet() -> Fernet:
    raw_key = os.environ.get("SECRET_KEY", "").strip()
    if raw_key:
        return Fernet(raw_key.encode())

    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if KEY_PATH.exists():
        return Fernet(KEY_PATH.read_bytes().strip())

    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    KEY_PATH.chmod(0o600)
    return Fernet(key)


def _encrypt(value: str, f: Fernet) -> str:
    if not value:
        return ""
    return ENC_PREFIX + f.encrypt(value.encode()).decode()


def _decrypt(value: str, f: Fernet) -> str:
    if not value or not value.startswith(ENC_PREFIX):
        return value
    return f.decrypt(value[len(ENC_PREFIX) :].encode()).decode()


def _decrypt_repo(repo: dict, f: Fernet) -> dict:
    r = dict(repo)
    for field in ENCRYPTED_FIELDS:
        r[field] = _decrypt(r.get(field, ""), f)
    return r


def _decrypt_link_section(section: dict, f: Fernet) -> dict:
    s = dict(section)
    s["floccus_password"] = _decrypt(s.get("floccus_password", ""), f)
    return s


def _encrypt_link_section(section: dict, f: Fernet) -> dict:
    s = dict(section)
    val = s.get("floccus_password", "")
    s["floccus_password"] = _encrypt(val, f) if val else ""
    return s


def _encrypt_repo(repo: dict, f: Fernet) -> dict:
    r = dict(repo)
    for field in ENCRYPTED_FIELDS:
        val = r.get(field, "")
        r[field] = _encrypt(val, f) if val else ""
    return r


def _migrate_legacy(raw: dict) -> dict:
    """Migrate old single-repo format to new repos-list format."""
    if "repos" in raw:
        return raw
    # Old format has repo_url at top level
    repo_url = raw.get("repo_url", "")
    repo: dict = dict(REPO_DEFAULTS)
    repo.update(
        {
            "id": _new_id(),
            "name": "Main",
            "url": repo_url,
            "platform": "gitea",
            "auth_mode": raw.get("auth_mode", "none"),
            "ssh_key": raw.get("ssh_key", ""),
            "pat": raw.get("pat", ""),
            "ca_cert": raw.get("ca_cert", ""),
            "permissions": {"read": bool(repo_url), "write": bool(repo_url)},
        }
    )
    return {
        "repos": [repo] if repo_url else [],
        "git_user_name": raw.get("git_user_name", DEFAULTS["git_user_name"]),
        "git_user_email": raw.get("git_user_email", DEFAULTS["git_user_email"]),
    }


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def load() -> dict:
    f = _get_fernet()
    if not SETTINGS_PATH.exists():
        return copy.deepcopy(DEFAULTS)
    raw = json.loads(SETTINGS_PATH.read_text())
    raw = _migrate_legacy(raw)
    result = copy.deepcopy(DEFAULTS)
    result.update(raw)
    result["repos"] = [_decrypt_repo(r, f) for r in result.get("repos", [])]
    result["link_sections"] = [_decrypt_link_section(s, f) for s in result.get("link_sections", [])]
    for field in TOP_LEVEL_ENCRYPTED_FIELDS:
        result[field] = _decrypt(result.get(field, ""), f)
    return result


def save(data: dict) -> None:
    f = _get_fernet()
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    to_store = dict(data)
    to_store["repos"] = [_encrypt_repo(r, f) for r in to_store.get("repos", [])]
    to_store["link_sections"] = [
        _encrypt_link_section(s, f) for s in to_store.get("link_sections", [])
    ]
    for field in TOP_LEVEL_ENCRYPTED_FIELDS:
        val = to_store.get(field, "")
        to_store[field] = _encrypt(val, f) if val else ""
    SETTINGS_PATH.write_text(json.dumps(to_store, indent=2, ensure_ascii=False))
    SETTINGS_PATH.chmod(0o600)


def get_repo(repo_id: str) -> dict | None:
    cfg = load()
    for repo in cfg.get("repos", []):
        if repo["id"] == repo_id:
            return repo
    return None


def upsert_repo(repo: dict) -> dict:
    """Add or update a repo. Assigns id if missing. Returns updated repo."""
    cfg = load()
    if not repo.get("id"):
        repo["id"] = _new_id()
    repos = cfg.get("repos", [])
    for i, r in enumerate(repos):
        if r["id"] == repo["id"]:
            repos[i] = repo
            break
    else:
        repos.append(repo)
    cfg["repos"] = repos
    save(cfg)
    return repo


def delete_repo(repo_id: str) -> bool:
    cfg = load()
    repos = cfg.get("repos", [])
    new_repos = [r for r in repos if r["id"] != repo_id]
    if len(new_repos) == len(repos):
        return False
    cfg["repos"] = new_repos
    save(cfg)
    return True


def update_permissions(repo_id: str, permissions: dict) -> None:
    from datetime import datetime

    cfg = load()
    for repo in cfg.get("repos", []):
        if repo["id"] == repo_id:
            repo["permissions"] = permissions
            repo["last_checked"] = datetime.now().isoformat(timespec="seconds")
            break
    save(cfg)


def get_templates() -> list[dict]:
    return load().get("templates", [])


def upsert_template(template: dict) -> dict:
    cfg = load()
    if not template.get("id"):
        template["id"] = _new_id()
    templates = cfg.get("templates", [])
    for i, t in enumerate(templates):
        if t["id"] == template["id"]:
            templates[i] = template
            break
    else:
        templates.append(template)
    cfg["templates"] = templates
    save(cfg)
    return template


def delete_template(template_id: str) -> bool:
    cfg = load()
    templates = cfg.get("templates", [])
    new_templates = [t for t in templates if t["id"] != template_id]
    if len(new_templates) == len(templates):
        return False
    cfg["templates"] = new_templates
    save(cfg)
    return True


def get_ics_profiles() -> list[dict]:
    return load().get("ics_profiles", [])


def get_ics_profile(profile_id: str) -> dict | None:
    for p in get_ics_profiles():
        if p.get("id") == profile_id:
            return p
    return None


def upsert_ics_profile(profile: dict) -> dict:
    cfg = load()
    if not profile.get("id"):
        profile["id"] = _new_id()
    profiles = cfg.get("ics_profiles", [])
    for i, p in enumerate(profiles):
        if p["id"] == profile["id"]:
            profiles[i] = profile
            break
    else:
        profiles.append(profile)
    cfg["ics_profiles"] = profiles
    save(cfg)
    return profile


def delete_ics_profile(profile_id: str) -> bool:
    cfg = load()
    profiles = cfg.get("ics_profiles", [])
    new_profiles = [p for p in profiles if p["id"] != profile_id]
    if len(new_profiles) == len(profiles):
        return False
    cfg["ics_profiles"] = new_profiles
    save(cfg)
    return True


def get_appointment_ics_profiles() -> list[dict]:
    return load().get("appointment_ics_profiles", [])


def get_appointment_ics_profile(profile_id: str) -> dict | None:
    for p in get_appointment_ics_profiles():
        if p.get("id") == profile_id:
            return p
    return None


def upsert_appointment_ics_profile(profile: dict) -> dict:
    cfg = load()
    if not profile.get("id"):
        profile["id"] = _new_id()
    profiles = cfg.get("appointment_ics_profiles", [])
    for i, p in enumerate(profiles):
        if p["id"] == profile["id"]:
            profiles[i] = profile
            break
    else:
        profiles.append(profile)
    cfg["appointment_ics_profiles"] = profiles
    save(cfg)
    return profile


def delete_appointment_ics_profile(profile_id: str) -> bool:
    cfg = load()
    profiles = cfg.get("appointment_ics_profiles", [])
    new_profiles = [p for p in profiles if p["id"] != profile_id]
    if len(new_profiles) == len(profiles):
        return False
    cfg["appointment_ics_profiles"] = new_profiles
    save(cfg)
    return True


def get_holiday_ics_profiles() -> list[dict]:
    return load().get("holiday_ics_profiles", [])


def get_holiday_ics_profile(profile_id: str) -> dict | None:
    for p in get_holiday_ics_profiles():
        if p.get("id") == profile_id:
            return p
    return None


def upsert_holiday_ics_profile(profile: dict) -> dict:
    import uuid as _uuid

    cfg = load()
    profiles = cfg.get("holiday_ics_profiles", [])
    if not profile.get("id"):
        profile["id"] = _uuid.uuid4().hex[:8]
    for i, p in enumerate(profiles):
        if p.get("id") == profile["id"]:
            profiles[i] = profile
            cfg["holiday_ics_profiles"] = profiles
            save(cfg)
            return profile
    profiles.append(profile)
    cfg["holiday_ics_profiles"] = profiles
    save(cfg)
    return profile


def delete_holiday_ics_profile(profile_id: str) -> bool:
    cfg = load()
    profiles = cfg.get("holiday_ics_profiles", [])
    new_profiles = [p for p in profiles if p["id"] != profile_id]
    if len(new_profiles) == len(profiles):
        return False
    cfg["holiday_ics_profiles"] = new_profiles
    save(cfg)
    return True


def get_module_repos(module: str) -> dict:
    """Return {"repos": [...], "primary": "..."} for a module."""
    return load().get("module_repos", {}).get(module, {"repos": [], "primary": ""})


def set_module_repos(module_repos: dict) -> None:
    """Save module→repo assignments. module_repos: {module: {"repos": [...], "primary": "..."}}"""
    cfg = load()
    existing = cfg.get("module_repos", {})
    existing.update(module_repos)
    cfg["module_repos"] = existing
    save(cfg)


def is_module_enabled(module: str) -> bool:
    return load().get("modules_enabled", {}).get(module, True)


def set_modules_enabled(enabled: dict[str, bool]) -> None:
    cfg = load()
    current = cfg.get(
        "modules_enabled",
        {
            "knowledge": True,
            "tasks": True,
            "vacations": True,
            "mail_templates": True,
            "ticket_templates": True,
        },
    )
    current.update(enabled)
    cfg["modules_enabled"] = current
    save(cfg)


def toggle_repo_enabled(repo_id: str) -> bool | None:
    """Toggle enabled flag on a repo. Returns new state or None if not found."""
    cfg = load()
    for repo in cfg.get("repos", []):
        if repo["id"] == repo_id:
            repo["enabled"] = not repo.get("enabled", True)
            save(cfg)
            return repo["enabled"]
    return None


def generate_new_key() -> str:
    return Fernet.generate_key().decode()


def generate_ssh_keypair() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_openssh = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )
        .decode()
    )
    return private_pem, public_openssh


def get_link_sections() -> list[dict]:
    return load().get("link_sections", [])


def upsert_link_section(section: dict) -> dict:
    cfg = load()
    if not section.get("id"):
        section["id"] = _new_id()
    sections = cfg.get("link_sections", [])
    for i, s in enumerate(sections):
        if s["id"] == section["id"]:
            sections[i] = section
            break
    else:
        sections.append(section)
    cfg["link_sections"] = sections
    save(cfg)
    return section


def delete_link_section(section_id: str) -> bool:
    cfg = load()
    sections = cfg.get("link_sections", [])
    new_sections = [s for s in sections if s["id"] != section_id]
    if len(new_sections) == len(sections):
        return False
    cfg["link_sections"] = new_sections
    save(cfg)
    return True


def derive_public_key(private_key_pem: str) -> str:
    if not private_key_pem.strip():
        return ""
    try:
        private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
        return (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.OpenSSH,
                format=serialization.PublicFormat.OpenSSH,
            )
            .decode()
        )
    except Exception:
        return ""
