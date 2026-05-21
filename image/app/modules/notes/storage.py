"""Notes storage — YAML files in notes/ subdirectory."""

import logging
import uuid
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class NoteStorage:
    """Manages notes/{id}.yaml files inside the data git repo."""

    def __init__(self, git_storage):
        self._git = git_storage
        self._dir = Path(git_storage.local_path) / "notes"

    def _path(self, note_id: str) -> Path:
        return self._dir / f"{note_id}.yaml"

    def _decrypt_body(self, note: dict) -> dict:
        """Return note with body decrypted if encrypted flag is set."""
        if note.get("encrypted") and note.get("body", "").startswith("enc:"):
            try:
                from core import settings_store

                note = dict(note)
                note["body"] = settings_store.decrypt_value(note["body"])
            except Exception as e:
                logger.warning("Failed to decrypt note body %s: %s", note.get("id"), e)
        return note

    def _read(self, path: Path) -> dict | None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Failed to read note %s: %s", path, e)
            return None

    def _write(self, note: dict):
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(note["id"]).write_text(
            yaml.dump(note, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def list_notes(self, query: str = "") -> list[dict]:
        items = []
        q = query.strip().lower()
        for name in self._git.list_committed("notes"):
            if not name.endswith(".yaml"):
                continue
            raw = self._git.read_committed(f"notes/{name}")
            if raw is None:
                continue
            n = yaml.safe_load(raw.decode("utf-8"))
            if not isinstance(n, dict):
                continue
            if q:
                n_dec = self._decrypt_body(n)
                if (
                    q not in n_dec.get("subject", "").lower()
                    and q not in n_dec.get("body", "").lower()
                ):
                    continue
            items.append(n)
        return sorted(items, key=lambda x: x.get("updated", x.get("created", "")), reverse=True)

    def get_note(self, note_id: str) -> dict | None:
        raw = self._git.read_committed(f"notes/{note_id}.yaml")
        if raw is None:
            return None
        data = yaml.safe_load(raw.decode("utf-8"))
        if not isinstance(data, dict):
            return None
        note = self._decrypt_body(data)
        if isinstance(note.get("body"), str):
            note["body"] = note["body"].replace("\r\n", "\n").replace("\r", "\n")
        return note

    def create_note(self, data: dict) -> dict:
        today = date.today().isoformat()
        body = data.get("body", "")
        encrypt = bool(data.get("encrypt", False))
        if encrypt and body:
            from core import settings_store

            body = settings_store.encrypt_value(body)
        note = {
            "id": _new_id(),
            "subject": data.get("subject", "").strip(),
            "body": body,
            "created": today,
            "updated": today,
        }
        if encrypt:
            note["encrypted"] = True
        self._git._pull()
        self._write(note)
        self._git._commit_and_push(f"notes: add '{note['subject']}'")
        return note

    def update_note(self, note_id: str, data: dict) -> dict | None:
        # Read raw (without decryption) to preserve existing encrypted state
        raw = self._git.read_committed(f"notes/{note_id}.yaml")
        if raw is None:
            return None
        note = yaml.safe_load(raw.decode("utf-8"))
        if not isinstance(note, dict):
            return None

        body = data.get("body", note.get("body", ""))
        encrypt = bool(data.get("encrypt", False))

        if encrypt and body:
            from core import settings_store

            body = settings_store.encrypt_value(body)
        elif not encrypt:
            # Remove encryption — body is already plaintext from form
            note.pop("encrypted", None)

        note.update(
            {
                "subject": data.get("subject", note["subject"]).strip(),
                "body": body,
                "updated": date.today().isoformat(),
            }
        )
        if encrypt:
            note["encrypted"] = True

        self._git._pull()
        self._write(note)
        self._git._commit_and_push(f"notes: update '{note['subject']}'")
        return self._decrypt_body(note)

    def delete_note(self, note_id: str) -> bool:
        note = self.get_note(note_id)
        if note is None:
            return False
        subject = note.get("subject", note_id)
        self._git._pull()
        p = self._path(note_id)
        if not p.exists():
            return False
        p.unlink()
        self._git._commit_and_push(f"notes: delete '{subject}'")
        return True

    def bulk_delete_notes(self, note_ids: list[str]) -> int:
        if not note_ids:
            return 0
        self._git._pull()
        deleted = 0
        for nid in note_ids:
            p = self._path(nid)
            if p.exists():
                p.unlink()
                deleted += 1
        if deleted:
            self._git._commit_and_push(f"notes: bulk delete {deleted} note(s)")
        return deleted

    # ── Archive ────────────────────────────────────────────────────────────────

    def _archive_path(self, note_id: str) -> Path:
        return self._dir / "archive" / f"{note_id}.yaml"

    def list_archived_notes(self, query: str = "") -> list[dict]:
        items = []
        q = query.strip().lower()
        for name in self._git.list_committed("notes/archive"):
            if not name.endswith(".yaml"):
                continue
            raw = self._git.read_committed(f"notes/archive/{name}")
            if raw is None:
                continue
            n = yaml.safe_load(raw.decode("utf-8"))
            if not isinstance(n, dict):
                continue
            if q:
                n_dec = self._decrypt_body(n)
                if (
                    q not in n_dec.get("subject", "").lower()
                    and q not in n_dec.get("body", "").lower()
                ):
                    continue
            items.append(n)
        return sorted(items, key=lambda x: x.get("updated", x.get("created", "")), reverse=True)

    def get_archived_note(self, note_id: str) -> dict | None:
        raw = self._git.read_committed(f"notes/archive/{note_id}.yaml")
        if raw is None:
            return None
        data = yaml.safe_load(raw.decode("utf-8"))
        if not isinstance(data, dict):
            return None
        return self._decrypt_body(data)

    def archive_note(self, note_id: str) -> bool:
        note_raw = self._git.read_committed(f"notes/{note_id}.yaml")
        if note_raw is None:
            return False
        note = yaml.safe_load(note_raw.decode("utf-8"))
        if not isinstance(note, dict):
            return False
        subject = note.get("subject", note_id)
        self._git._pull()
        src = self._path(note_id)
        if not src.exists():
            return False
        dst = self._archive_path(note_id)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        self._git._commit_and_push(f"notes: archive '{subject}'")
        return True

    def restore_note(self, note_id: str) -> bool:
        note_raw = self._git.read_committed(f"notes/archive/{note_id}.yaml")
        if note_raw is None:
            return False
        note = yaml.safe_load(note_raw.decode("utf-8"))
        if not isinstance(note, dict):
            return False
        subject = note.get("subject", note_id)
        self._git._pull()
        src = self._archive_path(note_id)
        if not src.exists():
            return False
        dst = self._path(note_id)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        # Remove archive dir if empty
        archive_dir = self._dir / "archive"
        if archive_dir.is_dir() and not any(archive_dir.iterdir()):
            archive_dir.rmdir()
        self._git._commit_and_push(f"notes: restore '{subject}'")
        return True
