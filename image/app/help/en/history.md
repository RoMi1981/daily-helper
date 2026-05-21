# History

Shows all changes across all repos and modules — grouped by git commit.

## Time range tabs

| Tab | Range |
|-----|-------|
| Today | Commits since midnight |
| This week | Since Monday of the current week |
| This month | Since the 1st of the current month |
| Last 30 days | Rolling 30-day window |
| Last 3 months | 90 days |
| This year | Since 1 January |
| All | All available commits (max. 500) |

## Filters

| Filter | Description |
|--------|-------------|
| **Module** | Show only commits from a specific module (Knowledge, Tasks, Notes, …) |
| **Author** | Filter by git commit author |
| **From / To** | Restrict to a date range (based on commit timestamp) |

**Clear** removes all active filters while keeping the current time range tab.

## Reading the timeline

Each row is a git commit. Shown for each commit:
- **Author** — who made the change
- **Timestamp** — when the commit was created
- **Subject** — the git commit message (up to 80 characters)
- **Hash** — short commit SHA for reference
- **Changes** — each changed file with module badge and action (Added / Modified / Deleted)

Clicking the title navigates directly to the entry (not available for deleted entries).

## Repository health (Settings)

Under **Settings → Repositories** the **Health** button checks each repo:

| Field | Meaning |
|-------|---------|
| Reachable | Whether the remote git host is reachable |
| Last commit | Timestamp of the last local commit (warning if > 24 h) |
| Files | Total number of tracked files |
| Commits (7d) | Number of commits in the last 7 days |
