# CHANGELOG

All notable changes are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## 2026-05-07 — Snippets Copy Button Fix

### Fixed
- **Snippets copy button broken** — `onclick="copyCmd(this, {{ tojson }})"` with double-quoted attribute caused `SyntaxError: Unexpected end of input`; fixed by using single-quoted attribute `onclick='...'` in `list.html` and `detail.html`

---

## 2026-05-07 — Snippets List Actions, Global Clipboard Fallback

### Added
- **Snippets list — Edit / History / Delete buttons** — each snippet card in the list view now shows edit, history and delete actions directly; no need to open the detail page first
- **Global `copyText()` utility** — `base.html` defines a `copyText(text)` function used by all modules; falls back to `execCommand('copy')` when `navigator.clipboard` is unavailable (HTTP, older browsers); replaces 11 individual inline clipboard calls

---

## 2026-05-07 — i18n Complete (404 Keys, All Modules)

### Added
- **i18n Phases 2–14 complete** — 404 translation keys in `en.json` + `de.json`, fully in sync; covers all modules, forms, buttons, status messages, calendar legends, settings page, and empty states
- **i18n key categories**: `action.*` (40+ buttons), `field.*` (form labels), `status.*` / `priority.*` / `recurring.*` (badges), `empty.*` / `confirm.*` (empty states), `cal.*` (calendar), `settings.*`, `home.*`, `qc.*` (quick capture), `msg.*`, `label.*`, `nav.*`

### Fixed
- **Jinja2 loop variable shadowing `t()`**: 6 templates used `{% for t in ... %}` which overwrote the `t()` translation function; caused `TypeError: 'dict' object is not callable` on page load; fixed by renaming loop vars to `tmpl` / `task_item` / `ctype` / `btype` / `te` in `mail_templates/list.html`, `ticket_templates/list.html`, `tasks/form.html`, `settings.html`, `calendar/capacity.html`, `calendar/index.html`

---

## 2026-05-06 — Offline Mode, Repo Status, Multilingual UI

### Added
- **Offline Mode** — when `git push` fails due to network errors (timeout, connection refused, DNS failure etc.), the local commit is kept and a `.pending_push` flag is written; a background task retries every 60 s automatically; successful retry clears the flag and invalidates cache
- **Repo offline banner** — HTMX-polled banner (`#repo-status-banner`) appears at the top of every page when any repo has queued changes; auto-refreshes every 30 s; disappears immediately once the push succeeds
- **Multilingual navigation (i18n)** — `core/i18n.py` with JSON locale files (`locales/en.json`, `locales/de.json`); Jinja2 global `t()` function; sidebar + navbar breadcrumb labels translated; language toggle (English / Deutsch) in Settings → Appearance; `<html lang>` reflects chosen language
- **`MultiRepoStorage.repos_status()`** — returns online/pending status for all repos without a remote call
- **`MultiRepoStorage.retry_all_pending()`** — single call to retry all offline repos

### Changed
- **`_commit_and_push()`** refactored: commit phase and push phase are separate try/except blocks; network errors now queue instead of reverting the working tree; conflict/auth/other errors still revert and raise as before
- **Settings → Appearance** — new Language radio buttons; saved via `POST /settings/appearance`
- `test_other_push_error_raises_raw_message` updated to use a permission-denied error (not a network error) as expected input

---

## 2026-05-06 — Recurring Appointments

### Added
- **Recurring appointments** — appointments can be set to repeat weekly, monthly, or yearly; when a recurring appointment is deleted, the next occurrence is automatically created with a new ID; recurring interval displayed as a badge (repeat icon) on the appointment card; `recurring` field in YAML schema (`none` | `weekly` | `monthly` | `yearly`)
- **Recurring select in forms** — new-appointment form and edit form both have a "Recurring" dropdown; `relativedelta` handles month/year edge cases (e.g. Jan 31 + 1 month = Feb 28)
- **Unit tests** — 7 new tests in `test_appointments.py` covering create with recurring, invalid recurring defaults to none, weekly/monthly/yearly next-occurrence on delete, no next for `none`, and update sets recurring
- **E2E tests** — `TestRecurringAppointments` in `test_appointments.py`: recurring badge visible, non-recurring has no badge

---

## 2026-05-06 — Holiday ICS Profiles, Task Dependencies, Unified Design System

### Added
- **Holiday ICS Profiles** — configurable ICS export profiles for public holidays; create/edit/delete in Settings → Holiday ICS; download button appears on holiday rows in the calendar when at least one profile is configured; multi-file download (one per profile) using the same JS pattern as vacation ICS
- **Task dependencies (blocked by)** — tasks can be marked as blocked by other open tasks; edit form shows a scrollable checkbox list; blocked tasks show a lock badge in the list view; `blocked_by: []` YAML field (backward-compatible)
- **E2E tests** — `test_task_dependencies.py` (blocked indicator, edit form checkbox list) and `test_holiday_ics.py` (settings CRUD, calendar download button, ICS file download)

