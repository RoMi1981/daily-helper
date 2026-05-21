"""Mail template storage — YAML files in mail_templates/ subdirectory."""

import logging
import uuid
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class MailTemplateStorage:
    """Manages mail_templates/{id}.yaml files inside the data git repo."""

    def __init__(self, git_storage):
        self._git = git_storage
        self._dir = Path(git_storage.local_path) / "mail_templates"

    def _path(self, template_id: str) -> Path:
        return self._dir / f"{template_id}.yaml"

    def _read(self, path: Path) -> dict | None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Failed to read mail template %s: %s", path, e)
            return None

    def _write(self, template: dict):
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(template["id"]).write_text(
            yaml.dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def list_templates(self) -> list[dict]:
        self._git._pull()
        if not self._dir.exists():
            return []
        items = []
        for f in self._dir.glob("*.yaml"):
            t = self._read(f)
            if t:
                items.append(t)
        return sorted(items, key=lambda x: x.get("name", "").lower())

    def get_template(self, template_id: str) -> dict | None:
        self._git._pull()
        p = self._path(template_id)
        return self._read(p) if p.exists() else None

    def create_template(self, data: dict) -> dict:
        template = {
            "id": _new_id(),
            "name": data.get("name", "").strip(),
            "to": data.get("to", "").strip(),
            "cc": data.get("cc", "").strip(),
            "subject": data.get("subject", "").strip(),
            "body": data.get("body", "").strip(),
            "created": date.today().isoformat(),
        }
        self._git._pull()
        self._write(template)
        self._git._commit_and_push(f"mail-templates: add '{template['name']}'")
        return template

    def update_template(self, template_id: str, data: dict) -> dict | None:
        template = self.get_template(template_id)
        if not template:
            return None
        template.update({
            "name": data.get("name", template["name"]).strip(),
            "to": data.get("to", template.get("to", "")).strip(),
            "cc": data.get("cc", template.get("cc", "")).strip(),
            "subject": data.get("subject", template.get("subject", "")).strip(),
            "body": data.get("body", template.get("body", "")).strip(),
        })
        self._write(template)
        self._git._commit_and_push(f"mail-templates: update '{template['name']}'")
        return template

    def delete_template(self, template_id: str) -> bool:
        self._git._pull()
        p = self._path(template_id)
        if not p.exists():
            return False
        t = self._read(p)
        p.unlink()
        name = t.get("name", template_id) if t else template_id
        self._git._commit_and_push(f"mail-templates: delete '{name}'")
        return True
