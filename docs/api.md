# Daily Helper — API Reference

All endpoints return HTML unless noted otherwise. The application is a server-rendered web app; these endpoints are primarily designed for browser use. JSON/REST endpoints are explicitly marked.

## Global

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Home dashboard |
| GET | `/search?q=…` | Global full-text search across all modules |
| GET | `/health` | JSON health check (`{"status":"ok","cache_keys":N,"cache_hit_rate_pct":N}`) |
| GET | `/metrics` | Prometheus metrics |
| GET | `/history` | Audit log (filterable by module, author, date) |
| GET | `/settings` | Settings page |
| POST | `/settings/export` | Download encrypted settings backup (`.dhbak`) |
| POST | `/settings/import` | Restore settings from backup file |
| GET | `/api/redis-status` | JSON Redis status |
| POST | `/api/cache/flush` | Flush Redis cache |
| POST | `/api/restart` | Restart the application |
| GET/POST | `/api/favorites/toggle` | HTMX: toggle favorite for any module entry |

---

## Knowledge

| Method | Path | Description |
|--------|------|-------------|
| GET | `/knowledge` | Entry list (filterable by category) |
| GET | `/knowledge/new` | New entry form |
| POST | `/knowledge/entries` | Create entry |
| GET | `/knowledge/entries/{repo}/{category}/{slug}` | View entry |
| GET | `/knowledge/entries/{repo}/{category}/{slug}/edit` | Edit form |
| POST | `/knowledge/entries/{repo}/{category}/{slug}/edit` | Save edit |
| POST | `/knowledge/entries/{repo}/{category}/{slug}/delete` | Delete entry |
| POST | `/knowledge/entries/{repo}/{category}/{slug}/toggle-pin` | Toggle pinned status |
| GET | `/knowledge/entries/{repo}/{category}/{slug}/history` | Git history for entry |
| GET | `/api/preview` | JSON: render Markdown to HTML (`?content=…`) |

---

## Tasks

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tasks` | Task list (open + done) |
| POST | `/tasks` | Create task |
| GET | `/tasks/{id}/edit` | Edit form (includes "Blocked by" task picker) |
| POST | `/tasks/{id}/edit` | Save edit (accepts `blocked_by[]` list) |
| POST | `/tasks/{id}/toggle` | HTMX: toggle done/undone, returns updated card HTML |
| POST | `/tasks/{id}/delete` | Delete task |
| GET | `/tasks/{id}/history` | Git history for task |
| POST | `/tasks/bulk-delete` | Delete multiple tasks (`ids[]` form field) |

**Task YAML schema:**
```yaml
id: abc12345
title: "Task title"
description: ""
due_date: "2026-05-01"   # optional
priority: medium          # high | medium | low
done: false
recurring: none           # none | daily | weekly | monthly
blocked_by: []            # list of task IDs this task is blocked by
created: "2026-04-01"
```

---

## Vacations

| Method | Path | Description |
|--------|------|-------------|
| GET | `/vacations` | Vacation list + account summary |
| POST | `/vacations` | Create vacation request |
| GET | `/vacations/{id}/edit` | Edit form |
| POST | `/vacations/{id}/edit` | Save edit |
| POST | `/vacations/{id}/status` | Update status (HTMX inline) |
| POST | `/vacations/{id}/delete` | Delete entry |
| GET | `/vacations/{id}/export.ics` | Download ICS (`?profile=id` for named profile) |
| GET | `/vacations/{id}/mail` | Vacation mail preview |
| GET | `/vacations/{id}/mail.eml` | Download `.eml` file |
| GET | `/vacations/export.csv` | Download all entries as CSV (`?year=YYYY`) |
| GET | `/vacations/calendar` | Redirect to `/calendar` |

---

## Calendar

| Method | Path | Description |
|--------|------|-------------|
| GET | `/calendar` | Unified monthly calendar (`?year=YYYY&month=MM`) |
| GET | `/calendar/capacity` | Sprint capacity view |
| GET | `/calendar/holiday.ics` | Download holiday ICS (`?date=YYYY-MM-DD&name=…&profile=id`) |

---

## Appointments

| Method | Path | Description |
|--------|------|-------------|
| GET | `/appointments` | Appointment list |
| POST | `/appointments` | Create appointment |
| GET | `/appointments/{id}/edit` | Edit form |
| POST | `/appointments/{id}/edit` | Save edit |
| POST | `/appointments/{id}/delete` | Delete appointment |
| GET | `/appointments/{id}/export.ics` | Download ICS (`?profile=id` for named profile) |

---

## Notes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/notes` | Note list |
| GET | `/notes/new` | New note form |
| POST | `/notes/new` | Create note |
| GET | `/notes/{id}` | View note |
| GET | `/notes/{id}/edit` | Edit form |
| POST | `/notes/{id}/edit` | Save edit |
| POST | `/notes/{id}/delete` | Delete note |
| POST | `/notes/{id}/archive` | Archive note |
| POST | `/notes/archive/{id}/restore` | Restore from archive |
| GET | `/notes/{id}/history` | Git history |
| POST | `/notes/bulk-delete` | Delete multiple notes |

