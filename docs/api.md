# Daily Helper — API Reference

All endpoints return HTML unless noted otherwise. The application is a server-rendered web app; these endpoints are primarily designed for browser use. JSON endpoints are marked **JSON**, HTMX partials **HTMX**.

This file is checked against the application's routes by `image/tests/test_api_docs.py`: every route must be listed with its method, and every listed route must exist.

---

## Global

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/` | Redirects to `/widgets` (the widget dashboard is the application start page) |
| GET | `/help/{module}` | Help page for a module (language from Settings, English fallback) |
| GET | `/search` | Global full-text search across all modules |
| POST | `/api/preview` | **HTMX**: render Markdown to sanitised HTML (JSON body `{"content": …}`) |
| GET | `/api/repos/{repo_id}/health` | **HTMX**: health details for one repository |
| GET | `/api/templates` | **JSON**: knowledge entry templates |
| GET | `/health` | **JSON**: `{"status": "ok", "version": …, "cache": bool}`, plus `cache_keys` and `cache_hit_rate_pct` while Redis is connected |
| GET | `/api/repos-status-banner` | **HTMX**: banner for unreachable repositories / pending pushes |
| GET | `/api/redis-status` | **HTMX**: Redis indicator for the navbar (re-polls every 30 s) |
| POST | `/api/restart` | Restart the application |
| POST | `/api/cache/flush` | Flush Redis cache |
| POST | `/api/favorites/toggle` | **HTMX**: toggle favorite for any module entry |
| POST | `/api/sync` | **HTMX**: reset the pull throttle for all repositories and flush the cache |
| GET | `/metrics` | Prometheus metrics |

---

## Knowledge

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/knowledge/` | Entry list (filterable by category) |
| GET | `/knowledge/search` | **HTMX**: search results partial (`?q=&category=`) |
| GET | `/knowledge/new` | New entry form |
| POST | `/knowledge/entries` | Create entry |
| GET | `/knowledge/entries/{repo_id}/{category}/{slug}` | View entry |
| GET | `/knowledge/entries/{repo_id}/{category}/{slug}/edit` | Edit form |
| POST | `/knowledge/entries/{repo_id}/{category}/{slug}/edit` | Save edit |
| POST | `/knowledge/entries/{repo_id}/{category}/{slug}/pin` | **HTMX**: toggle pinned status |
| POST | `/knowledge/entries/{repo_id}/{category}/{slug}/attachments` | Upload an attachment to an entry |
| GET | `/knowledge/entries/{repo_id}/{category}/{slug}/attachments/{filename}` | Download an attachment |
| POST | `/knowledge/entries/{repo_id}/{category}/{slug}/attachments/{filename}/delete` | Delete an attachment |
| GET | `/knowledge/entries/{repo_id}/{category}/{slug}/history` | Git history for entry |
| POST | `/knowledge/entries/{repo_id}/{category}/{slug}/delete` | Delete entry |
| GET | `/knowledge/category/{category}` | Entries of one category (paginated, `?page=`) |

---

## Tasks

**Task YAML schema** (open tasks in `tasks/`, done tasks in `tasks/done/`):

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

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/tasks` | Task list (open + done) |
| POST | `/tasks` | Create task |
| GET | `/tasks/{task_id}/edit` | Edit form (includes "Blocked by" task picker) |
| POST | `/tasks/{task_id}/edit` | Save edit (accepts `blocked_by[]` list) |
| POST | `/tasks/{task_id}/toggle` | **HTMX**: toggle done/undone, returns updated card HTML |
| GET | `/tasks/{task_id}/history` | Git history for task |
| POST | `/tasks/{task_id}/delete` | Delete task |
| POST | `/tasks/bulk-delete` | Delete multiple tasks (`ids[]` form field) |

---

## Vacations

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/vacations` | Vacation list + account summary |
| GET | `/vacations/calendar` | Redirect to `/calendar` |
| GET | `/vacations/{entry_id}/mail` | Vacation mail preview |
| GET | `/vacations/{entry_id}/mail.eml` | Download `.eml` file |
| GET | `/vacations/{entry_id}/export.ics` | Download ICS (`?profile=id` for named profile) |
| GET | `/vacations/export.csv` | Download all entries as CSV (`?year=YYYY`) |
| POST | `/vacations` | Create vacation request |
| GET | `/vacations/{entry_id}/edit` | Edit form |
| POST | `/vacations/{entry_id}/edit` | Save edit |
| POST | `/vacations/{entry_id}/status` | Update status (HTMX inline) |
| POST | `/vacations/{entry_id}/delete` | Delete entry |

---

