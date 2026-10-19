# Operations

Copy or move content between two repos. Visible when at least 2 repos are configured.

## Prerequisites

Configure at least 2 repos in **Settings**. The `🔀 Ops` link then appears in the navigation.

## Copying or moving content

1. Select the **source repo**
2. Select the **target repo**
3. Select the **module** (Knowledge, Tasks, Vacations, Appointments, Mail Templates, Ticket Templates, Notes, Links, Runbooks, Snippets, MOTD, RSS)
4. Check entries from the list (for Knowledge: categories or individual entries)
5. Click **Copy** or **Move**

When moving, the entry is deleted from the source repo and created in the target repo. Both changes are saved as separate git commits.

## ZIP Export

Exports all YAML/MD/TXT files from a repo as a ZIP archive (`daily-helper_{repo}_export.zip`). Useful for backups or migration.

## ZIP Import

Imports a ZIP archive into a repo:

| Mode | Behaviour |
|------|-----------|
| **Merge** | Existing entries are kept; new entries from the ZIP are added |
| **Overwrite** | All existing data in the target repo is replaced |

The import automatically writes a git commit. Path traversal attacks are blocked.