---

## Links

| Method | Path | Description |
|--------|------|-------------|
| GET | `/links` | Link list (filterable by section, category, search) |
| GET | `/links/new` | New link form |
| POST | `/links/new` | Create link |
| GET | `/links/{id}/edit` | Edit form |
| POST | `/links/{id}/edit` | Save edit |
| POST | `/links/{id}/delete` | Delete link |
| POST | `/links/bulk-delete` | Delete multiple links |

---

## Runbooks

| Method | Path | Description |
|--------|------|-------------|
| GET | `/runbooks` | Runbook list |
| GET | `/runbooks/new` | New runbook form |
| POST | `/runbooks/new` | Create runbook |
| GET | `/runbooks/{id}` | View runbook (step-by-step execution) |
| POST | `/runbooks/{id}/edit` | Save edit |
| POST | `/runbooks/{id}/delete` | Delete runbook |
| POST | `/runbooks/bulk-delete` | Delete multiple runbooks |

---

## Snippets

| Method | Path | Description |
|--------|------|-------------|
| GET | `/snippets` | Snippet list |
| GET | `/snippets/new` | New snippet form |
| POST | `/snippets/new` | Create snippet |
| GET | `/snippets/{id}` | View snippet |
| POST | `/snippets/{id}/edit` | Save edit |
| POST | `/snippets/{id}/delete` | Delete snippet |
| POST | `/snippets/bulk-delete` | Delete multiple snippets |

---

## Mail Templates

| Method | Path | Description |
|--------|------|-------------|
| GET | `/mail-templates` | Template list |
| POST | `/mail-templates/new` | Create template |
| POST | `/mail-templates/{id}/edit` | Save edit |
| POST | `/mail-templates/{id}/delete` | Delete template |
| GET | `/mail-templates/{id}/download.eml` | Download as `.eml` |

---

## Ticket Templates

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ticket-templates` | Template list |
| POST | `/ticket-templates/new` | Create template |
| POST | `/ticket-templates/{id}/edit` | Save edit |
| POST | `/ticket-templates/{id}/delete` | Delete template |

---

## MOTD

| Method | Path | Description |
|--------|------|-------------|
| GET | `/motd` | Message list |
| POST | `/motd/new` | Create message |
| POST | `/motd/{id}/edit` | Save edit |
| POST | `/motd/{id}/delete` | Delete message |
| POST | `/motd/import` | Import from URL |
| POST | `/motd/import-file` | Import from file |
| GET | `/api/home/motd` | JSON: current active MOTD for home widget |

---

## Picture of the Day (PotD)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/potd` | Picture list |
| POST | `/potd/upload` | Upload image |
| POST | `/potd/fetch` | Fetch image from URL |
| GET | `/potd/{id}/raw` | Serve raw image |
| POST | `/potd/{id}/delete` | Delete image |
| GET | `/api/home/potd` | JSON: today's PotD for home widget |

---

## Memes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/memes` | Meme list |
| POST | `/memes/upload` | Upload meme |
| POST | `/memes/fetch` | Fetch meme from URL |
| GET | `/memes/{id}/raw` | Serve raw meme |
| POST | `/memes/{id}/delete` | Delete meme |
| GET | `/api/home/meme` | JSON: random meme for home widget |

---

## RSS Reader

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rss` | Feed list + article list for current feed |
| POST | `/rss/feeds/new` | Add feed |
| POST | `/rss/feeds/{id}/edit` | Edit feed |
| POST | `/rss/feeds/{id}/delete` | Delete feed |
| POST | `/rss/feeds/{id}/set-default` | Set default feed |
| GET | `/api/home/rss` | JSON: recent articles for home widget |

---

## Operations (Copy / Move)

Available when 2+ repositories are configured.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/operations` | Operations page (copy/move between repos) |
| POST | `/operations/execute` | Execute copy or move |
| GET | `/operations/export` | ZIP export of all data |
| POST | `/operations/import` | ZIP import |

---

## History / Audit

| Method | Path | Description |
|--------|------|-------------|
| GET | `/history` | Audit log (filterable by module, author, date range) |
| GET | `/history/{repo_id}/{path}` | File-level git history |
