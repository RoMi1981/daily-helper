# Daily Helper

[![GitHub](https://img.shields.io/badge/GitHub-romi1981%2Fdaily--helper-181717?logo=github)](https://github.com/romi1981/daily-helper)

A self-hosted, git-backed daily companion for knowledge management, task tracking, vacation planning, appointment tracking, runbooks, notes, links, snippets, mail/ticket templates, a Message of the Day, a Picture of the Day and an RSS Reader. All data is stored as plain files in git repositories — human-readable, version-controlled, and usable without the frontend.

---

## Table of Contents

- [Features](#features)
  - [Knowledge Base](#knowledge-base)
  - [Tasks](#tasks)
  - [Vacation Tracker](#vacation-tracker)
  - [Mail Templates](#mail-templates)
  - [Ticket Templates](#ticket-templates)
  - [Notes](#notes)
  - [Links](#links)
  - [Runbooks](#runbooks)
  - [Snippets](#snippets)
  - [Appointments](#appointments)
  - [Central Calendar](#central-calendar)
  - [MOTD](#motd-message-of-the-day)
  - [Picture of the Day](#picture-of-the-day)
- [Memes](#memes)
  - [RSS Reader](#rss-reader)
  - [Navigation & UX](#navigation--ux)
  - [Repositories & Storage](#repositories--storage)
  - [Infrastructure](#infrastructure)
  - [Security](#security)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
  - [Settings UI](#settings-ui-settings)
- [Floccus Browser Sync](#floccus-browser-sync)
- [Data Format](#data-format)
- [Common Commands](#common-commands)
- [Testing](#testing)
- [Deployment](#deployment)

---

## Features

### Knowledge Base

| Feature | Details |
|---------|---------|
| **Markdown editor** | Toolbar (headings, bold/italic/strikethrough, inline code, code block, lists, blockquote, table, link) + live preview tab; output sanitized with `bleach` |
| **Entry templates** | 4 built-in presets (How-To, Troubleshooting, Cheatsheet, Meeting Notes) + custom templates managed in Settings |
| **Pinned entries** | Pin any entry to the top of the home page via a toggle button; stored as `pinned: true` in frontmatter |
| **Syntax highlighting** | highlight.js on all code blocks; dark/light theme-aware, applied to editor preview as well |
| **Categories** | Selectable or created on the fly; grouped by repository in the sidebar |
| **Pagination** | Category views paginate at 20 entries per page |
| **Copy button** | Appears on hover on all code blocks, copies to clipboard |

### Tasks

| Feature | Details |
|---------|---------|
| **Task management** | Create tasks with title, description, due date, priority, and recurrence |
| **Priority levels** | High / Medium / Low with color indicators |
| **Recurring tasks** | Daily / weekly / monthly recurring task support; follow-up created automatically on completion |
| **One-click toggle** | Mark tasks done/undone via checkbox (HTMX, no page reload) |
| **Bulk delete** | Select multiple tasks with checkboxes; floating action bar; single git push for the whole batch |
| **Favorites** | Star button on every entry (HTMX toggle); starred entries appear in the home dashboard favorites widget; stored in `favorites.yaml` in the primary git repo |
| **URL linking** | URLs in task descriptions rendered as clickable links |
| **Task dependencies** | Mark a task as "blocked by" one or more other open tasks; blocked badge shown in the task list until all blockers are completed; configured in the task edit form |

### Vacation Tracker

| Feature | Details |
|---------|---------|
| **Vacation requests** | Create requests with start/end date and notes |
| **Status workflow** | Planned → Requested → Approved → Documented |
| **Account overview** | Year navigation with total / used / planned / remaining day counts; configurable carryover from previous year |
| **Calendar view** | Monthly calendar showing entries and public holidays by German state/region |
| **Holiday language** | Public holiday names displayed in German or English (configurable in Settings) |
| **ICS export** | Download Outlook 365 compatible `.ics` file per vacation entry — works without any profile configured (default: all-day, Out of Office) |
| **ICS export profiles** | Named profiles in Settings → *Vacations ICS Export Profiles*; control subject/body template (placeholders: `{note}`, `{start_date}`, `{end_date}`, `{days}`), show-as (free/oof/busy), all-day vs. timed, attendees and Outlook category; filename includes date range; all configured profiles downloaded at once |
| **CSV export** | Export all entries for a year including work day calculation |
| **Mail template** | Configure a reusable vacation request email in Settings (To, CC, Subject, Body); placeholders: `{{from}}`, `{{to}}`, `{{working_days}}`; 📧 button on each vacation card opens a preview page with all fields filled and copy-to-clipboard buttons; **Open in Mail Client** generates a `mailto:` link; **Download .eml** exports an RFC 2822 file that opens directly as a new draft in Outlook, Thunderbird and Apple Mail |

### Mail Templates

| Feature | Details |
|---------|---------|
| **Template CRUD** | Create, edit, delete named mail templates with To, CC, Subject and Body fields |
| **Copy to clipboard** | One-click copy formats all fields (To / CC / Subject / Body) ready to paste into any mail client |
| **Open in mail client** | Generates a `mailto:` link with all fields pre-filled; opens the default mail client as a new draft |
| **Download .eml** | Exports an RFC 2822 `.eml` file; opens directly as a new draft in Outlook, Thunderbird and Apple Mail |

### Ticket Templates

| Feature | Details |
|---------|---------|
| **Template CRUD** | Create, edit, delete named ticket templates with Description and Body fields |
| **Copy to clipboard** | One-click copy of description + body for pasting into any issue tracker |

### Notes

| Feature | Details |
|---------|---------|
| **Note CRUD** | Create, edit, delete long-form notes with Subject and Body fields |
| **Global search** | Search across all notes by subject and body |
| **In-note search** | Highlight matching terms inside an open note; navigate matches with Enter / Shift+Enter |
| **Line numbers** | Toggleable in Settings → Notes; shown in both the detail view and the editor |
| **Jump buttons** | "↓ End" button at the top and "↑ Top" button at the bottom of the detail view for fast navigation in long notes |
| **Full-width layout** | Detail and edit views expand to full screen width on desktop |
| **Click-to-edit** | Click anywhere in the note body to switch to edit mode; selecting text is unaffected |
| **Full-height editor** | Edit form uses full viewport height — the textarea expands to fill the screen without scrolling |
| **Scroll position** | Configurable per-settings: open notes at top (start) or bottom (end) |
| **Bulk delete** | Select multiple notes with checkboxes; floating action bar; single git push for the batch |
| **Favorites** | Star button on every note; starred notes appear in the home dashboard favorites widget |

### Links

| Feature | Details |
|---------|---------|
| **Link CRUD** | Create, edit, delete bookmarks with Title, URL, Category and Description |
| **Categories** | Free-text categories with `<datalist>` autocomplete from existing values |
| **Grouped list** | Links grouped by category with filter badges; click a badge to show only that category |
| **Search** | Full-text search across title, URL and description |
| **Copy URL** | One-click copy of the link URL to clipboard |
| **Link sections** | Organize links into independent named sections (e.g. Work, Personal); each section has its own storage subdirectory and optional Floccus credentials; section selector shown when more than one section is configured; existing flat data is auto-migrated on first access |
| **Floccus sync** | [Nextcloud Bookmarks REST API v2](https://github.com/nextcloud/bookmarks) compatible endpoint — lets the [Floccus](https://floccus.org) browser extension sync bookmarks bidirectionally; each link section can have its own Floccus credentials; configure in Settings → Link Sections; see [Floccus Setup](#floccus-browser-sync) below |
| **Bulk delete** | Select multiple links with checkboxes; floating action bar; single git push for the batch |
| **Favorites** | Star button on every link; starred links appear in the home dashboard favorites widget |

### Runbooks

| Feature | Details |
|---------|---------|
| **Runbook CRUD** | Create, edit, delete runbooks with Title, Description and ordered Steps |
| **Steps** | Each step has a Title and optional body (details, commands, notes); empty-title steps are filtered out |
| **Dynamic form** | Add, remove and reorder steps in the create/edit form without page reload |
| **Session checklist** | Detail view shows a checkbox per step backed by `sessionStorage` — resets on page reload, reusable across runs |
| **Progress bar** | Visual progress indicator showing X / N steps completed |
| **Copy step body** | One-click copy of each step's body (commands, scripts) to clipboard |
| **Reset** | One-click reset of all checkboxes for a fresh run |
| **Bulk delete** | Select multiple runbooks with checkboxes; floating action bar; single git push for the batch |
| **Favorites** | Star button on every runbook; starred runbooks appear in the home dashboard favorites widget |

### Snippets

| Feature | Details |
|---------|---------|
| **Snippet CRUD** | Create, edit, delete snippets with Title, Description and ordered command steps |
| **Steps** | Each step has an optional description and a required command; empty-command steps are filtered out |
| **Dynamic form** | Add, remove and reorder steps without page reload |
| **Copy per command** | One-click copy of each command to clipboard in both list and detail views |
| **Full-text search** | Searches title, description and all commands |
| **Bulk delete** | Select multiple snippets with checkboxes; floating action bar; single git push for the batch |
| **Favorites** | Star button on every snippet; starred snippets appear in the home dashboard favorites widget |

### Appointments

| Feature | Details |
|---------|---------|
| **Appointment CRUD** | Create, edit, delete whole-day appointments with Title, Start/End Date, Type and optional Note |
| **Types** | Training 📚 · Conference 🎙 · Team Event 👥 · Business Trip ✈️ · Other 📌 |
| **Recurring appointments** | Weekly / monthly / yearly repeat; next occurrence created automatically on delete; repeat badge shown on card |
| **List view** | Year navigation; entries sorted by start date |
| **ICS export** | Download `.ics` per entry — works without any profile configured (default: all-day, Busy, subject `{title} {start_date}–{end_date}`) |
| **ICS export profiles** | Named profiles in Settings → *Appointment ICS Export Profiles* (separate from vacation profiles); placeholders: `{title}`, `{type}`, `{note}`, `{start_date}`, `{end_date}`, `{days}`; show-as (free/busy/oof), all-day vs. timed, attendees, Outlook category; all profiles downloaded at once |

### Central Calendar

Unified monthly calendar at `/calendar` aggregating all event types. Old module-specific calendar URLs redirect here (301).

| Feature | Details |
|---------|---------|
| **Unified view** | Public holidays, vacation entries and appointments in a single month grid |
| **Holiday display** | Color-coded by German state (configurable); names in German or English |
| **Vacation overlay** | Approved/documented entries shown in green; planned/requested with dashed border |
| **Appointment overlay** | Shown in indigo with type icon; covers weekends (unlike vacations which count work days only) |
| **Today highlight** | Current day highlighted with red background and bold day number |
| **Month navigation** | Previous/next month links; year + month selectable via query params |
| **Event list** | Below the grid: all holidays, vacations and appointments sorted by date with full details |
| **Legend** | Color legend showing all event types; conditional on enabled modules |
| **Holiday ICS export** | Per-holiday download button in the event list; one button triggers all configured *Holiday ICS Profiles* sequentially; profiles configured in Settings → *Holiday ICS Profiles* (subject/body with `{name}`/`{date}` placeholders, show-as, attendees, Outlook category) |

### MOTD (Message of the Day)

| Feature | Details |
|---------|---------|
| **Daily message** | One message shown at the top of the home page; rotates deterministically by date (same message all day) |
| **Next button** | HTMX button advances to the next message for today; offset stored in Redis with midnight TTL |
| **CRUD** | Create, edit, delete messages; `active` flag to deactivate without deleting |
| **Mass import** | Import from textarea (one line = one message) or `.txt` file upload; single git commit for the whole batch |
| **Duplicate detection** | Duplicate messages (case-insensitive) are detected and skipped on create and bulk import |
| **Module toggle** | Enable/disable in Settings; repo assignment like all other modules |

### Picture of the Day

| Feature | Details |
|---------|---------|
| **Daily display** | One entry from the collection shown each day on the home page; selected deterministically so the same day always shows the same entry |
| **Formats** | Images (JPG, PNG, WebP, GIF) displayed inline as `<img>`; PDFs embedded as `<iframe>` jumping to the correct page |
| **Upload** | Upload any file (max 25 MB) or fetch from URL; PDFs split into one entry per page automatically |
| **PDF thumbnails** | PDF page entries show a rendered canvas preview via PDF.js (bundled, no CDN) |
| **Next button** | Advance to the next entry on the home widget; resets at midnight |
| **Lightbox** | Click any image thumbnail to open a full-screen overlay; close with Escape or click outside |
| **Copy to clipboard** | Copy the image as PNG to the system clipboard directly from the lightbox or the list |
| **Storage** | Media files as `potd/{id}.{ext}`; PDF page sidecars as `potd/{page_id}.yaml` — all version-controlled in the data git repo |
| **Module toggle** | Enable/disable in Settings; repo assignment like all other modules |

### Memes

| Feature | Details |
|---------|---------|
| **Daily display** | One meme shown on the home page each day; same deterministic selection as PotD |
| **Formats** | Images only: JPG, PNG, WebP, GIF (max 25 MB) |
| **Upload** | Upload a file or fetch from URL |
| **Next button** | Advance to the next meme on the home widget; resets at midnight |
| **Lightbox** | Click any image thumbnail to open a full-screen overlay; close with Escape or click outside |
| **Copy to clipboard** | Copy the image as PNG to the system clipboard directly from the lightbox or the list |
| **Storage** | `memes/{id}.{ext}` in the data repo |
| **Module toggle** | Enable/disable in Settings; repo assignment like all other modules |

### RSS Reader

| Feature | Details |
|---------|---------|
| **Feed display** | Reads RSS and Atom feeds via `feedparser`; up to 50 items per feed shown with title (link), date and summary |
| **Feed management** | Add/edit/delete feeds directly on the RSS module page; feeds stored as `rss/{id}.yaml` in the data git repo |
| **Subnav** | Horizontal scrollable tab bar between feeds (sticky, active tab follows scroll) |
| **Redis cache** | Feed content cached for 15 minutes; falls back to direct fetch if Redis is unavailable |
| **Manual refresh** | ↻ button per feed forces a fresh fetch and clears the cache for that feed |
| **HTMX lazy load** | Each feed card loads independently after page render; no blocking of the page on slow feeds |
| **Module toggle** | Enable/disable in Settings; repo assignment like all other modules |

### Navigation & UX

| Feature | Details |
|---------|---------|
| **Desktop sidebar** | Persistent 220 px left sidebar on desktop (≥ 769 px) showing all module links with active-state highlighting; always visible without scrolling |
| **Mobile drawer** | Sidebar slides in as a drawer on mobile (≤ 768 px); hamburger button (☰) toggles it; overlay click and Escape key close it |
| **Full-text search** | Live search across all repositories (HTMX, 300 ms debounce); filter by category via dropdown; links open in the correct module page |
| **Global search** | `GET /search?q=` queries all enabled modules simultaneously; results grouped by module with context snippets and `<mark>` highlighting; filter by date (`date_from` / `date_to`); navbar input (expandable, `/` shortcut) |
| **Favorites** | Star button (HTMX toggle, no page reload) on all list entries across Tasks, Notes, Links, Snippets and Runbooks; starred items collected in `favorites.yaml` in the primary git repo; home dashboard shows a favorites widget grouped by module with direct links |
| **Bulk actions** | Select multiple entries with checkboxes on all list pages (Tasks, Notes, Links, Snippets, Runbooks); floating action bar shows selected count and delete action; single git push for the whole batch |
| **History** | `GET /history` shows all git commits across all repos and modules; time-range tabs (Today / This Week / This Month / 30d / 90d / 365d / All) with HTMX partial reload; filter bar for module, author, and date range; each commit shows author, timestamp, subject, short hash and per-change badges (Added / Modified / Deleted); results cached in Redis per range |
| **Help system** | Each module has a help page at `/help/{module}`; `?` button in module headers; `?` keyboard shortcut navigates to help from any module page |
| **Keyboard shortcuts** | `/` focuses search · `n` opens New Entry · `e` opens Edit · `?` opens module help · `q` opens Quick-Capture modal |
| **Quick-Capture Modal** | Press `q` to open a floating modal; type tabs for Tasks, Notes, Links, Snippets (direct POST), Knowledge (redirects to /new with prefilled fields); success toast; Esc to close |
| **Dark / light theme** | Settings → Appearance: Dark / Light / Auto (follows OS `prefers-color-scheme`); navbar toggle overrides for the current session |
| **UI language** | Settings → Appearance → Language: English / Deutsch; full UI translation (404 keys, all modules, forms, buttons, status messages); module content (entries, notes, etc.) stays in the language you write it in |
| **Offline mode** | Network push failures queue locally; background retry every 60 s; orange banner shown while changes are pending |
| **Lucide icons** | All UI icons are [Lucide SVG](https://lucide.dev/) — no icon font dependency; accent-colored in sidebar and settings |
| **Status badge** | Fixed pill (bottom-right) showing Redis key count + cache hit rate; auto-refreshes every 30 s |
| **Data export/import** | Export all settings as an **encrypted `.dhbak` backup** (PBKDF2+Fernet, password required); import accepts `.dhbak` (password-protected) or legacy `.json`; one-click **Backup to Repo** commits the encrypted backup into any configured git repository |

### Repositories & Storage

| Feature | Details |
|---------|---------|
| **Multi-repo** | Any number of git repositories; each can be public (read-only) or authenticated (read-write) |
| **Repo enable/disable** | Toggle any configured repository on or off in Settings without removing it — disabled repos are excluded from storage, search and module assignments |
| **Copy repo** | Clone an existing repo's configuration to a new entry with a different URL, inheriting all auth settings |
| **URL uniqueness** | Duplicate repo URLs are rejected at add/update time |
| **Authentication** | `none` · `ssh` (deploy key) · `pat` (Personal Access Token) · `basic` (username + password, passed via `GIT_ASKPASS`, never embedded in URLs) |
| **Custom CA cert** | Per-repo CA certificate for self-signed HTTPS remotes; available for all auth modes |
| **GPG commit signing** | Per-repo GPG private key (ASCII-armored); signs every commit with `--gpg-sign`; passphrase cached non-interactively via gpg-agent loopback |
| **Per-repo git identity** | Name + email per repo, overrides global default |
| **Permission detection** | Checks write access via Gitea/GitHub/GitLab API for PAT auth; SSH/basic probed with `git ls-remote` |
| **Pull-throttling** | `git pull` runs at most every 5 minutes per repo (configurable); reads served from `origin/main` git objects without a pull |
| **Push conflict detection** | Rejected pushes show a human-readable error instead of raw git output |
| **Write-test** | "Test Connection" performs a write test via a temporary branch in addition to `git ls-remote` |
| **Orphaned repo cleanup** | Local clones in `/tmp` for repos removed from settings are automatically deleted on the next settings reload |

### Infrastructure

| Feature | Details |
|---------|---------|
| **Redis cache** | Optional; caches git-file reads, module listings, global search results, history, and binary image files (PotD/Memes, base64, 1 h TTL); app degrades gracefully without it; auto-reconnects after Redis restart; max file size configurable in Settings → System (default 10 MB) |
| **Redis stats** | Footer shows key count + hit rate (`⚡ 42 keys · 87% hits`); auto-refreshes every 30 s |
| **Home system panel** | Home page shows Redis status + cache hit rate + key breakdown by type, `/tmp` usage bar (color-coded at 65%/85%), and local clone size per repository |
| **Home: next vacation** | Right sidebar shows next upcoming vacation start date and number of working days remaining (holidays excluded via `python-holidays`); hidden when no future vacation exists or vacations module is disabled |
| **Vacation summary** | `requested` entries count towards Planned and After planned totals (alongside `planned`) |
| **Settings: RSS** | Dedicated RSS section in Settings; configures number of home widget articles (default 3) |
| **TLS / HTTPS** | HTTP only · self-signed (CA + cert generated in-app, import CA once) · custom CRT + KEY |
| **Module toggle** | Enable/disable any module individually in Settings — disabled modules are hidden from nav and blocked at route level (404) |
| **Module repo assignment** | Assign any subset of repos to each module. Knowledge aggregates all assigned repos; all other modules write to the configured primary repo. Repos can be shared between modules. |
| **Operations** | Copy or move Knowledge, Tasks, Vacations, Appointments, Mail Templates, Ticket Templates, Notes, Links or Runbooks between repositories; visible when 2+ repos are configured; **ZIP Export** downloads all YAML/MD/TXT files of a repo as a zip archive; **ZIP Import** uploads a zip with merge or overwrite mode (path-traversal protected, auto-committed to git) |
| **Entry history** | Every object (Knowledge entries, Notes, Tasks, Runbooks, Snippets, Mail Templates, Ticket Templates) has a `/history` page showing the full git log for that file; each commit is expandable to show the unified diff; SHA validation prevents path injection |
| **Health endpoint** | `GET /health` → `{"status":"ok","version":"..."}` for Docker healthchecks |
| **Metrics endpoint** | `GET /metrics` — entry/category counts + cache status; Prometheus-compatible (`Accept: text/plain`); toggle in Settings |

### Security

- Markdown output sanitized with `bleach` — embedded `<script>` and other dangerous tags stripped
- Category names and entry slugs validated against path traversal (`../`, absolute paths, empty strings)
- Write permission enforced on edit/delete — returns 403 if repo is read-only
- Git error messages sanitized — credentials stripped from URLs before reaching the client
- Preview endpoint rate-limited (20 req / 10 s per IP)
- Secrets (SSH key, PAT, CA cert, basic password) encrypted with **Fernet AES-128** in `settings.json`
- Basic auth credentials passed via temporary `GIT_ASKPASS` script in `DATA_DIR/run/` — never in process arguments or URLs; not written to `/tmp` (which is `noexec`)
- GPG keys stored encrypted (Fernet AES-128); each repo gets an isolated `GNUPGHOME` in `DATA_DIR/run/`; passphrase cached via `allow-loopback-pinentry`

---

## Architecture

```
Browser (HTMX + highlight.js)
    │
FastAPI (uvicorn)
    ├──→ Redis (optional, cache)
    │
MultiRepoStorage
    ├── GitStorage (repo A) ──→ reads: git show origin/main
    │                      ──→ writes: pull → commit → push → Remote Repo A
    └── GitStorage (repo B) ──→ /data/repos/{id-b}/ ──→ Remote Repo B (read-only)

Settings & secrets: /data/settings.json  (Fernet-encrypted sensitive fields)
```

**Stack:** Python 3.12 · FastAPI · Jinja2 · HTMX · highlight.js · GitPython-free (subprocess-based git)

### Module structure

```
image/app/
├── main.py                         # App init, settings routes, system routes
├── core/
│   ├── state.py                    # Singleton get_storage() / reset_storage()
│   ├── storage.py                  # GitStorage + MultiRepoStorage
│   ├── settings_store.py           # Fernet-encrypted settings persistence
│   ├── module_repos.py             # Module→repo assignment helpers
│   ├── permission_checker.py       # Platform API permission checks
│   ├── cache.py                    # Graceful Redis wrapper
│   ├── templates.py                # Central Jinja2 instance with globals
│   ├── tls.py                      # TLS certificate generation/parsing
│   └── prepare_tls.py              # Entrypoint TLS setup
└── modules/
    ├── knowledge/router.py
    ├── tasks/{router,storage}.py
    ├── vacations/{router,storage,holidays_helper,ics_generator}.py
    ├── appointments/{router,storage,ics_generator}.py
    ├── calendar/router.py
    ├── notes/{router,storage}.py
    ├── links/{router,storage}.py
    ├── runbooks/{router,storage}.py
    ├── mail_templates/{router,storage}.py
    ├── ticket_templates/{router,storage}.py
    ├── motd/{router,storage}.py
    ├── potd/router.py
    ├── memes/router.py
    └── operations/router.py
```

---

## Quickstart

No build required — pull the image directly from GHCR:

```bash
curl -O https://raw.githubusercontent.com/romi1981/daily-helper/main/examples/docker-compose.yml
docker compose up -d
```

App is available at **http://localhost:8080**. Open **Settings** (`/settings`) to add your first repository.

> To build from source instead: `git clone` the repo and run `docker compose up -d --build` from the root.

---

## Configuration

Everything is configured through the Settings UI. No environment variables are required to get started.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/data` | Directory for `settings.json` and repo clones |
| `SECRET_KEY` | *(auto-generated)* | Fernet key for encrypting secrets; auto-created at `$DATA_DIR/.secret_key` if not set |
| `REDIS_URL` | `redis://redis:6379` | Redis connection URL; caching skipped silently if unreachable |
| `PULL_THROTTLE_SECONDS` | `300` | Minimum seconds between `git fetch` calls per repo |
| `PUID` | `1005` | UID of the `appuser` process; adjusted at container startup via `usermod` |
| `PGID` | `1005` | GID of the `appuser` process; adjusted at container startup via `groupmod` |

### Settings UI (`/settings`)

**Repositories**
- Add any number of git repos with a name, URL and platform type (`gitea`, `github`, `gitlab`, `generic`)
- Auth method: `none` (public), `ssh` (paste or generate an ed25519 deploy key), `pat`, or `basic` (username + password)
- **Check Permissions** — queries the platform API and updates the read/write badge
- **Test Connection** — runs `git ls-remote` + a temporary write-test branch and displays a full diagnostic table
- **Generate SSH Key** — creates an ed25519 key pair; copy the public key and add it as a deploy key in your git host
- **Copy** — clones the repo configuration to a new entry with a different URL
- Enable/disable any repo without removing it

**Modules** — enable/disable any module individually; assign repos per module

**Entry Templates** — add, edit, and delete custom Markdown templates; templates appear alongside the 4 built-ins in the New Entry dropdown

**Git Identity** — name and email used for all commits (global default; overridable per repo)

**TLS / HTTPS**

| Mode | Description |
|------|-------------|
| HTTP only | Default, no TLS |
| Self-signed | App generates a CA + server cert; import `ca.crt` into your browser once |
| Custom | Paste your own CRT + KEY (e.g. from a wildcard certificate) |

Requires an app restart after changing the TLS mode.

**Vacation Settings** — days per year, carryover from previous year, German state for public holidays (all 16 Bundesländer), holiday display language (German / English); **Mail Template** for vacation requests (To, CC, Subject, Body with placeholders `{{from}}`, `{{to}}`, `{{working_days}}`)

**Notes Settings** — default scroll position (start / end); line numbers toggle

**Vacations ICS Export Profiles** — named profiles for vacation `.ics` downloads; each profile controls subject/body template, show-as, all-day vs. timed, attendees, Outlook category; profiles editable inline; filename includes date range

**Appointment ICS Export Profiles** — same structure as vacation profiles but separate; default show-as: Busy

**Link Sections** — named sections for the Links module (e.g. Work, Personal); each section has its own storage subdirectory (`links/{section_id}/`) and optional Floccus credentials (`floccus_username` / `floccus_password`, Fernet-encrypted); the "Default" section is auto-created on first access; existing flat `links/*.yaml` data is migrated automatically; section dropdown appears when more than one section is configured

**Data Export / Import** — export all settings as an encrypted `.dhbak` file (password required; PBKDF2-SHA256 + Fernet AES-128); import detects the format automatically — `.dhbak` requires the password, unencrypted `.json` (legacy) is still accepted; **Backup to Repo** encrypts the current settings and commits them to a selected git repository under `settings-backup/settings.dhbak`

**System** — flush Redis cache, restart the app

---

## Floccus Browser Sync

[Floccus](https://floccus.org) is an open-source browser extension (Chrome, Firefox, Edge) that syncs bookmarks to various backends. Daily Helper implements the [Nextcloud Bookmarks REST API v2](https://github.com/nextcloud/bookmarks) so Floccus can sync directly with your Links module — bidirectionally, across browsers and devices.

### Setup

**1. Configure credentials in Daily Helper**

Go to **Settings → Link Sections** and edit (or create) the section you want to sync. Enable Floccus sync and set a username and password for that section. The page shows the Nextcloud URL to paste into Floccus once configured. Each section can have its own independent credentials — useful for syncing different bookmark sets from different browser profiles.

**2. Install Floccus**

Install the [Floccus extension](https://floccus.org) from your browser's extension store.

**3. Add account in Floccus**

- Open Floccus → **Add account**
- Server type: **Nextcloud Bookmarks**
- Nextcloud URL: `https://your-daily-helper-instance.example.com` (the base URL shown in Settings)
- Username + Password: the API credentials from step 1
- Floccus opens a confirmation tab ("✅ Daily Helper — Authorized") and connects automatically

**4. Configure sync folder**

Select which browser bookmark folder to sync and hit **Sync**.

### How it works

Floccus maps bookmark **folders** to daily-helper **categories**: a bookmark in the folder `Work/Projects` gets the tag `Work` as its category (the `floccus:` folder-path tags are filtered out automatically). Sub-folder hierarchy is flattened — daily-helper has a single category level.

### Implemented API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/index.php/login/v2` | Nextcloud Login Flow v2 — issues a pre-approved token |
| `POST` | `/index.php/login/v2/poll` | Returns credentials for the issued token |
| `GET` | `/ocs/v2.php/cloud/capabilities` | Capabilities stub required by Floccus |
| `GET` | `/index.php/apps/bookmarks/public/rest/v2/bookmark` | List bookmarks (paginated, `page` + `limit`) |
| `POST` | `/index.php/apps/bookmarks/public/rest/v2/bookmark` | Create bookmark |
| `PUT` | `/index.php/apps/bookmarks/public/rest/v2/bookmark/{id}` | Update bookmark |
| `DELETE` | `/index.php/apps/bookmarks/public/rest/v2/bookmark/{id}` | Delete bookmark |
| `GET` | `/index.php/apps/bookmarks/public/rest/v2/folder` | Root folder list |
| `GET` | `/index.php/apps/bookmarks/public/rest/v2/folder/{id}/children` | Folder children (always empty — no sub-folders) |
| `GET` | `/index.php/apps/bookmarks/public/rest/v2/folder/{id}/hash` | Change-detection hash (MD5 of sorted bookmark IDs) |
| `POST/PUT` | `/index.php/apps/bookmarks/public/rest/v2/folder/{id}` | Create/update folder stubs (no-op, returns root) |
| `DELETE` | `/index.php/apps/bookmarks/public/rest/v2/folder/{id}` | Delete folder — removes all bookmarks in that category from the data repo |
| `PATCH` | `/index.php/apps/bookmarks/public/rest/v2/folder/{id}/childorder` | Child order stub (no-op) |
| `POST` | `/index.php/apps/bookmarks/public/rest/v2/lock` | Sync lock (always succeeds) |
| `DELETE` | `/index.php/apps/bookmarks/public/rest/v2/lock` | Sync unlock |

### Data mapping

| Floccus / Nextcloud | Daily Helper Links |
|---------------------|--------------------|
| `id` | `id` |
| `url` | `url` |
| `title` | `title` |
| `description` | `description` |
| `tags` | `category` (first non-`floccus:` tag) |
| `folders` | always `[-1]` (root) |

### Authentication

All bookmark API requests use **HTTP Basic Auth**. The incoming username is matched against all enabled link sections — the matching section's storage is used for every operation. If no section matches, 401 is returned; if no section has Floccus enabled, 503 is returned.

The initial login uses the [Nextcloud Login Flow v2](https://docs.nextcloud.com/server/latest/developer_manual/client_apis/LoginFlow/index.html): Floccus posts to `/index.php/login/v2`, receives a poll token, and polls until credentials are returned. Daily Helper pre-approves the token using the **first enabled section** — no user interaction is needed. For additional sections (beyond the first), configure Floccus to use Basic Auth credentials directly instead of Login Flow v2.

### Permission Logic

| Auth mode | Read | Write |
|-----------|------|-------|
| none | ✓ (public repo) | ✗ |
| ssh | detected via `git ls-remote` | assumed ✓ if reachable |
| pat | via platform API (`repo` / `repository` / `read_api` scope) | via platform API |
| basic | detected via `git ls-remote` | assumed ✓ if reachable |

---

## Data Format

Knowledge entries are Markdown files with YAML frontmatter:

```markdown
---
title: Docker Tips
category: DevOps
created: 2026-04-01
pinned: true
---

## Common Commands

...
```

All other modules store their data as YAML files in named subdirectories:

```
your-data-repo/
├── knowledge/
│   ├── DevOps/
│   │   ├── docker-tips.md
│   │   └── k8s-cheatsheet.md
│   └── Python/
│       └── async-patterns.md
├── tasks/                    # tasks/{id}.yaml
├── vacations/
│   └── entries/              # vacations/entries/{id}.yaml
├── appointments/
│   └── entries/              # appointments/entries/{id}.yaml
├── notes/                    # notes/{id}.yaml
├── links/                    # links/{id}.yaml
├── runbooks/                 # runbooks/{id}.yaml
├── mail_templates/           # mail_templates/{id}.yaml
└── ticket_templates/         # ticket_templates/{id}.yaml
```

Files are human-readable and the repository works as a standalone archive without the frontend.

---

## Testing

**~750 tests** across unit tests, router integration tests, a real-git integration suite and 60 Playwright E2E browser tests.

```bash
# With Docker (matches production environment exactly)
docker build -f image/Dockerfile.test -t daily-helper-test image/
docker run --rm daily-helper-test

# Without Docker
cd image && pip install -r requirements.txt pytest httpx
python -m pytest tests/ -v --ignore=tests/test_storage_integration.py
```

Tests run automatically on every push and pull request via Gitea Actions. See [TESTING.md](TESTING.md) for full details.

---

## Deployment

The CI workflow builds and tests on every push, then publishes the image to GHCR:

| Step | Trigger | Details |
|------|---------|---------|
| Tests | every PR + push | `image/Dockerfile.test` → pytest (unit + integration + E2E) |
| Image build | push to `main`/`dev` (paths: `image/**`) | Docker Buildx; `:latest` for `main`, `:dev` for `dev` |
| Publish | after image build on `main` | `image/`, `examples/`, public README → GitHub; image → GHCR |

### Docker Image

```bash
# GitHub Container Registry (public)
docker pull ghcr.io/romi1981/daily-helper:latest

# Run
docker compose up -d
```

After deployment: open `/settings` and add your repositories.