### Changed
- **Unified module list design system** — new CSS classes `.mod-card`, `.mod-card-info`, `.mod-card-title`, `.mod-card-meta`, `.mod-card-actions`; applied to notes, runbooks, snippets, links, mail-templates, ticket-templates, motd; mobile ≤ 600 px: actions wrap full-width below content with divider line
- **Task and vacation cards** — padding raised to `1rem 1.25rem` (matches `.card` default); gap increased to `0.75rem`; mobile breakpoint added for action buttons
- **"New" button placement** — primary action button moved into `page-header` for all modules (notes, runbooks, motd, mail-templates, ticket-templates, tasks, vacations)
- **Settings subnav** — ICS Profiles, Appointment ICS, and Holiday ICS sections added to horizontal subnav and JS sections array
- **docs/api.md** — new complete API reference covering all endpoints across all modules

---

## 2026-05-05 — Redis Caching, Home System Panel, E2E Robustness

### Added
- **Redis caching for git reads** — `read_committed()` and `list_committed()` cached with 600 s TTL; invalidated on every write
- **Redis caching for global search** — search results cached 60 s; invalidated on repo writes
- **Redis caching for history** — commit history cached per time-range (60–600 s); invalidated on writes
- **Redis image caching** — PotD and Meme binary files cached in Redis (base64-encoded, 1 h TTL, max 10 MB per file by default)
- **Configurable image cache size** — Settings → System: "Max image cache size (MB)" (default 10 MB); applied immediately without restart
- **Home: RSS widget** — RSS feed widget in right sidebar (top position)
- **Home: system panel** — shows Redis status, key count, hit rate, key-type breakdown, `/tmp` usage bar (color-coded), and local clone size per repository
- **Home: next vacation countdown** — right sidebar shows next upcoming vacation date and number of working days remaining; only shown when vacations module is enabled and a future vacation exists
- **Settings: RSS section** — dedicated RSS fieldset in Settings with configurable home article count (1–20, default 3); accessible via settings subnav
- **Vacation summary: requested counts as planned** — entries with status `requested` now appear in the Planned / After planned totals alongside `planned` entries

### Changed
- **Cache invalidation** — `invalidate_repo()` now also clears `history_commits:*`, `home:recent`, `potd:file:*`, and `meme:file:*`; removes stale `kb:search:*` pattern
- **tmpfs** — all docker-compose files raised from 64 MB to 512 MB

### Fixed
- **Orphaned repo cleanup** — local git clones in `/tmp` for repos removed from settings are deleted on next settings reload
- **E2E tests** — robustified 5 intermittently failing tests (`test_set_default_feed`, `test_finds_note`, `test_copy_button_present`, `test_ics_download_starts`, `test_task_history_link_in_edit_form`)

---

## 2026-05-04 — Multi-Repo Reads, Lightbox, Bug Fixes

### Added
- **Multi-repo read for all modules** — every module now aggregates LIST from all assigned repos (deduped by ID); GET/UPDATE/DELETE use first-hit search across all repos; CREATE stays on primary repo
- **Lightbox modal** — clicking any image thumbnail in Memes or PotD (list view and home widget) opens a full-screen lightbox overlay; close with Escape or click outside
- **Copy image to clipboard** — lightbox and per-card button copies the image as a PNG blob to the system clipboard via the Clipboard API (requires HTTPS or localhost)

### Fixed
- **RSS multi-repo** — `edit_feed`, `delete_feed`, `set_default_feed` now use `_find_store()` to search all assigned repos; previously only wrote to the primary repo
- **Memes 503 vs 404** — `serve_meme` and `delete_meme` now return 503 when no repository is configured (was incorrectly returning 404)

---

## 2026-05-04 — Memes Module, PotD PDF Thumbnails, Home Layout

### Added
- **Memes module** — image collection (JPG/PNG/WebP/GIF); upload via file or URL; daily random selection with HTMX next-button (Redis offset); home widget; stat tile; full nav/settings/history integration
- **PotD PDF thumbnails** — PDF page entries in the collection show a rendered canvas preview via PDF.js 3.11.174 (bundled locally under `/static`, no CDN required)
- **PotD URL fetch** — `POST /potd/fetch` downloads image/PDF from an http/https URL via `httpx`; type detected from `Content-Type` header with URL extension fallback
- **PotD next-button** — home widget has a `›` button to advance to the next picture for today (same Redis-offset pattern as MOTD)

### Changed
- **Home layout** — two-column desktop grid (`1fr 1fr`); right sidebar shows MOTD, PotD and Memes widgets; left side shows stat tiles + repos + favourites + recent + system; below 900 px the sidebar stacks on top
- **MOTD/PotD order** — MOTD first, then PotD, then Memes on home page

---

## 2026-05-03 — Mobile Overflow Fixes, CI Improvements

