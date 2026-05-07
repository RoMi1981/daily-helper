# Daily Helper — User Guide

This guide explains how to use Daily Helper day-to-day. For installation and configuration see the main [README](../README.md).

---

## Table of Contents

- [Navigation](#navigation)
- [Knowledge Base](#knowledge-base)
- [Tasks](#tasks)
- [Notes](#notes)
- [Links](#links)
- [Runbooks](#runbooks)
- [Snippets](#snippets)
- [Mail Templates](#mail-templates)
- [Ticket Templates](#ticket-templates)
- [Vacations](#vacations)
- [Appointments](#appointments)
- [Calendar](#calendar)
- [MOTD (Message of the Day)](#motd-message-of-the-day)
- [Picture of the Day](#picture-of-the-day)
- [Memes](#memes)
- [RSS Reader](#rss-reader)
- [History](#history)
- [Search](#search)
- [Operations](#operations)
- [Settings](#settings)
- [Keyboard Shortcuts](#keyboard-shortcuts)

---

## Navigation

Daily Helper uses a **persistent sidebar** on desktop (≥ 769 px) listing all enabled modules. On mobile a **hamburger button** (☰) opens a slide-in drawer with the same links.

The **top navbar** contains:
- **☰** — opens the mobile drawer
- **Brand** — link to home dashboard
- **Search bar** — global search across all modules; press `/` to focus
- **🔀 Operations** — visible when 2+ repositories are configured
- **⚙ Settings** — application settings
- **☀️ / 🌙** — theme toggle (session override; persistent theme mode is set in Settings → Appearance)

The **home dashboard** shows a tile per enabled module with the current entry count, a repository overview, a "New Entries / Recent Changes" section, and a **System** panel at the bottom.

When the Vacations module is enabled and a future vacation exists, a **Next Vacation** block appears in the right sidebar showing the number of working days remaining until the start date (public holidays excluded based on the configured state) and the date range.

The System panel shows:

- **Redis** — connection status, total key count, cache hit rate, and a breakdown of cached key types (file, ls, search, history, rss, etc.)
- **/tmp usage** — a color-coded progress bar showing tmpfs utilisation (turns orange above 65 %, red above 85 %)
- **Repository clone sizes** — each enabled repository shows its local clone size on disk next to the hard-drive icon
- **App version**

---

## Knowledge Base

The Knowledge Base stores structured Markdown entries organized in categories.

### Creating an Entry

1. Click **New Entry** in the sidebar or press `n`
2. Select or type a **Category** (creates the category if it doesn't exist)
3. Choose a **Repository** if you have more than one configured
4. Optionally select an **Entry Template** (How-To, Troubleshooting, Cheatsheet, Meeting Notes or any custom template)
5. Enter a **Title** and write the **Content** using the Markdown editor
6. Switch between **Edit** and **Preview** tabs at any time
7. Click **Save**

### Editing an Entry

Open an entry and click **Edit** (only available for writable repositories), or press `e`.

### Markdown Editor Toolbar

| Button | Effect |
|--------|--------|
| H1 / H2 / H3 | Heading levels |
| **B** | Bold |
| *I* | Italic |
| ~~S~~ | Strikethrough |
| `code` | Inline code |
| `⌨` | Code block (prompts for language) |
| List / OL / ✓ | Bullet, numbered or checkbox list |
| `"` | Blockquote |
| `—` | Horizontal rule |
| Table | Insert table (prompts for rows and columns) |
| Link | Insert hyperlink |

### Pinning Entries

Click **☆ Pin** on any entry to pin it. Pinned entries appear in a dedicated section at the top of the home page and are visually highlighted in category view. Click **★ Pinned** to unpin.

### File Attachments

On the entry detail page click **Upload file** to attach files (max 25 MB each). Attached files are stored in the git repository alongside the entry and listed as download links on the detail page. Deleting an entry also deletes its attachments.

### Searching the Knowledge Base

Use the search bar in the navbar (or the search bar on the Knowledge page) to search full-text across all entries. Filter by category using the dropdown next to the search bar. Selecting a category without entering a search term returns all entries in that category.

### Entry Version History

Every entry has a **History** button. Clicking it shows a list of all commits that changed this file, with date, author and commit message. Each commit is expandable to show the exact diff (what was added / removed).

---

## Tasks

### Creating a Task

On the **Tasks** page use the quick-create form at the top: enter a title and optionally a due date, then press **Add**. For more options (description, priority, recurrence) click **New Task** to open the full form.

**Fields:**

| Field | Options |
|-------|---------|
| Title | Required |
| Description | Optional free text; URLs are rendered as clickable links |
| Due date | Optional date picker |
| Priority | High / Medium / Low |
| Recurring | None / Daily / Weekly / Monthly |

### Completing a Task

Check the checkbox on the task card. The task moves to the **Done** section. If the task is recurring, a new task is automatically created with the next due date.

### Editing and Deleting

Click the **✏ Edit** link on any task card to open the edit form. The form also has a **History** button showing all git commits for this task.

Use the **Delete** button in the edit form to remove a task permanently.

### Task Dependencies

Open a task's edit form and scroll to **Blocked by**. Check any number of other open tasks that must be completed first. A locked badge — *blocked (N)* — appears on the task card in the list as long as at least one blocker is still open. When all blockers are done the badge disappears automatically.

### Filtering

Use the search bar on the Tasks page to filter open and done tasks by title and description. The result count is shown below the search bar. Clear the filter with the **×** button.

### Bulk Delete

Click **Select** to enter selection mode. Check any number of tasks, then click **Delete selected** in the floating action bar. All selected tasks are removed in a single git commit.

### Favorites

Click the **★ star** button on any task card to mark it as a favorite. Starred tasks appear in the **Favorites** widget on the home dashboard, grouped by module.

---

## Notes

Notes are long-form documents with a subject line and a body. Unlike Knowledge entries they have no category — they are a flat list.

### Creating a Note

Go to **Notes → New Note**. Enter a **Subject** and write the **Body**. Optionally enable **Encrypt** to store the note encrypted at rest (requires the encryption key configured in the container).

### Detail View

- **In-note search** — search within the open note using the search bar at the top of the detail view; matches are highlighted; navigate with Enter / Shift+Enter
- **Double-click** anywhere in the note body to jump directly to the edit form
- **↓ End / ↑ Top** buttons for one-click navigation in long notes
- **History** button — full git log for this note file

### Archiving a Note

Click **Archive** on any note to move it out of the active list. Archived notes appear at `/notes/archive` and can be restored at any time with the **Restore** button.

### Line Numbers

Enable line numbers in **Settings → Notes**. When enabled, a synchronized gutter is shown in both the detail view and the editor. The Tab key inserts 2 spaces in the editor.

### Bulk Delete

Click **Select** to enter selection mode. Check any number of notes, then click **Delete selected** in the floating action bar.

### Favorites

Click the **★ star** button on any note in the list to mark it as a favorite.

---

## Links

Links is a bookmark manager that syncs with the [Floccus](https://floccus.org) browser extension.

### Creating a Link

Go to **Links → New Link**. Fields:

| Field | Description |
|-------|-------------|
| Title | Display name |
| URL | Must start with `http`, `https`, `ftp`, `ftps`, `mailto`, `ssh` or `git` |
| Category | Free text; autocompletes from existing categories |
| Description | Optional notes |

### Browsing and Filtering

Links are grouped by category. Click a **category badge** above the list to filter to that category. Use the **search bar** for full-text search across title, URL and description.

Click the **copy icon** next to any link to copy the URL to the clipboard.

### Bulk Delete

Click **Select** to enter selection mode. Check any number of links, then click **Delete selected** in the floating action bar.

### Favorites

Click the **★ star** button on any link to mark it as a favorite.

### Link Sections

If you have configured multiple link sections (e.g. Work, Personal) in Settings → Link Sections, a **section dropdown** appears above the link list. Each section is independent — separate storage, separate Floccus credentials.

---

## Runbooks

Runbooks are step-by-step procedures with a session-based checklist for tracking progress during execution.

### Creating a Runbook

Go to **Runbooks → New Runbook**. Enter a title and add steps with **+ Add Step**. Each step has:
- **Title** (required)
- **Body** — optional description, commands or notes (Markdown supported)

Use the **↑ ↓** arrows to reorder steps and **✕** to remove a step. Steps are saved with the runbook.

### Running a Runbook

Open a runbook to see the detail view with:
- **Checkboxes** — check each step as you complete it (stored in browser session only; resets on reload)
- **Progress bar** — shows X / N steps completed
- **Copy button** per step — copies the step body to the clipboard
- **Reset** — unchecks all steps for a fresh run

### Bulk Delete

Click **Select** to enter selection mode. Check any number of runbooks, then click **Delete selected** in the floating action bar.

### Favorites

Click the **★ star** button on any runbook to mark it as a favorite.

---

## Snippets

Snippets store reusable commands or scripts with multiple steps.

### Creating a Snippet

Go to **Snippets → New Snippet**. Enter a title and optional description. For each command step:
- **Description** — what the command does (optional)
- **Command** — the actual command or script (required)

Click **+ Add Command** to add more steps. The first command field is focused automatically when creating a new snippet.

### Using Snippets

On the snippet detail page or in the list view, click the **copy icon** next to any command to copy it to the clipboard. The snippet list supports full-text search across title, description and all commands.

Each snippet card in the list view also shows **Edit** (pencil), **History** (clock) and **Delete** (trash) buttons directly — no need to open the detail page first.

### Bulk Delete

Click **Select** to enter selection mode. Check any number of snippets, then click **Delete selected** in the floating action bar.

### Favorites

Click the **★ star** button on any snippet to mark it as a favorite.

---

## Mail Templates

Mail Templates store reusable email texts with pre-filled To, CC, Subject and Body.

### Creating a Mail Template

Go to **Mail Templates → New Template** and fill in the fields. All fields are optional except the name.

### Using a Mail Template

On the Mail Templates list, click **Copy** to copy all fields (To / CC / Subject / Body) to the clipboard in a format ready to paste into any mail client. Click **Open in Mail Client** to open a pre-filled `mailto:` link in your default mail app. Click **Download .eml** to download an RFC 2822 file that opens as a new draft in Outlook, Thunderbird or Apple Mail.

---

## Ticket Templates

Ticket Templates store issue / ticket descriptions with a title and body.

### Creating a Ticket Template

Go to **Ticket Templates → New Template** and fill in the **Name**, **Description** and **Body** fields.

### Using a Ticket Template

Click **Copy** in the list view to copy description + body to the clipboard for pasting into any issue tracker (Jira, GitHub Issues, Gitea, etc.).

---

## Vacations

The Vacation Tracker manages vacation requests with status tracking and working day calculation.

### Creating a Vacation Request

Go to **Vacations → New Vacation**. Enter:
- **Start date** and **End date** (end ≥ start required)
- **Status** — Planned / Requested / Approved / Documented
- **Note** — optional free text

Working days (excluding weekends and public holidays for your configured state) are calculated automatically.

### Status Workflow

Move requests through statuses on the list page using the status buttons on each card:

```
Planned → Requested → Approved → Documented
```

### Account Overview

The **Account** section at the top of the Vacations page shows:
- **Total days** — configured days per year + carryover from previous year
- **Used** — approved + documented entries (working days only)
- **Planned** — entries with status `planned` or `requested` (not yet approved)
- **Remaining** — total − used − planned

Use the **year navigation** to view past or future years.

### Vacation Mail Template

If a mail template is configured in **Settings → Vacation → Mail Template**, a 📧 button appears on each vacation card. Click it to open a preview page with all fields (To, CC, Subject, Body) filled in with the actual dates and working day count. From there you can:
- Copy individual fields to the clipboard
- Click **Open in Mail Client** to open a pre-filled compose window
- Click **Download .eml** to get a draft file for Outlook / Thunderbird / Apple Mail

### ICS Export

Click **Download ICS** on any vacation entry to download an Outlook-compatible `.ics` file. If you have named **ICS Export Profiles** configured in Settings, all profiles are downloaded at once as separate files.

### CSV Export

The **Export CSV** button on the Vacations page downloads all entries for the current year including calculated working days.

---

## Appointments

Appointments track whole-day external events: trainings, conferences, team events, business trips, etc.

### Creating an Appointment

Go to **Appointments → New Appointment**. Fields:

| Field | Description |
|-------|-------------|
| Title | Required |
| Type | Training 📚 · Conference 🎙 · Team Event 👥 · Business Trip ✈️ · Other 📌 |
| Start date / End date | End ≥ start required |
| Recurring | None · Weekly · Monthly · Yearly |
| Note | Optional |

### Recurring Appointments

Set **Recurring** to Weekly, Monthly, or Yearly when creating or editing an appointment. When you delete a recurring appointment, the next occurrence is automatically created with a fresh ID. The appointment duration (multi-day) is preserved across all occurrences. Month-end edge cases are handled correctly (e.g. Jan 31 + 1 month = Feb 28). A repeat icon badge appears on recurring cards in the list view.

### ICS Export

Download an `.ics` file per appointment using the **Download ICS** button. Appointment ICS Export Profiles (configured separately from vacation profiles in Settings) control the format.

---

## Calendar

The central **Calendar** at `/calendar` combines all event types in a single monthly view:

| Color / Style | Meaning |
|--------------|---------|
| Green background | Approved or documented vacation |
| Green dashed border | Planned or requested vacation |
| Indigo | Appointment |
| Gray | Public holiday |
| Red background + border | Today |

Navigate months with **← Prev** and **Next →**. The event list below the grid shows full details for every event in the month.

### Holiday ICS Export

If one or more **Holiday ICS Profiles** are configured (Settings → *Holiday ICS*), a download button appears next to each public holiday in the event list. Clicking it downloads an `.ics` file for every configured profile sequentially — ready for import into Outlook or any calendar app.

**Profile options**: Name (used as filename prefix), Subject template (`{name}` = holiday name, `{date}` = ISO date), Show-as (Free / OOF / Busy), Required and optional attendees, Outlook category, No-Online-Meeting flag (suppresses Teams link).

**Sprint Capacity** (`/calendar/capacity`) shows per-sprint progress bars: total work days, available days (minus vacations + holidays + appointments) and remaining days from today.

---

## MOTD (Message of the Day)

The **Message of the Day** module shows a rotating daily message at the top of the home dashboard.

### Creating MOTDs

Go to **MOTD → New Message** and enter the text. Only active messages rotate on the home page; toggle any message active or inactive with the button in the list.

### Mass Import

Go to **MOTD → Import** to create many messages at once. Either paste them into the textarea (one message per line) or upload a `.txt` file. The entire import is a single git commit. Duplicate messages (case-insensitive) are skipped automatically — the result shows how many were created vs. skipped.

### Duplicate Detection

When creating a single message or importing a list, duplicates are detected automatically (comparison is case-insensitive and ignores leading/trailing whitespace). Duplicates are skipped silently during import; a warning appears when saving a single duplicate.

### Home Widget

The MOTD widget appears at the top of the home dashboard. Click **→** to manually advance to the next message. Advancing is saved in Redis and resets at midnight so the same message is shown all day by default.

---

## Picture of the Day

The **Picture of the Day** (PotD) module shows one entry from your collection each day on the home dashboard.

### Building the Collection

Go to **Picture of the Day** and use the upload form:
1. Choose a **file** — supported formats: JPG, JPEG, PNG, WebP, GIF, PDF (max 25 MB)
2. Click **Upload**

Images are added as a single collection entry. PDFs are automatically split — each page becomes its own entry (page count is detected automatically via `pypdf`). PDF page entries appear with a dashed border in the list.

### Daily Selection

Each day, one entry from the collection is shown. The selection is deterministic: the same date always shows the same entry. The whole collection rotates — so every entry will be shown over time.

### Home Widget

- **Images** (JPG/PNG/WebP/GIF) — displayed inline, scaled to fit the widget
- **PDFs** — embedded as a scrollable `<iframe>` viewer; jumps directly to the correct page

### URL Fetch

Instead of uploading a file, paste a URL into the **URL** field and click **Fetch from URL**. The app downloads the image server-side and stores it in the collection — useful for grabbing images directly from the web.

### Next Button

Click **›** on the home widget to advance to the next entry for today. The offset is saved in Redis and resets at midnight.

### Lightbox

Click any image thumbnail (in the list or the home widget) to open it full-screen in a lightbox overlay. Close with **Escape**, the **×** button, or a click on the dark backdrop. PDFs open as before (no lightbox).

### Copy Image to Clipboard

In the lightbox, click **Copy image** to copy the image as a PNG blob to the system clipboard. There is also a clipboard icon button on each card in the list view that opens the lightbox and triggers the copy immediately. This requires HTTPS or localhost — the button silently fails on plain HTTP.

### Deleting an Entry

Use the **Delete** button in the PotD list view. Deleting a PDF page entry only removes that page's sidecar; the source PDF remains in the collection for other pages.

---

## Memes

The **Memes** module works exactly like Picture of the Day but for images only (no PDF support).

### Building the Collection

Go to **Memes** and either:
- Choose a file (JPG, JPEG, PNG, WebP, GIF — max 25 MB) and click **Upload**
- Paste a URL and click **Fetch from URL** to download and store an image directly

### Daily Display

One meme is shown on the home page each day. The selection is deterministic — the same date always shows the same meme. Click **›** on the home widget to skip to the next meme (offset resets at midnight).

### Lightbox

Click any image thumbnail (in the list or the home widget) to open it full-screen. Close with **Escape**, the **×** button, or a click on the backdrop.

### Copy Image to Clipboard

Click the clipboard icon on any card in the list, or use the **Copy image** button inside the lightbox. Requires HTTPS or localhost.

### Storage

Memes are stored as `memes/{id}.{ext}` in the data git repo.

---

## RSS Reader

The **RSS Reader** module reads RSS and Atom feeds and displays them on a dedicated page.

### Managing Feeds

Go to **RSS Reader** and click **Add Feed** at the top right. Enter a name and the feed URL. Each feed can be enabled or disabled individually with the **Edit** button.

Feed configuration is stored in the data git repo as `rss/{id}.yaml` — version-controlled alongside all other content.

### Navigating Between Feeds

A horizontal tab bar at the top of the page shows all configured feeds. Click any tab to jump to that feed. The active tab follows as you scroll through the feeds.

### Refreshing a Feed

Click the **↻** button on a feed card to force a fresh fetch. The cached version is discarded and new content is loaded immediately. By default feeds are cached for 15 minutes.

---

## History

The **History** page at `/history` shows a complete git log of all changes across all configured repositories.

Use the **time-range tabs** to switch between: Today / This Week / This Month / 30d / 90d / 365d / All. Tab switches load instantly via HTMX without a full page reload, preserving any active filters.

The **filter bar** lets you narrow results by:
- **Module** — e.g. show only Tasks or Notes commits
- **Author** — filter by git commit author name
- **Date from / Date to** — custom date range (overrides the tab)

Each commit shows: author, timestamp, subject line, short hash, and per-change badges: `Added` / `Modified` / `Deleted` with the entry title linked where possible (strikethrough if the entry no longer exists).

---

## Search

The global **Search** at `/search` queries all enabled modules simultaneously. Results are grouped by module with up to 10 items per group and a "View all →" link.

- Press `/` anywhere on the page to focus the navbar search input
- The search bar in the navbar is hidden on mobile — use the full `/search` page instead
- Results include Knowledge entries, Tasks, Notes, Links, Runbooks, Snippets, Mail Templates, Ticket Templates, Vacations and Appointments
- Matching text is highlighted with a **context snippet** below each result title — showing the surrounding text with the search term highlighted in purple
- **Filter by date**: use the "Created from / to" date pickers to narrow results by creation date (or `start_date` for Vacations and Appointments)

---

## Operations

Operations allows copying or moving content between repositories, and exporting / importing repository data as ZIP archives.

> Operations is only visible in the navigation when **2 or more repositories** are configured.

### Copy / Move Content

1. Go to **Operations**
2. Select a **Source repository**
3. Select a **Content type** (Knowledge, Tasks, Notes, Links, …)
4. Check the items you want to transfer — use **Select all** / **Deselect all** to manage the selection; Knowledge entries can be selected by category
5. Select a **Target repository**
6. Choose **Copy** (items remain in the source) or **Move** (items are removed from the source after transfer)
7. Click **Execute** and confirm the dialog

A success or error message appears after the operation.

### ZIP Export

In the **Export** card select a repository and click **Download ZIP**. A `.zip` file is downloaded containing all YAML and Markdown files from that repository.

### ZIP Import

In the **Import** card:
1. Select the **target repository** (only writable repositories are listed)
2. Choose the **mode**:
   - **Merge** — only imports files that don't already exist; existing files are kept as-is
   - **Overwrite** — replaces all files in the repository with the contents of the ZIP
3. Select the **ZIP file** to upload
4. Click **Import** and confirm

All imported files are committed to git automatically.

---

## Settings

Open **Settings** via the ⚙ link in the navbar. The settings page has a sticky sub-navigation on the left; sections scroll into view when you click a link.

### Appearance

Choose the application theme:

| Option | Behaviour |
|--------|-----------|
| **Auto (OS)** | Follows the operating system `prefers-color-scheme` setting. Changes take effect live without a page reload. |
| **Dark** | Always use dark theme. |
| **Light** | Always use light theme. |

The **☀️ / 🌙** toggle in the navbar overrides the theme for the current browser session only; it does not change the saved setting.

**Language** — Choose **English** or **Deutsch**. The sidebar navigation and navbar breadcrumb labels switch immediately. Module content (form labels, page titles, error messages) remains in English in this initial release.

### Offline Mode

When the git remote is unreachable (DNS failure, network timeout, connection refused), Daily Helper keeps the local commit and queues the push. A background task retries every 60 seconds. While changes are pending, an orange **Offline** banner appears at the top of every page and auto-refreshes every 30 seconds. The banner disappears automatically once the push succeeds and no further intervention is required.

### Repositories

Add, edit, remove and test git repositories. See the [README Configuration section](../README.md#configuration) for full details on auth methods, TLS, GPG signing and permission detection.

### Modules

Enable or disable any module individually. Disabled modules are hidden from the navigation and return 404 on all their routes.

Assign repositories to each module:
- **Knowledge** — reads from all assigned repos, writes to the primary
- **All other modules** — read and write to the primary repo

### Entry Templates

Manage custom Markdown templates that appear in the **New Entry** dropdown alongside the 4 built-in presets. Each template has a name and a Markdown body (uses the same editor as new entries).

### Git Identity

Set the **name** and **email** used for all git commits. These can be overridden per repository in the repo edit form.

### Vacation

Configure:
- **Days per year** and **carryover** from the previous year
- **German state** for public holiday calculation (all 16 Bundesländer)
- **Holiday language** — German or English names in the calendar
- **Show weekends** — toggle to hide Saturday / Sunday from the calendar grid
- **Mail Template** — reusable vacation request email with `{{from}}`, `{{to}}`, `{{working_days}}` placeholders

### ICS Export Profiles

Create named profiles for **Vacation ICS** and **Appointment ICS** exports independently. Each profile controls:
- Subject and body template (with placeholders like `{start_date}`, `{end_date}`, `{days}`, `{title}`)
- Show-as: Free / Busy / Out of Office
- All-day vs. timed event
- Optional attendees and Outlook calendar category

### Notes

- **Default scroll position** — open notes at the top (start) or bottom (end) of the page
- **Line numbers** — show a line number gutter in both detail view and editor

### Link Sections

Create and manage named link sections (e.g. Work, Personal). Each section can have its own **Floccus credentials** for browser bookmark sync. Existing flat links data is migrated automatically to the `default` section on first access.

### Data Export / Import

- **Export** — downloads all settings as a password-protected `.dhbak` file (PBKDF2-SHA256 + Fernet AES-128)
- **Import** — accepts `.dhbak` (requires password) or legacy `.json` (no password)
- **Backup to Repo** — encrypts the current settings and commits them to a selected git repository under `settings-backup/settings.dhbak`

### System

- **Max image cache size (MB)** — maximum file size for PotD and Meme images stored in Redis (base64-encoded); files larger than this limit are not cached; default is 10 MB; applied immediately without restart
- **Flush cache** — clears all Redis keys immediately
- **Restart** — sends SIGTERM to the app process; Docker restarts it automatically

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `/` | Focus the navbar search input |
| `q` | Open the Quick-Capture modal (create a Task, Note, Link, Snippet or Knowledge entry without leaving the current page) |
| `?` | Navigate to the help page for the current module (e.g. `/help/tasks` when on the Tasks page) |
| `n` | Open New Entry (Knowledge) |
| `e` | Open Edit for the current entry (when viewing a Knowledge entry) |
| `Tab` | Insert 2 spaces in the Notes editor (when line numbers are enabled) |
| `Enter` / `Shift+Enter` | Navigate to next / previous in-note search match |
| `Escape` | Close the mobile sidebar drawer or Quick-Capture modal |

### Quick-Capture Modal

Press `q` from anywhere (not while an input is focused) to open the Quick-Capture modal:

1. Select a **type** using the tabs at the top (Tasks, Notes, Links, Snippets, Knowledge)
2. Fill in the required fields (at minimum a title or subject)
3. Click **Save** or press Enter on the last field
4. A success toast confirms the save — the modal closes and you stay on the current page

> **Note:** Knowledge entries redirect to the full `/knowledge/new` form with the title and category pre-filled, because creating a Knowledge entry requires selecting a repository.

### Help System

Each module has a help page accessible via:
- The `?` button in the module list page header
- The `?` keyboard shortcut from anywhere on that module's page
- Directly at `/help/{module}` (e.g. `/help/tasks`, `/help/notes`)