## Calendar

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/calendar` | Unified monthly calendar (`?year=YYYY&month=MM`) |
| GET | `/calendar/capacity` | Sprint capacity view |
| GET | `/calendar/holiday.ics` | Download holiday ICS (`?date=YYYY-MM-DD&name=…&profile=id`) |
| GET | `/calendar/vacations-redirect` | Redirect to the shared calendar, keeping `?year=&month=` |

---

## Appointments

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/appointments` | Appointment list |
| GET | `/appointments/{entry_id}/export.ics` | Download ICS (`?profile=id` for named profile) |
| GET | `/appointments/calendar` | Redirect to the shared calendar (`/calendar`) |
| POST | `/appointments` | Create appointment |
| GET | `/appointments/{entry_id}/edit` | Edit form |
| POST | `/appointments/{entry_id}/edit` | Save edit |
| POST | `/appointments/{entry_id}/delete` | Delete appointment |

---

## Notes

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/notes` | Note list |
| GET | `/notes/new` | New note form |
| POST | `/notes/new` | Create note |
| GET | `/notes/archive` | Archived notes |
| POST | `/notes/archive/{note_id}/restore` | Restore from archive |
| GET | `/notes/{note_id}` | View note |
| GET | `/notes/{note_id}/history` | Git history |
| GET | `/notes/{note_id}/edit` | Edit form |
| POST | `/notes/{note_id}/edit` | Save edit |
| POST | `/notes/{note_id}/delete` | Delete note |
| POST | `/notes/{note_id}/archive` | Archive note |
| POST | `/notes/bulk-delete` | Delete multiple notes |

---

## Links

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/links` | Link list (filterable by section, category, search) |
| GET | `/links/new` | New link form |
| POST | `/links/new` | Create link |
| GET | `/links/{link_id}/edit` | Edit form |
| POST | `/links/{link_id}/edit` | Save edit |
| POST | `/links/{link_id}/delete` | Delete link |
| POST | `/links/bulk-delete` | Delete multiple links |
| POST | `/links/bulk-move` | Move selected links to another section (one commit) |

---

## Floccus bookmark sync