### Fixed
- **Mobile overflow — History** — commit subjects wrap on their own line (≤600px); filter-bar overflow clipped; date inputs no longer exceed flex container on Android
- **Mobile overflow — Notes list** — subject uses `word-break: break-word`; body snippet uses `word-break: break-all` for encrypted (spaceless) content
- **Mobile overflow — History audit entries** — module badge + action label stay inline; entry title wraps instead of overflowing right edge
- **Favourite buttons** — moved inside card frame for Notes, Runbooks, Links, Tasks (previously floated outside the card border)
- **Notes detail** — body textarea uses `white-space: pre-wrap` so long lines wrap instead of extending off-screen

### Changed
- **CI — redis-e2e cleanup** — `docker rm -f redis-e2e` runs before starting Redis so cancelled runs don't leave a stale container
- **CI — login job** — new `login` preflight job checks registry credentials; `test` and `e2e` only start after it succeeds, preventing wasted parallel runs on credential failures
- **E2E viewport** — corrected from 1080×2340 (physical pixels) to 390×844 (CSS pixels) so tests detect real mobile overflows
- **E2E search selector** — `/search` page now uses `#global-search-input` instead of `input[name="q"]` to avoid matching the hidden nav input

---

## 2026-05-02 — RSS Reader, PotD Collection Mode, MOTD Duplicate Detection

### Added
- **RSS Reader** — RSS and Atom feed reading via `feedparser`; feeds stored as YAML in the data git repo (`rss/{id}.yaml`); feed management (add/edit/delete) directly in the module page; Redis cache per feed (15 min); Refresh button per feed; horizontal scrollable subnav between feeds
- **MOTD duplicate detection** — `create_entry` and `bulk_import` detect and skip duplicate messages (case-insensitive, trimmed); import report shows how many messages were created vs. skipped
- **History/Operations for MOTD and RSS** — both modules now appear in History (git log), Operations copy/move, and home recent activity
- **PotD collection mode** — ID-based storage (random 8-char hex IDs) instead of date-based filenames; upload images/PDFs in any order; PDF page count detected automatically via `pypdf`; one page per collection entry; daily entry selected deterministically (`(today_int + offset) % len(entries)`) — same algorithm as MOTD

### Changed
- **Navigation** — module menu items and home tiles sorted alphabetically

---

## 2026-05-01 — PotD Multi-Page PDF, CI improvements

### Added
- **PotD: Multi-Page PDF Upload** — upload one PDF, page count detected automatically; each page becomes a separate collection entry with a sidecar YAML; PDF viewer jumps directly to the correct page (`#page=N` fragment)
- **Virtual PotD entries** — sidecar-only entries without their own media file; shown with dashed border in the list; deleting a sidecar removes only that page, not the source PDF

### Fixed
- **Home tiles on mobile** — fixed 2 columns at ≤480px instead of up to 3; long labels wrap correctly
- **Pinned entry titles** — `min-width: 0` prevents overflow on long entry titles

### Infrastructure
- **CI resource limits** — `--cpus=6 --memory=32g` on all test containers; prevents host overload from parallel test jobs
- **Redis for E2E tests** — `redis:7-alpine` runs alongside E2E tests; eliminates 30-second retry waits; E2E run time significantly reduced

---

## 2026-04-30 — Picture of the Day, History+Audit-Merge

### Added
- **Picture of the Day (PotD)** — täglicher Inhalt auf der Startseite; Datei aus dem Data-Repo (`potd/YYYY-MM-DD.{ext}`); Bilder (JPG/PNG/WebP/GIF) werden inline angezeigt, PDFs als eingebetteter Viewer (`<iframe>`); Fallback auf zuletzt verfügbare Datei; Upload-Formular auf der PotD-Seite (max 25 MB); Re-Upload für gleiches Datum ersetzt vorherige Datei; Delete-Button pro Eintrag; Module-Toggle + Repo Assignment; Home-Widget per HTMX lazy-load (`/api/home/potd`)
- **33 Unit-Tests für PotD** — `_list_files`, `_find_today_or_latest`, Router (list, upload, serve, delete, home widget)

### Changed
- **History + Audit zusammengeführt** — `/audit`-Route und Audit-Modul entfernt; `/history` übernimmt alle Funktionen; Zeit-Tabs (Today / This Week / This Month / 30d / 90d / 365d / All) mit HTMX-Partial-Reload; Filter-Bar (Modul, Autor, Datumsbereich) integriert; Tab-Wechsel erhält aktive Filter; Commit-Ansicht gruppiert (Autor, Timestamp, Subject, Hash, per-Change-Badges)

---

## 2026-04-30 — MOTD-Modul

