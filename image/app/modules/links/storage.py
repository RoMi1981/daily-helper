"""Links storage — YAML files in links/{section_id}/ subdirectory."""

import logging
import uuid
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class LinkStorage:
    """Manages links/{section_id}/{id}.yaml files inside the data git repo."""

    def __init__(self, git_storage, section_id: str = "default"):
        self._git = git_storage
        self._section_id = section_id
        self._dir = Path(git_storage.local_path) / "links" / section_id

    def _path(self, link_id: str) -> Path:
        return self._dir / f"{link_id}.yaml"

    def _prefix(self) -> str:
        return f"links/{self._section_id}"

    def _read(self, path: Path) -> dict | None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Failed to read link %s: %s", path, e)
            return None

    def _write(self, link: dict):
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(link["id"]).write_text(
            yaml.dump(link, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def list_links(self, query: str = "", category: str = "") -> list[dict]:
        items = []
        q = query.strip().lower()
        cat = category.strip().lower()
        for name in self._git.list_committed(self._prefix()):
            if not name.endswith(".yaml"):
                continue
            raw = self._git.read_committed(f"{self._prefix()}/{name}")
            if raw is None:
                continue
            link = yaml.safe_load(raw.decode("utf-8"))
            if not isinstance(link, dict):
                continue
            if q and not any(
                q in link.get(field, "").lower()
                for field in ("title", "url", "description", "category")
            ):
                continue
            if cat and link.get("category", "").lower() != cat:
                continue
            items.append(link)
        return sorted(
            items, key=lambda x: (x.get("category", "").lower(), x.get("title", "").lower())
        )

    def get_categories(self) -> list[str]:
        cats: set[str] = set()
        for name in self._git.list_committed(self._prefix()):
            if not name.endswith(".yaml"):
                continue
            raw = self._git.read_committed(f"{self._prefix()}/{name}")
            if raw is None:
                continue
            link = yaml.safe_load(raw.decode("utf-8"))
            if isinstance(link, dict) and link.get("category"):
                cats.add(link["category"])
        return sorted(cats)

    def get_link(self, link_id: str) -> dict | None:
        raw = self._git.read_committed(f"{self._prefix()}/{link_id}.yaml")
        if raw is None:
            return None
        data = yaml.safe_load(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None

    def create_link(self, data: dict) -> dict:
        link = {
            "id": _new_id(),
            "title": data.get("title", "").strip(),
            "url": data.get("url", "").strip(),
            "category": data.get("category", "").strip(),
            "description": data.get("description", "").strip(),
            "created": date.today().isoformat(),
        }
        self._git._pull()
        self._write(link)
        self._git._commit_and_push(f"links: add '{link['title']}'")
        return link

    def update_link(self, link_id: str, data: dict) -> dict | None:
        self._git._pull()
        link = self.get_link(link_id)
        if not link:
            return None
        link.update(
            {
                "title": data.get("title", link["title"]).strip(),
                "url": data.get("url", link.get("url", "")).strip(),
                "category": data.get("category", link.get("category", "")).strip(),
                "description": data.get("description", link.get("description", "")).strip(),
            }
        )
        self._write(link)
        self._git._commit_and_push(f"links: update '{link['title']}'")
        return link

    def delete_link(self, link_id: str) -> bool:
        self._git._pull()
        p = self._path(link_id)
        if not p.exists():
            return False
        link = self._read(p)
        p.unlink()
        title = link.get("title", link_id) if link else link_id
        self._git._commit_and_push(f"links: delete '{title}'")
        return True

    def bulk_delete_links(self, link_ids: list[str]) -> int:
        if not link_ids:
            return 0
        self._git._pull()
        deleted = 0
        for lid in link_ids:
            p = self._path(lid)
            if not p.exists():
                # may be in a section subdirectory
                for sub in (self._dir).iterdir() if self._dir.is_dir() else []:
                    if sub.is_dir():
                        sp = sub / f"{lid}.yaml"
                        if sp.exists():
                            sp.unlink()
                            deleted += 1
                            break
            else:
                p.unlink()
                deleted += 1
        if deleted:
            self._git._commit_and_push(f"links: bulk delete {deleted} link(s)")
        return deleted
