"""Ticket template storage — YAML files in ticket_templates/ subdirectory."""

import uuid
from datetime import date

from core.yaml_dir_storage import YamlDirStorage


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class TicketTemplateStorage(YamlDirStorage):
    """Manages ticket_templates/{id}.yaml files inside the data git repo."""

    subdir = "ticket_templates"

    def list_templates(self) -> list[dict]:
        return sorted(self._list_raw(), key=lambda x: x.get("name", "").lower())

    def get_template(self, template_id: str) -> dict | None:
        return self.get_entry(template_id)

    def create_template(self, data: dict) -> dict:
        template = {
            "id": _new_id(),
            "name": data.get("name", "").strip(),
            "description": data.get("description", "").strip(),
            "body": data.get("body", "").strip(),
            "created": date.today().isoformat(),
        }
        with self._git.write_lock():
            self._git._pull()
            self._write(template)
            self._git._commit_and_push(f"ticket-templates: add '{template['name']}'")
        return template

    def update_template(self, template_id: str, data: dict) -> dict | None:
        template = self.get_template(template_id)
        if not template:
            return None
        template.update(
            {
                "name": data.get("name", template["name"]).strip(),
                "description": data.get("description", template.get("description", "")).strip(),
                "body": data.get("body", template.get("body", "")).strip(),
            }
        )
        with self._git.write_lock():
            self._git._pull()
            self._write(template)
            self._git._commit_and_push(f"ticket-templates: update '{template['name']}'")
        return template

    def delete_template(self, template_id: str) -> bool:
        with self._git.write_lock():
            t = self._delete(template_id)
            if t is None:
                return False
            name = t.get("name", template_id)
            self._git._commit_and_push(f"ticket-templates: delete '{name}'")
        return True