### Added
- **MOTD (Message of the Day)** — tägliche rotierende Nachricht ganz oben auf der Home-Seite; deterministisch per Datum (gleiche Nachricht den ganzen Tag), Weiterschalten per `→`-Button (HTMX, kein Reload); Offset in Redis gespeichert (läuft um Mitternacht ab)
- **MOTD CRUD** — `GET/POST /motd`, `/motd/new`, `/motd/{id}/edit`, `/motd/{id}/delete`; Nachrichten mit `active`-Flag (deaktivierbar ohne Löschen)
- **Mass Import** — `GET /motd/import`: Textarea (eine Zeile = eine Nachricht) + Datei-Upload (`.txt`); ein git-Commit für den gesamten Import
- **Home-Widget** — HTMX lazy-load (`/api/home/motd`); accent-farbiger linker Rand; Weiter-Button direkt im Widget
- **Module-Toggle + Repo Assignment** — wie alle anderen Module in Settings konfigurierbar
- **Online-Hilfe** — `GET /help/motd`; `?`-Button in der List-Page
- **32 Unit-Tests** — Storage (CRUD, bulk_import, get_daily, active-Filter), Router (list, create, edit, delete, import, next)

---

## 2026-04-29 — Bulk-Aktionen, Favoriten, Audit-Log, Repo-Gesundheitscheck

### Added
- **Bulk-Delete** — "Select" button on all list pages (Tasks, Notes, Links, Snippets, Runbooks); multi-select checkboxes; floating action bar; single git push per bulk operation
- **Favoriten** — star button (HTMX toggle, no page reload) on all list entries; `favorites.yaml` stored in primary git repo; Home dashboard shows pinned favorites with module badge and direct link
- **Audit Log** — `GET /audit` shows all git commits across repos, filterable by module, author, and date range; each commit grouped with author, timestamp, subject, short hash, and per-change badges (Added / Modified / Deleted); nav link in sidebar; `?` help page
- **Repo Health Check** — "Health" button per repo in Settings; shows reachability, last commit timestamp (warning if >24h), file count, and commit count for the past 7 days; uses HTMX, no page reload

---

## 2026-04-25 — Theme Mode, Help System, Search Highlighting, Quick-Capture Modal

### Added
- **Theme mode setting** — Settings → Appearance: choose Dark, Light, or Auto (follows OS `prefers-color-scheme`); persistent in `settings.json`; navbar toggle still works as session override; live OS change listener when in Auto mode
- **Help System Stufe 1 — Feld-Hinweise** — `field-hint` texts on all form fields across Knowledge, Tasks, Notes, Links, Runbooks, Snippets, Mail Templates, Ticket Templates, Appointments and Vacations; no JS, no backend
- **Help System Stufe 2 — Modul-Hilfeseiten** — `GET /help/{module}` renders markdown help files from `app/help/`; `?` help button in all module list page headers; 10 help files covering all modules
- **Help System Stufe 3 — `?`-Shortcut** — pressing `?` anywhere (not in input) navigates to the help page of the current module
- **Filter search by date** — global search accepts `date_from` and `date_to` query params; date range filter row below search input; "(filtered by date)" indicator in result count; entries filtered by `created` field (Knowledge, Tasks, Notes, Links, Runbooks, Snippets) or `start_date` (Vacations, Appointments)
- **Search result highlighting** — matching text shown as context snippet below each result title with `<mark>` highlighting; Knowledge (body), Tasks (description), Notes (body), Runbooks (description + steps), Snippets (description + commands)
- **Quick-Capture Modal** — press `q` anywhere (not in input) to open a floating modal; type tabs for Knowledge (redirects to /knowledge/new with prefilled fields), Tasks, Notes, Links, Snippets; saves directly via POST; success toast appears on save; Esc closes

---

## 2026-04-25

### Added

**Modules**
- **Notes module** — Subject + Body; list with global search; detail with in-note search (highlight + keyboard navigation); configurable scroll position; toggleable; repo assignment; included in Operations and global search
- **Links module** — bookmarks with free-text category + `<datalist>` autocomplete; list grouped by category with filter badges; full-text search; copy-URL button; toggleable; repo assignment; included in Operations and global search
- **Runbooks module** — ordered steps (Title + Body); session checklist (`sessionStorage`), progress bar and reset; step body copy-to-clipboard; dynamic add/remove/reorder; toggleable; repo assignment; included in Operations and global search
- **Snippets module** — title + description + arbitrary steps (description + command); full-text search; copy-per-command in list and detail; dynamic step form with "+ Add Command" below last step, first textarea pre-focused; toggleable; repo assignment; included in Operations and global search
- **Mail Templates module** — To/CC/Subject/Body; one-click copy-to-clipboard; toggleable; repo assignment; included in Operations
- **Ticket Templates module** — Description/Body; one-click copy-to-clipboard; toggleable; repo assignment; included in Operations
- **Appointments module** — create/edit/delete whole-day appointments; types: Training, Conference, Team Event, Business Trip, Other (each with icon); list with year navigation + inline add form; monthly calendar; Appointment ICS export profiles (same options as vacation profiles, `{title}`, `{type}`, `{note}`, `{start_date}`, `{end_date}`, `{days}` placeholders); toggleable; repo assignment; included in Operations
- **Operations module** — copy or move any content type (Knowledge, Tasks, Vacations, Appointments, Mail Templates, Ticket Templates, Notes, Links, Runbooks, Snippets) between repos; batch selection with category-level checkboxes for Knowledge; `🔀 Ops` nav link visible when 2+ repos configured
- **Operations: ZIP Export/Import** — export all YAML/MD/TXT files from a repo as a ZIP (`daily-helper_{repo}_export.zip`); import ZIP with Merge (keep existing) or Overwrite (replace all) mode; path-traversal protection; changes committed to git automatically
- **Global search** — `GET /search?q=` queries all enabled modules simultaneously; results grouped by module with icon and "View all →" link; up to 10 items per group; total count shown; per-module exceptions isolated; navbar search input (expands on focus, `/` shortcut); hidden on mobile

