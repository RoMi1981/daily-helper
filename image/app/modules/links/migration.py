"""Auto-migration: flat links/*.yaml → links/{section_id}/*.yaml."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def migrate_flat_to_section(git_storage, section_id: str) -> bool:
    """Move flat links/*.yaml files to links/{section_id}/.

    Returns True if any files were migrated. Safe to call repeatedly —
    only migrates files that still exist at the flat level.
    """
    flat_names = git_storage.list_committed("links")
    to_migrate = [n for n in flat_names if n.endswith(".yaml")]
    if not to_migrate:
        return False

    base = Path(git_storage.local_path)
    target_dir = base / "links" / section_id
    target_dir.mkdir(parents=True, exist_ok=True)

    git_storage._pull()
    moved = 0
    for name in to_migrate:
        src = base / "links" / name
        dst = target_dir / name
        if src.exists() and not dst.exists():
            dst.write_bytes(src.read_bytes())
            src.unlink()
            moved += 1

    if moved:
        logger.info("Migrated %d links to section '%s'", moved, section_id)
        git_storage._commit_and_push(
            f"links: migrate {moved} flat files to section '{section_id}'"
        )

    return moved > 0