A subset of the Nextcloud Bookmarks API, enough for the [Floccus](https://floccus.org) browser extension. HTTP Basic Auth with the per-section username and password from **Settings → Link Sections**; each section is its own bookmark collection. All responses are JSON except the login grant page.

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/index.php/apps/bookmarks/public/rest/v2/bookmark` | List bookmarks (`?url=` filter, `?page=` and `?limit=` paging) |
| POST | `/index.php/apps/bookmarks/public/rest/v2/bookmark` | Create a bookmark |
| GET | `/index.php/apps/bookmarks/public/rest/v2/bookmark/{link_id}` | Get one bookmark |
| PUT | `/index.php/apps/bookmarks/public/rest/v2/bookmark/{link_id}` | Update a bookmark |
| DELETE | `/index.php/apps/bookmarks/public/rest/v2/bookmark/{link_id}` | Delete a bookmark |
| GET | `/index.php/apps/bookmarks/public/rest/v2/folder` | Root folder list — Floccus uses this to discover the folder tree. |
| GET | `/index.php/apps/bookmarks/public/rest/v2/folder/{folder_id}/children` | Return folder children with full bookmark data (layers=-1 is the common call). |
| GET | `/index.php/apps/bookmarks/public/rest/v2/folder/{folder_id}/hash` | Hash for change detection — MD5 of sorted bookmark IDs in scope. |
| POST | `/index.php/apps/bookmarks/public/rest/v2/folder` | Create folder — returns a stable ID derived from the folder title. |
| PUT | `/index.php/apps/bookmarks/public/rest/v2/folder/{folder_id}` | Folder update stub. |
| DELETE | `/index.php/apps/bookmarks/public/rest/v2/folder/{folder_id}` | Delete folder — removes all bookmarks with that category. |
| DELETE | `/index.php/apps/bookmarks/public/rest/v2/folder/{folder_id}/bookmarks/{link_id}` | Remove a bookmark from a folder. |
| POST | `/index.php/apps/bookmarks/public/rest/v2/folder/{folder_id}/import` | Bulk import — not implemented. |
| PATCH | `/index.php/apps/bookmarks/public/rest/v2/folder/{folder_id}/childorder` | Child order stub — no-op. |
| POST | `/index.php/apps/bookmarks/public/rest/v2/lock` | Sync lock stub — always succeeds (single-user, no real locking needed). |
| DELETE | `/index.php/apps/bookmarks/public/rest/v2/lock` | Sync unlock stub. |
| GET | `/ocs/v2.php/cloud/capabilities` | Minimal Nextcloud capabilities stub required by Floccus during login. |
| POST | `/index.php/login/v2` | Nextcloud Login Flow v2 — init. Issues a pending token; credentials entered on grant page. |
| POST | `/index.php/login/v2/poll` | Nextcloud Login Flow v2 — poll. Returns credentials once the user has logged in. |
| GET | `/index.php/login/v2/grant` | Login form shown when Floccus opens the grant URL. User must enter credentials. |
| POST | `/index.php/login/v2/grant` | Handles the login form submission. Validates credentials and approves the token. |

---

## Runbooks

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/runbooks` | Runbook list |
| GET | `/runbooks/new` | New runbook form |
| POST | `/runbooks/new` | Create runbook |
| GET | `/runbooks/{runbook_id}` | View runbook (step-by-step execution) |
| GET | `/runbooks/{runbook_id}/edit` | Edit form |
| POST | `/runbooks/{runbook_id}/edit` | Save edit |
| GET | `/runbooks/{runbook_id}/history` | Git history for a runbook |
| POST | `/runbooks/{runbook_id}/delete` | Delete runbook |
| POST | `/runbooks/bulk-delete` | Delete multiple runbooks |

---

## Snippets

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/snippets` | Snippet list |
| GET | `/snippets/new` | New snippet form |
| POST | `/snippets/new` | Create snippet |
| GET | `/snippets/{snippet_id}` | View snippet |
| GET | `/snippets/{snippet_id}/edit` | Edit form |
| POST | `/snippets/{snippet_id}/edit` | Save edit |
| GET | `/snippets/{snippet_id}/history` | Git history for a snippet |
| POST | `/snippets/{snippet_id}/delete` | Delete snippet |
| POST | `/snippets/bulk-delete` | Delete multiple snippets |

---

## Mail Templates

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/mail-templates` | Template list |
| GET | `/mail-templates/new` | New template form |
| POST | `/mail-templates/new` | Create template |
| GET | `/mail-templates/{template_id}/edit` | Edit form |
| POST | `/mail-templates/{template_id}/edit` | Save edit |
| GET | `/mail-templates/{template_id}/download.eml` | Download as `.eml` |
| GET | `/mail-templates/{template_id}/history` | Git history for a template |
| POST | `/mail-templates/{template_id}/delete` | Delete template |

---

## Ticket Templates

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/ticket-templates` | Template list |
| GET | `/ticket-templates/new` | New template form |
| POST | `/ticket-templates/new` | Create template |
| GET | `/ticket-templates/{template_id}/edit` | Edit form |
| POST | `/ticket-templates/{template_id}/edit` | Save edit |
| GET | `/ticket-templates/{template_id}/history` | Git history for a template |
| POST | `/ticket-templates/{template_id}/delete` | Delete template |

---

## MOTD

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/motd` | Message list |
| GET | `/motd/new` | New message form |
| POST | `/motd/new` | Create message |
| GET | `/motd/import` | Import form |
| POST | `/motd/import` | Import from URL |
| POST | `/motd/import-file` | Import from file |
| GET | `/motd/{motd_id}/edit` | Edit form |
| POST | `/motd/{motd_id}/edit` | Save edit |
| POST | `/motd/{motd_id}/delete` | Delete message |
| POST | `/motd/next` | **HTMX**: advance to the next message for today |

---

## Picture of the Day (PotD)

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/potd` | Picture list |
| POST | `/potd/upload` | Upload image |
| GET | `/potd/{entry_id}/raw` | Serve raw image |
| POST | `/potd/fetch` | Fetch image from URL |
| POST | `/potd/{entry_id}/delete` | Delete image |
| POST | `/potd/next` | **HTMX**: advance to the next picture for today |

---

## Memes

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/memes` | Meme list |
| POST | `/memes/upload` | Upload meme |
| POST | `/memes/fetch` | Fetch meme from URL |
| GET | `/memes/{entry_id}/raw` | Serve raw meme |
| POST | `/memes/next` | **HTMX**: advance to the next meme for today |
| POST | `/memes/{entry_id}/delete` | Delete meme |

---

## RSS Reader

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/rss` | Feed list + article list for current feed |
| POST | `/rss/feeds/new` | Add feed |
| POST | `/rss/feeds/{feed_id}/edit` | Edit feed |
| POST | `/rss/feeds/{feed_id}/delete` | Delete feed |
| POST | `/rss/feeds/{feed_id}/set-default` | Set default feed |
| GET | `/rss/feed/{feed_id}` | **HTMX**: articles of one feed (cached 15 min) |
| POST | `/rss/feed/{feed_id}/refresh` | **HTMX**: re-fetch a feed, bypassing the cache |
| GET | `/rss/{feed_id}` | Reader page for one feed |

---

## EOL Tracker

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/eol` | Tracked software with live status from endoflife.date |
| GET | `/eol/add` | Search page for adding a product |
| GET | `/eol/search` | **HTMX**: product search against endoflife.date (`?q=`) |
| GET | `/eol/product/{product}` | Release cycles of a product |
| GET | `/eol/timeline/{product}` | Gantt timeline of a product's support phases |
| POST | `/eol/add` | Track a product cycle |
| POST | `/eol/{entry_id}/notes` | Save notes for a tracked entry |
| POST | `/eol/{entry_id}/delete` | Stop tracking an entry |

---

## Widgets (start page)

`/widgets` is the application start page (`GET /` redirects here). Customisable dashboard with drag-and-drop, resizable widgets on a 24-column grid; layout and per-widget settings persisted in `settings.json`.

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/widgets` | Widget dashboard (renders all enabled widgets) |
| POST | `/widgets/layout` | Save widget layout (position, size, enabled state, per-widget settings) as JSON |
| GET | `/widgets/calendar-partial` | **HTMX**: calendar widget month navigation (`?year=&month=`) |
| POST | `/widgets/{widget_id}/settings` | Save settings for a single widget |

---

## Operations (Copy / Move)

Available when 2+ repositories are configured.

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/operations` | Operations page (copy/move between repos) |
| POST | `/operations/execute` | Execute copy or move |
| GET | `/operations/export` | ZIP export of all data |
| POST | `/operations/import` | ZIP import |

---

## History

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/history` | Audit log (filterable by module, author, date range) |

---

## Settings

| Method | Path | Description |
| -------- | ------ | ------------- |
| GET | `/settings` | Settings page |
| POST | `/settings/appearance` | Save theme and language |
| POST | `/settings/git-identity` | Save the global git author name and email |
| POST | `/settings/repos` | Add a repository |
| POST | `/settings/repos/{repo_id}` | Update a repository |
| POST | `/settings/repos/{repo_id}/delete` | Remove a repository (local clone is cleaned up) |
| POST | `/settings/repos/{repo_id}/copy` | Create a copy of a repository's settings |
| POST | `/settings/repos/{repo_id}/toggle` | **HTMX**: enable / disable a repository |
| POST | `/settings/repos/{repo_id}/check` | **HTMX**: check read/write permissions via the platform API |
| POST | `/settings/repos/{repo_id}/test` | **HTMX**: test the git connection (clone, fetch, test push) |
| POST | `/settings/repos/{repo_id}/sync` | **HTMX**: force a pull for one repository |
| POST | `/settings/templates` | Add a knowledge entry template |
| POST | `/settings/templates/{template_id}` | Update a knowledge entry template |
| POST | `/settings/templates/{template_id}/delete` | Delete a knowledge entry template |
| POST | `/settings/generate-keypair` | **JSON**: generate an ed25519 SSH key pair |
| POST | `/settings/tls` | Save the TLS mode |
| POST | `/settings/notes` | Save notes settings (scroll position, line numbers) |
| POST | `/settings/vacation` | Save vacation settings (state, days per year, carry-over) |
| POST | `/settings/vacation-mail` | Save the vacation mail template |
| POST | `/settings/sprints` | Save sprint settings |
| POST | `/settings/link-sections/new` | Add a link section (optionally with Floccus sync) |
| POST | `/settings/link-sections/{section_id}/edit` | Update a link section |
| POST | `/settings/link-sections/{section_id}/delete` | Delete a link section (stored links are kept) |
| POST | `/settings/ics-profiles` | Add a vacation ICS profile |
| POST | `/settings/ics-profiles/{profile_id}/edit` | Update a vacation ICS profile |
| POST | `/settings/ics-profiles/{profile_id}/delete` | Delete a vacation ICS profile |
| POST | `/settings/appointment-ics-profiles` | Add an appointment ICS profile |
| POST | `/settings/appointment-ics-profiles/{profile_id}/edit` | Update an appointment ICS profile |
| POST | `/settings/appointment-ics-profiles/{profile_id}/delete` | Delete an appointment ICS profile |
| POST | `/settings/holiday-ics-profiles` | Add a holiday ICS profile |
| POST | `/settings/holiday-ics-profiles/{profile_id}/edit` | Update a holiday ICS profile |
| POST | `/settings/holiday-ics-profiles/{profile_id}/delete` | Delete a holiday ICS profile |
| POST | `/settings/module-repos` | Save which repositories each module uses |
| POST | `/settings/modules` | Enable / disable modules |
| POST | `/settings/metrics` | Enable / disable the `/metrics` endpoint |
| POST | `/settings/ticket-templates` | Save the ticket template description length limit |
| POST | `/settings/cache` | Save the cache file size limit |
| POST | `/settings/tls/generate` | **HTMX**: generate a self-signed CA and server certificate |
| POST | `/settings/export` | Download encrypted settings backup (`.dhbak`) |
| POST | `/settings/import` | Restore settings from backup file |
| POST | `/settings/backup-to-repo` | **HTMX**: commit an encrypted settings backup to a repository |
| GET | `/settings/tls/ca.crt` | Download the CA certificate |