**Knowledge**
- **File attachments** — upload files to any knowledge entry (max 25 MB); download links on detail page; stored in git at `knowledge/{category}/{slug}/{filename}`; deleted with entry; `_safe_filename()` prevents path traversal
- **Category name validation** — `/` blocked in new category names (frontend `pattern` + backend redirect with error)
- **Category-only search** — selecting a category filter with an empty query returns all entries in that category (`GET /knowledge/search?category=X`)

**Notes**
- **Archive / Restore** — archive a note to move it out of the active list; `/notes/archive` page with restore button; stored in `notes/archive/{id}.yaml`; `list_committed` is non-recursive so archived notes never appear in the active list
- **Line numbers** — toggleable in Settings → Notes; both detail view and edit form show a scroll-synced gutter; Tab key inserts 2 spaces; ResizeObserver keeps gutter height in sync
- **Jump buttons** — "↓ End" at top and "↑ Top" at bottom of detail view for one-click navigation in long notes
- **Full-width on desktop** — detail and edit expand to full available width on screens wider than 768 px
- **Double-click to edit** — single click opens detail, double-click navigates directly to edit form; `window.getSelection().removeAllRanges()` prevents text-selection from blocking navigation
- **Note encryption** — individual notes encrypted at rest with Fernet; `encrypt` checkbox on form; storage saves `enc:<base64>` + `encrypted: true`; detail/list/search always receive plaintext (transparent decrypt)
- **Cursor-at-end** — edit form positions cursor at end of body textarea via `setSelectionRange(len, len)` after focus

**Tasks**
- **Task search** — search bar on `/tasks` filters open and done tasks by title and description via `GET /tasks?q=`; clear button; result count shown
- **Task deadlines in calendar** — open tasks with a due date appear as ✅ markers on the calendar day; high-priority tasks flagged 🔴; legend entry added when tasks are present
- **Success flash** — creating or updating a task redirects to `/tasks?saved=1` with a "Task saved." banner

**Vacations**
- **Vacation mail template** — configure a reusable vacation request email in Settings → Vacation → Mail Template (To, CC, Subject, Body); placeholders `{{from}}`, `{{to}}`, `{{working_days}}` replaced at use time; 📧 button on each vacation card when a template is configured; mail preview page (`GET /vacations/{id}/mail`) shows all fields with copy-to-clipboard buttons, "Open in Mail Client" `mailto:` link and "Download .eml" button
- **Vacation EML export** — `GET /vacations/{id}/mail.eml` generates an RFC 2822 `.eml` with placeholders replaced; opens as draft in Outlook, Thunderbird and Apple Mail
- **Sprint capacity bars** — `/calendar/capacity` shows three progress bars per sprint: Gesamt (total work days, Bitcoin Orange), Verfügbar (after vacations/holidays/blocked appointments), Verbleibend (remaining from today); all relative to Gesamt = 100%; auto-scroll to current sprint on load
- **Calendar: hide weekends** — "Show weekends in calendar" in Settings → Vacation; when disabled, calendar renders a 5-column Mon–Fri grid

**Calendar**
- **Central Calendar module** — unified `/calendar` aggregating public holidays, vacations and appointments in a single monthly grid; event list below the grid; `/vacations/calendar` and `/appointments/calendar` redirect 301 to `/calendar`; Calendar nav tab visible when Vacations or Appointments enabled
- **Cross-calendar display** — Vacation calendar shows appointment markers (📆); Appointments calendar shows vacation entries (🏖); both show public holidays
- **Today highlight** — current day shown with red background, red border and bold red day number in all calendar views

**History**
- **History module** — `/history` filterable git log of all changes; tabs: Today / This Week / This Month / 30d / 90d / 365d / All; deleted entries strikethrough (no link); Redis-cached per range (60–600 s); HTMX tab switching
- **Entry-Versionshistorie (all modules)** — every object has a `/history` page with the full `git log --follow` of its file; commit list with SHA, date, author and message; each entry is expandable showing the unified diff; History button on Knowledge entries, Notes, Tasks (form), Runbooks (detail), Snippets (detail), Mail Templates (list), Ticket Templates (list); `GitStorage.get_file_history()` and `get_file_diff()` with SHA validation against injection; shared partial `partials/history_view.html` for all modules

**Settings & Auth**
- **Module toggle** — enable/disable each module individually in Settings; disabled modules hidden from nav and blocked at route level (HTTP 404)
- **Module repo assignment** — assign any subset of repos to each module; Knowledge aggregates reads across all assigned repos; all other modules write to primary repo; backward-compatible fallback
- **Repo enable/disable** — toggle any repo on/off without removing it; `enabled` flag in `settings.json` defaults to `true`
- **Encrypted settings export/import** — exported as password-protected `.dhbak` binary (PBKDF2-SHA256, 480 000 iterations, Fernet AES-128); password required on import; legacy `.json` imports still accepted; **Backup to Repo** action commits encrypted settings to any configured git repo under `settings-backup/settings.dhbak`; `core/crypto.py` implements `encrypt_export` / `decrypt_export` / `is_encrypted`
- **ICS export profiles** — create/edit named ICS export profiles (subject template, body template, show-as free/oof, all-day vs. timed, optional attendees, calendar category); profiles editable inline; exported filename includes date range
- **Link Sections** — links organized into independent named sections (Work, Personal, …), each in its own `links/{section_id}/` subdirectory; section dropdown in Links list when 2+ sections configured; existing flat `links/*.yaml` data migrated automatically to `links/default/` on first access (`modules/links/migration.py`, lazy + idempotent)
- **Per-section Floccus credentials** — each link section can independently enable Floccus browser sync with its own username + password (Fernet-encrypted); authentication matches HTTP Basic Auth username against all enabled sections; Settings → **Link Sections** replaces former "API Sync" fieldset
- **Floccus Login Flow v2 — credential form** — grant page shows HTML login form instead of auto-approving; wrong credentials return 401 with form; poll endpoint returns 404 until form submitted successfully
- **Floccus Server URL hint** — Settings → Link Sections always shows `window.location.origin` at top of fieldset without opening a section
- **Force sync** — "Force sync" button in Settings resets pull throttle for all git stores and flushes Redis cache; useful when remote changes are not reflected after cache flush alone
- **Copy Repo** — "Copy" button in Settings per repo clones config (URL, auth, CA cert, PAT, etc.) to a new entry with a different URL
- **URL uniqueness validation** — adding or updating a repo with a URL already in use shows a validation error
- **Test Connection diagnostics** — runs `git ls-remote` + write test via temp branch; shows full diagnostic table: auth mode, platform, PAT/CA cert/SSH key presence, git read/write access, API access, effective URL, raw git output
- **API scope check** — "Check Permissions" output shows whether the PAT has API read scope; documents required PAT scopes per platform
- **Repo card badges** — Settings repo list shows inline badges: 🔐 CA cert, 🔑 GPG key, 👤 custom identity
- **Home repo badges** — Home dashboard repo list shows the same CA cert / GPG key / identity badges
- **Basic Auth** — new auth mode: username + password Fernet-encrypted, passed to git via temporary `GIT_ASKPASS` script in RAM-only tmpfs; never embedded in URLs or process arguments
- **push_retry_count per repo** — configurable in Settings → Repo Edit (0–10, default 1); `GitStorage._commit_and_push()` retries with `git pull --rebase` on push rejection due to concurrent writes
- **Sync button per repo** — "Sync" button triggers `POST /settings/repos/{id}/sync`; force-resets `_last_pull = 0` + immediate `git pull --rebase`; result shown in diagnostic area

**UI / UX**
- **Desktop sidebar navigation** — module links in a permanent 220 px left sidebar on desktop; active module highlighted; hidden on mobile (≤ 768 px); top navbar shows only hamburger, brand, Ops shortcut, Settings and theme toggle
- **Mobile drawer** — sidebar slides in from left as overlay drawer (≤ 768 px); hamburger button (☰) toggles; overlay click and Escape close; links inside close automatically
- **Mobile toolbar** — editor toolbar scrolls horizontally on small screens; scrollbar hidden
- **Home: recent activity** — home dashboard shows "New Entries" (last 10 added) and "Recent Changes" (last 10 modified); loaded asynchronously via `GET /api/home/recent`
- **Home tiles sorted alphabetically** — stat cards ordered A–Z (Appointments, Knowledge, Links, Mail templates, Notes, Runbooks, Tasks, Ticket templates, Vacations), followed by Repositories and Total
- **Pinned entries** — `☆ Pin` / `★ Pinned` HTMX toggle on entry pages; pinned entries appear in a dedicated section at top of home page and highlighted in category view; `pinned: true` in frontmatter, preserved on edit
- **Pagination** — category view: 20 entries per page; Previous/Next navigation; page indicator in header
- **Entry templates** — dropdown in New Entry with 4 presets: How-To, Troubleshooting, Cheatsheet, Meeting Notes; fills editor with starter Markdown
- **Custom entry templates** — full CRUD section in Settings; stored in `settings.json`; appear in an optgroup in New Entry dropdown; use same WYSIWYG editor as entry forms
- **Repo-aware category filter** — category dropdown in New Entry hides categories from other repos when a repo is selected; no extra API call
- **Settings sticky nav active-section** — IntersectionObserver highlights current section link in sticky subnav; active link scrolled horizontally into view; `window.__settingsSetActive` exposed for E2E testing
- **Dark/light theme toggle** — ☀️/🌙 in navbar; preference saved in `localStorage`; anti-flash inline script in `<head>`
- **Keyboard shortcuts** — `/` focuses search, `n` → New Entry, `e` → Edit (when on an entry page); inactive when an input is focused
- **Syntax highlighting** — highlight.js applied to code blocks and live preview; theme-aware, re-applied after every HTMX swap
- **Search category filter** — dropdown next to search box; filters without full page reload (HTMX)
- **Redis stats in footer** — `⚡ N keys · X% hits`; auto-refreshes every 30 s via HTMX
- **Today highlight in calendar** — current day shown with red background + border + bold day number
- **MIT License** — `LICENSE` file added; referenced in GitHub publish workflow
- **GitHub mirror + GHCR** — repo mirrored to `github.com/romi1981/daily-helper`; image pushed to `ghcr.io/romi1981/daily-helper:latest` on every `main` build

**Testing**
- **E2E test suite (Playwright)** — session-scoped uvicorn fixture with real SSH git repo; auto-skipped without deploy key; 76 layout tests (19 pages × 2 viewports × 2 checks) in `test_responsive_layout.py` detecting horizontal overflow and key-element visibility; per-entry history tests for Tasks, Notes, Runbooks, Snippets; ZIP export/import tests; Notes double-click test; E2E test run time cut from 22+ min to ~2:15 (pull throttle + 60 s timeouts + session-scoped seed data)
- **Integration test suite** — `test_storage_integration.py`: 78 tests against a real git repo via SSH deploy key; covers all storage modules; auto-skip without key; CI passes key via `TEST_DEPLOY_KEY_PRIVATE` secret
- **605 unit + integration tests, ~80% coverage** — `operations/router.py` at 100%, `main.py` at 96%

### Changed

- **Desktop navigation layout** — module links moved from navbar tabs to persistent left sidebar; navbar area simplified
- **Storage read path** — all module reads (`list_committed`, `read_committed`) fetch data from `origin/main` via `git show` / `git ls-tree` instead of working tree; write operations still pull first; `_ensure_fetched()` throttles remote fetches
- **Appointments storage** — `list_entries()` / `get_entry()` use `list_committed()` / `read_committed()` (git-object reads); only write operations pull before writing
- **Home-page counts** — module tile counts use `list_committed()` (single `git ls-tree` per module) instead of loading and parsing all YAML files
- **Tasks: done/ subdirectory** — completed tasks stored in `tasks/done/{id}.yaml`; home dashboard tile counts only open tasks; `get_task` and `delete_task` check both locations transparently
- **Links: home count fix** — link count uses recursive file listing so all sections are counted correctly
- **Navigation module tabs** — sorted alphabetically; Home pinned top; Calendar tab added between Appointments and Knowledge
- **Vacation ICS Export Profiles** — renamed to *Vacations ICS Export Profiles* in Settings to distinguish from Appointment profiles
- **Settings page** — fully translated to English (TLS section, System section, all hints and buttons)
- **CI: E2E tests merged into main build workflow** — `test` (unit) and `e2e` (Playwright) run in parallel; `build` job has `needs: [test, e2e]`; standalone `e2e.yml` workflow removed
- **Preview debounce** — editor preview now debounced at 300 ms instead of firing on every keystroke
- `static/editor.js` — shared editor logic extracted from `new.html` and `edit.html`; supports multiple independent instances per page via `.editor-container` scoping
- `image/Dockerfile.test` — dedicated test image (Python 3.12-slim + requirements + pytest)
- `TESTING.md` — documents what is tested, how to run locally, how to add new tests

### Fixed

- **Operations: Export/Import on mobile** — two cards stacked on narrow screens via `grid-template-columns: repeat(auto-fit, minmax(280px, 1fr))`
- **Date validation in Vacations and Appointments** — `create_vacation`, `update_vacation`, `create_appointment`, `update_appointment` return HTTP 400 if `end_date < start_date`
- **Notes always empty in production** — `list_committed` was returning `notes/abc.yaml` instead of `abc.yaml` due to double-directory prefix in `git ls-tree` output; fixed by stripping the prefix in `list_committed`
- **Knowledge categories with prefix** — `get_categories()` had the same double-prefix bug; fixed consistently
- **Remote URL stale on PAT change** — `git remote set-url` is now called before every pull so a changed PAT takes effect immediately
- **GPG signing robustness** — key accessibility verified before signing; falls back to unsigned commit on failure
- **Working tree revert on failed push** — working tree reverted to avoid leaving uncommitted data changes behind
- **Write-permission enforcement** — `update_entry` and `delete_entry` return 403 for read-only repos
- **Empty content** — creating or editing an entry with empty content redirects back with an error banner
- **Git error sanitization** — credentials in URLs stripped from error messages before reaching the client (`https://token@host` → `https://***@host`)
- **Preview rate-limit** — `/api/preview` limited to 20 requests per 10 seconds per IP (HTTP 429)
- **E2E: strict mode violations** — ambiguous locators fixed with `exact=True`, `.first`, value-attribute selectors and scoped locators
- **E2E: Operations confirm dialog** — `page.on("dialog", ...)` registered before submit click
- **E2E: Vacation/Appointment year filter** — test dates changed to current year so entries appear in the default year view

### Security

- **XSS** — Markdown output sanitized with `bleach`; embedded `<script>` and other dangerous tags stripped
- **Path Traversal** — category names validated against `../`, absolute paths and empty strings before any directory is created
- **URL scheme validation in Links** — `create_link` and `update_link` reject URLs not in the allowlist (`http`, `https`, `ftp`, `ftps`, `mailto`, `ssh`, `git`) with HTTP 400; prevents `javascript:` XSS payloads from being stored
- **Redis reconnect** — cache module retries connection every 30 s after failure instead of staying permanently disabled
- **tmpfs for credentials** — `GIT_ASKPASS` scripts and GPG homedirs live in `DATA_DIR/run/` mounted as tmpfs; never written to `/tmp`
- TLS/HTTPS with three modes: HTTP only, self-signed (generate), custom CRT+KEY; CA cert download + copy; browser import instructions; custom mode: CRT+KEY Fernet-encrypted in `settings.json`
- `GET /health` — `{"status":"ok","version":"..."}` for lightweight healthchecks
- `GET /metrics` — JSON for browsers, Prometheus text format for scrapers; toggle in Settings → System

---

## 2026-04-02

### Added
- Multi-repo support: manage multiple git repositories, each with own auth (none/SSH/PAT)
- Permission detection via platform REST API (Gitea, GitHub, GitLab) for PAT auth; SSH key probes with `git ls-remote`
- Read-only repos: searchable and viewable, no create/edit/delete
- Write repos: full access; repo selector on new entry form
- Settings: repo list with permission badges, add/edit/remove repos, per-repo "Check permissions" button
- Entry URLs now include `repo_id`: `/entries/{repo_id}/{category}/{slug}`
- Sidebar groups categories by repository name
- `permission_checker.py`: platform-specific API permission checks
- `MultiRepoStorage`: wraps multiple `GitStorage` instances, routes operations by repo_id
- Auto-migration: existing single-repo `settings.json` migrated to repos-list format on first load
- `DATA_DIR` env var replaces `DATA_LOCAL_PATH`; repos clone to `$DATA_DIR/repos/{id}`
- Edit entry: pre-filled editor at `/entries/{repo_id}/{category}/{slug}/edit`
- Edit button on entry view (only shown for writable repos)
- Copy button on code blocks in entry view (appears on hover)

### Changed
- `created` date is preserved when editing an existing entry

---

## 2026-04-01 (v2)

### Added
- Markdown editor toolbar: H1/H2/H3, Bold, Italic, Strikethrough, Inline Code, Code Block (with language prompt), List, Numbered List, Checkbox List, Blockquote, Horizontal Rule, Table (columns/rows dialog), Link
- Live preview tab in editor
- Settings page (`/settings`): repository URL, git identity, auth method
- SSH key authentication via `GIT_SSH_COMMAND`
- PAT authentication via HTTPS URL embedding (`oauth2:PAT@host`)
- Custom CA certificate for self-signed HTTPS
- SSH deploy key pair generator in settings (ed25519); public key displayed with copy button
- Public key derived from private key on settings page load
- Fernet AES-128 encryption for SSH key, PAT and CA cert in `/data/settings.json`
- Encryption key auto-generated on first start in `/data/.secret_key`
- "Test connection" button in settings (HTMX)
- Gitea Actions: `image_build.yml` (build & push), `ssh_deploy.yml` (deploy on build success), `manage.yml` (manual restart/stop/start)
- Mirror actions for all external action references
- `deploy/docker-compose.yml` for production (registry image + Traefik)
- Traefik + Let's Encrypt (automatic HTTPS via ACME)
- UID/GID 1005 in container (matches `gitea_deploy` on host)
- `gosu` in entrypoint for privilege drop after volume permission fix
- SSH key line-ending normalization (`\r\n` → `\n`) to fix OpenSSH load errors

### Removed
- `.env.example` — no configuration via environment variables needed

---

## 2026-04-01 (v1)

### Added
- Initial implementation
- FastAPI backend with HTMX frontend (dark theme)
- GitStorage driver: clones data repo, reads/writes MD files, auto-commits & pushes
- Full-text search with 300ms HTMX debounce
- Markdown editor with tab-based live preview
- Category directory tree (select or create new)
- Create, view and delete entries
- Frontmatter per entry: `title`, `category`, `created`
- Docker Compose stack with custom image build
