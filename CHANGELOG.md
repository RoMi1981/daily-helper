# CHANGELOG

All notable changes are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Changed

- **Saving no longer stalls every other request.** Each write (create, edit, delete, upload, ZIP import, copy/move between repos, favorites, settings backup) now runs its git sequence in a worker thread. Until now it ran on the single event loop, so a slow push made every other page wait, up to 15 s. `tests/test_write_routes_off_loop.py` checks all routes statically and one route per module at runtime.

---

## 2026-09-30 — Dependency updates

### Security

- **Four dependencies had known vulnerabilities**, 15 advisories in total; nothing checked for them until now. Updated: `python-multipart` 0.0.20 → 0.0.32 (denial of service while parsing forms), `markdown` 3.8 → 3.8.2, `bleach` 6.2.0 → 6.4.0, `cryptography` 44.0.2 → 50.0.2.
- **A line starting with `<![` hid the rest of a knowledge entry.** Python-Markdown 3.8 turned everything from there to the end into an HTML comment, which the sanitizer then removed, without any error (CVE-2025-69534).

### Changed

- **CI audits the dependencies.** `pip-audit` runs in the test job; a known vulnerability fails the job and blocks the image build and publishing.
- **Weekly dependency audit.** The same check runs every Monday without a push, so an advisory published between two pushes does not go unnoticed. A finding opens an issue — one while it stays open — and fails the run.

---

## 2026-09-28 — Full code and documentation review

### Security

- **Titles could run code in delete prompts.** Ten delete buttons put a title straight into an inline handler: `onsubmit="return confirm('Delete \'{{ link.title }}\'?')"`. Autoescaping turns `'` into `&#39;`, but the browser decodes entities in an attribute before it runs the JavaScript, so a link titled `x'+(document.title='PWNED')+'` executed its own code on the delete click. Link titles arrive from browser bookmarks via Floccus, i.e. from arbitrary web page titles, and the app has no login of its own. All 32 prompts now use a `data-confirm` attribute read by one handler in `base.html` — the text is a plain HTML attribute and never part of a script. The remaining inline handlers pass values with `| tojson`.

- **The Floccus login is throttled.** It is the only password-protected part of the app and allowed unlimited guessing. After 20 failed attempts within ten minutes — Basic Auth or the login grant form — every attempt gets `429` until the window has passed. The brake is global rather than per client: behind a reverse proxy every request carries the proxy's address, and `X-Forwarded-For` can be forged on direct access. During an attack the real Floccus client is locked out too; for a single-user app that is the better trade.

### Fixed

- **`settings.json` is written atomically.** It was rewritten in place; a crash or a full disk mid-write left truncated JSON, and the next start failed completely. It is now written to a sibling file and swapped in with `os.replace`.
- **"Delete selected" did nothing in snippets, links and tasks, and the first row could not be deleted.** Every row carried its own delete `<form>` inside the bulk-delete form. HTML forbids nested forms; the parser silently drops the inner start tag, and the inner `</form>` then closes the *outer* form. The first row's delete button therefore submitted the bulk form with no ids and no confirmation, and everything after the first row — including the toolbar button — sat outside any form. The delete buttons now stay inside the bulk form and use `formaction`.
- **The favourite star silently failed for titles containing `"`.** `hx-vals` was hand-written JSON with `| e`; the browser decoded the entity back into a bare quote and htmx could not parse it. Built with `| tojson` in the templates, and with `json.dumps` in the server response that replaces the button. The server response also showed an untranslated tooltip.
- **Moving items between repositories could lose them.** The delete step of a move walked every requested id, including items whose copy had just failed — they were removed from the source and existed nowhere. Only completely copied items are deleted now, and a half-copied item (a media file whose sidecar failed) is removed from the target again.
- **An unreadable `favorites.yaml` was replaced on the next star click.** `_load()` answered every parse error with an empty list, and toggling then wrote back a list holding only the new entry. A broken file (e.g. a merge conflict) now makes the toggle fail with 409 and leaves the file untouched; the list display falls back to empty and logs why.
- **Keyboard shortcuts:** `n` jumped to `/new`, a route that never existed; it now opens a new knowledge entry, as documented. `?` only knew ten of the nineteen modules with a help page — its list is now the one the help route itself serves.
- **Knowledge entries with broken frontmatter vanished without a trace** from listing and search. They are still skipped, but each one is logged with its path.
- **About 60 UI strings were not translated**, including all delete prompts, "History:", "Created · Updated", step and day counts, search result counts and the MOTD import messages. The i18n check skipped any text next to a template expression and every string inside `<script>`; it now masks expressions instead of skipping them and checks strings a script writes into the page. Counts now use a real singular: `t()` picks a `<key>.one` translation when `n` is 1 (e.g. "1 step", "3 steps").

### Documentation

- **`docs/api.md` rewritten from the actual routes.** Eight entries named routes that did not exist (four `/api/home/*` endpoints, `toggle-pin` instead of `pin`, `GET /api/preview` for a `POST`, a file-history route) and about eighty were missing, the whole EOL module among them; `/health` and `/api/redis-status` were described wrongly. A test now compares the file with the application's routes in both directions.
- **`TESTING.md`**: the "unit tests only" command collected the E2E suite and failed with 33 errors; the coverage figures were several points too high; the per-test tables covered 22 of 61 unit test files and described E2E tests that had long been rewritten. It now lists every test file with the first line of its docstring, and a test keeps that list complete.
- README and the public README had drifted in both directions (Memes and EOL missing from the contents, link moves, lightbox and image copy, the ticket description limit); the user guide's contents lacked EOL and the widget dashboard.
- The published tree no longer names internal hosts: test repository URLs come from the CI job instead of defaults in the test files, and a LAN address and the host's deploy user are gone from this changelog and the tests.

### Changed

- **htmx, Lucide and highlight.js are served by the app** from `static/vendor/` instead of unpkg and cdnjs. The UI no longer needs internet access, and a new Lucide release can no longer change the page on its own — it was loaded as `@latest`. Versions, sources and licenses are listed in `static/vendor/README.md`.

### Removed

- `static/pdf.min.js` and `pdf.worker.min.js` (1.4 MB), unused since Picture of the Day converts PDFs to PNG on the server.
- The 17 help files directly under `help/`; only `help/en/` and `help/de/` are read, and `notes.md` had already drifted.
- `appointments/calendar.html` and `vacations/calendar.html`; both routes redirect to the shared calendar.

### Tests

- Static checks: no template value in an inline handler unless it is an id or `| tojson`; `hx-vals` only via `| tojson`; no inline `confirm()`; no nested `<form>` (includes resolved).
- E2E: every row's delete button targets its own entry, bulk delete removes exactly the selection, a hostile link title is shown verbatim and not executed, the favourite star works with quotes. All four fail against the previous code.

## 2026-09-27 — Copy buttons lost their icon after a click

### Fixed

- **Copy buttons in ticket templates and runbooks keep their icon.** Both handlers saved the button's `textContent` before showing the ✓ and restored it afterwards. The buttons are icon-only, so `textContent` is empty: after the first click the icon was gone and the button shrank to its padding (35.8 → 25.6 px in ticket templates, 25.6 → 16 px in runbooks). Both now save `innerHTML`, like the mail template, snippet and link buttons already did. The ticket template feedback is now a plain `✓` like everywhere else instead of the untranslated `✓ Copied`.

### Tests

- The existing clipboard tests only checked what landed in the clipboard, never the button afterwards. New E2E tests assert that icon and width come back; a static check fails on any template that saves `textContent` to restore it later.

## 2026-09-17 — Redis on a private network

### Changed

- **Redis is no longer attached to the shared reverse-proxy network** in `deploy/docker-compose.yml` and the root compose file. Redis runs without a password, so every container on that network could read and write it. Worse, the service name `redis` resolved to the Redis of every stack on the network at once: with two stacks running, an app could end up on the other stack's Redis. Redis now sits on a project-scoped `backend` network that only the app joins. `examples/docker-compose.yml` already used the default project network and is unchanged.

## 2026-09-17 — Redis healthcheck

### Added

- **The Redis container has a healthcheck.** Until now neither `docker ps` nor container-health monitoring could tell when Redis hung. The check is `redis-cli ping | grep -q PONG` rather than plain `redis-cli ping`: `redis-cli` exits 0 even when the server replies with an error such as `LOADING` or `NOAUTH`, so the exit code alone would report a server that cannot serve as healthy. Verified both ways: a normal server turns `healthy`, one answering `NOAUTH` turns `unhealthy`, and a stopped server makes `redis-cli` block until the 5 s timeout. Applies to `deploy/`, the root and the `examples/` compose files.

## 2026-09-06 — Content cut off at the right edge, and the note cursor

### Fixed

- **Content column no longer grows past the viewport on desktop.** `.layout` is a `220px 1fr` grid; a grid item defaults to `min-width: auto`, so the content column could not shrink below the min-content width of its contents. One `<code>` line with `white-space: nowrap` — a snippet command — widened the whole column to 1733 px inside a 1920 px window, and `html { overflow-x: clip }` then cut the page off at the right edge instead of scrolling. `.content` now carries `min-width: 0`. Only desktop was affected: below 768 px the layout is a single column with `overflow-x: hidden`.
- **Knowledge search snippets wrap instead of spilling out of their card.** `.result-snippet` had no break rule, and the excerpt can be up to 200 monospace characters — a single long URL is wider than the card at 1280 px. Now `overflow-wrap: anywhere`.
- **Double-clicking a note opens the editor at the clicked spot.** The handler navigated to the edit form without the position, so the editor always fell back to the configured start/end setting — in practice the end of the note. The clicked offset now travels in the URL hash; the editor places the caret there and scrolls it into view. The line-number gutter behaves the same way, deriving the line from the click's y position.

### Tests

- The existing responsive check compares `documentElement.scrollWidth` against `innerWidth`, which `overflow-x: clip` keeps equal even when the column has already grown — it could not see this bug. A second check now asserts that `.content` itself stays inside the viewport, on a seeded page containing a long snippet command.
- E2E coverage for the note double-click position and for a search snippet made of one unbreakable token.

---

## 2026-08-19 — Published repository is English-only

### Changed

- **`CHANGELOG.md` translated to English.** The published GitHub repository is meant to be English, but every entry written since 2026-08-19 — and a few older ones — was German. The bilingual part of the product is deliberate and untouched: `locales/de.json` and `help/de/` are the German UI, not a leftover.
- **Two stale `HANDOVER.md` files removed from `image/`** (`image/HANDOVER.md`, `image/app/HANDOVER.md`, from sessions in May 2026). `image/` is published in full, so both internal German notes were shipped to GitHub and into the container image. The current handover lives in the repo root; the content stays available in git history.

### CI

- The publish job now **verifies the tree before pushing**: German text anywhere outside `locales/de.json` and `help/de/` fails the job. The CHANGELOG had been German for a long time without anyone noticing, so the check belongs at the publish boundary rather than in a review checklist.

---

## 2026-08-19 — Review phases 4 and 5: cascades replaced, concurrency made safe

Fourth and fifth phase of the plan in `TECH_DEBT_AUDIT.md`
(DASH-03/04/05/06/10, CORE-01, CORE-06, CONTENT-14).

### Fixed

- **No locking between `_pull()` and `_commit_and_push()`** (CONTENT-14). Two concurrent writes to the same repo could interleave: the second pull landed between the first writer's change and its commit and carried that file state along — a lost update. `GitStorage.write_lock()` is a reentrant lock per `repo_id`; every write sequence now runs inside it.

  The lock also covers the cases where pull and commit sit in different methods (the `delete_`/`bulk_delete_` paths via `YamlDirStorage._delete`), the read-modify-write in `favorites.toggle_favorite`, the slug search in `save_entry` and `toggle_pin`, the settings backup and the POTD migration. `tests/test_write_lock_coverage.py` checks statically across the whole app tree that no write sits outside the lock — a missing lock is invisible otherwise.

- **The date filter on `/search` never applied to knowledge results.** `GitStorage.search()` does not return `created`, the filter read it via `.get("created", "")`, and an empty value means "no date, so keep it". A from–to filter therefore still showed entries from any period. `search()` now returns the field.
- **Links outside the default section were invisible in three places.** Links live in user-defined sections (`links/{section}/`), but `LinkStorage` defaults to `default`. Global search, the bookmarks widget and the category list of its settings popover were all affected — no error anywhere, simply no results. `link_storages(store)` returns one storage per configured section; `tests/test_link_sections.py` fails any future caller that builds only one.
- **Changes to appointments never appeared in the history.** `AppointmentStorage` writes to `appointments/entries/{id}.yaml` while history detection expected `appointments/{id}.yaml`. Both layouts are recognised now (the flat one stays for older repos).
- **Knowledge results rendered without a context line.** The snippet came from `r.get("body", "")` — that field does not exist in search results, so `_highlight()` always received an empty string and the already computed excerpt was thrown away. Both defects date back to the old code and only surfaced once the new search ran against a real repo instead of mocks.

### Changed

- **Four `if/elif` cascades replaced by tables.** All four behaved the same way: a missing branch did *nothing* and reported nothing — exactly the class of defect that cost the EOL tile earlier.
  - `widgets_dashboard()`: 23-way cascade → `_WIDGET_LOADERS` (DASH-04).
  - `_parse_history_path()` (327 lines) → `_HISTORY_RULES`; eleven modules follow the same path pattern, only knowledge/tasks/notes/links keep their own handlers (DASH-06).
  - `global_search()` (441 lines) → `core/global_search.py` with `PROVIDERS`; the module check, date filter, error isolation, result cap and cache now exist once instead of twelve times (CORE-01).
  - `_do_copy_move()` (424 lines) → `_item_paths()`. Copy and delete derived their paths separately before; a type present in only one of the two cascades meant: copied, but never deleted on move (DASH-05).
- **`widgets/router.py` (1349 lines) split** into `registry.py`, `loaders.py` and a router module of 242 lines (DASH-03).

### Performance

- **Network-bound hot paths blocked the event loop** (CORE-06, first stage): `check_repo_permissions` (PAT request and `ls-remote`, up to 15 s), `sync_repo`, `repo_health` and building `/metrics` now run through `asyncio.to_thread`. Previously the whole app waited on a single repo check. The write routes of the content modules follow incrementally.
- **Widget loaders ran sequentially** (DASH-10): ten widgets meant ten consecutive git reads. Now `asyncio.gather` over a thread pool. The shared per-request caches can be filled twice in the process — one redundant read, never a wrong result.

### Tests

- `tests/test_repo_write_lock.py`: interleaving, reentrancy, release on failure, a lost-update scenario, and that two repos do not block each other.
- `tests/test_history_rules.py`: derives coverage from `modules_enabled` — a module without a history rule drops out of the history silently and now fails the test instead.
- Widget dispatch checked against the registry, search providers against `modules_enabled`, `_item_paths` per content type including sidecar files, loader parallelism via a barrier.

---

## 2026-08-19 — Review phase 3: UI translation complete

Third phase of the plan in `TECH_DEBT_AUDIT.md` (I18N-01, I18N-04).

### Fixed

- **444 hardcoded UI strings in 57 templates ignored the language setting.** The bulk sat in `settings.html` (152), plus the knowledge, snippets and runbook forms, the markdown editor toolbar, the EOL views and the widget edit mode. All of them go through `t()` now; roughly 190 keys were added (EN + DE), and part of the strings could reuse existing but unused keys.
- **`vacations/calendar.html` contained hardwired German text** ("↩ Liste") while its identical sibling `appointments/calendar.html` was English — an English-speaking user saw German there. Both use the same key now.
- **80 dead locale keys removed** (I18N-04), among them 34 with the `home.` prefix — leftovers from the removed home dashboard — and the month names `cal.jan`…`cal.dec`, which were never used because `holidays_helper.py` carries its own DE/EN lists. Every candidate was checked against templates, Python and JavaScript before deletion, including dynamically composed keys (`t("nav." ~ module)`); 10 candidates were kept for that reason.

### Tests

- `tests/test_widget_templates_i18n.py` → `tests/test_template_i18n.py`, now covering **all 93 templates** instead of only `templates/widgets/`. The detector ignores `<script>`/`<style>` content and Jinja statements, which would otherwise be picked up as text.
- New `VERBATIM`: a documented list of strings that deliberately stay English — product names, OAuth scope names, configuration values, paths, sample data. What is intentional is now stated in the test instead of being carried as open work.

---

## 2026-08-19 — Review phase 2: lint backlog to zero

Second phase of the plan in `TECH_DEBT_AUDIT.md`. The goal was the state the lint workflow comment had described since it was introduced: clear the backlog, then `strict: "true"`.

### Fixed

- **Five tests had never run since they were written** — `test_update_entry` (motd), `test_update_runbook`/`test_delete_runbook`, `test_update_snippet`/`test_delete_snippet` were each defined twice (storage level and router level), and the second definition silently shadowed the first. Surfaced by ruff F811. The router variants are now named `…_router`, the way the same files already handle it elsewhere — the suite grew from 1471 to 1476 tests, all green.
- **`test_next_button_rotates_meme` did not check the rotation** — the test read `src_before` but then only compared whether the widget still existed. With a single uploaded meme it could not have shown anything anyway, because `/memes/next` advances an offset. It now uploads two memes and checks that the image source actually changes.
- **The table of contents in both READMEs linked to a section that does not exist** — `[Common Commands](#common-commands)`; the heading of that name only appears inside a fenced markdown example. Entry removed (markdownlint MD051).
- **Outdated test counts in the docs** — README claimed ~1077, README.public ~750, TESTING.md ~796. The real numbers are ~1560 unit/integration tests plus 343 E2E tests.
- `_safe_filename()` in `knowledge/router.py` sat between two import blocks (CONTENT-18), as did a constant in `core/storage.py` — both moved below the imports.
- `zip()` in `eol/router.py` without `strict=` — entries would have been dropped silently for sequences of unequal length (B905).

### Changed

- **New `ruff.toml` and `.markdownlint-cli2.jsonc`** — the rule sets now live in the repo instead of existing only inside the CI image. A local run matches the CI result; divergence between the two environments caused a falsely green run twice, on 2026-07-28 (`pytest-asyncio`) and 2026-08-19 (template path). Documented exceptions: E402 in `tests/**` (the `sys.path` setup has to precede the app imports), E402 in `main.py` (deliberate handler-local imports to avoid cycles), B008 (FastAPI's `Depends(...)` idiom), MD013/MD033 and MD024/MD060 (the latter two are not reported by the CI version).
- **Lint backlog to zero**: 479 `ruff check` + **99 files `ruff format`** + ~196 markdownlint + 9 yamllint + 3 hadolint. 333 of the ruff-check findings via `--fix`, the rest reviewed individually. The formatter share was missing from the original assessment — the figure 479 came from `ruff check`, while the CI job additionally runs `ruff format --check`; that only became visible in the job log of this phase's first run.
- **`.gitea/workflows/lint.yml` is now `strict: "true"`** — the job fails on new findings instead of merely logging them.
- **CI workflow de-duplicated** — the registry cache reference appeared twice per job, each time in an over-long line; it now sits once as `CACHE_REF` in the `env` block.
- **Dockerfile** — `useradd -l` (DL3046, avoids an oversized `lastlog` file for high UIDs), HEALTHCHECK in exec form (DL3025), and two consecutive `RUN` instructions merged in `Dockerfile.e2e` (DL3059).

### Docs

- CHANGELOG, both READMEs and ROADMAP use real headings instead of bold paragraphs (MD036) — content unchanged.

---

## 2026-08-19 — Review phase 1: visible defects and guard precision

First phase of the plan in `TECH_DEBT_AUDIT.md` (review of 2026-08-19).

### Fixed

- **The "next meme" button showed the literal string `action.next` as its tooltip** — the key was used in `memes/list.html` but existed in no locale file. `core/i18n.t()` falls back to the key itself when it is missing, which is why this slipped through. The three identical buttons in `partials/meme_widget.html`, `partials/potd_widget.html` and `partials/motd_widget.html` had the same tooltip hardcoded and were converted along with it (`action.next_meme` / `action.next_picture` / `action.next_message`, EN + DE).
- **`GitStorage._reject_traversal()` accepted a separator in the value** — the function documents "a single path component" but accepted `sub/name`. Escaping the repo was not possible (`..` and absolute paths were already rejected), but `save_attachment(filename="a/b")` would have created a subdirectory silently. It now also checks for exactly one component — enforcing what the knowledge UI promises the user anyway ("No slashes allowed").
- Dead import (`UnsafeUrlError`) removed from `core/permission_checker.py` — a leftover of the same day's LAN repo fix (ruff F401).

### Tests

- New `tests/test_locale_keys.py`: checks that every `t("…")` key used in the code exists in `en.json`, and that `en.json` and `de.json` carry the same key set. A missing key is invisible otherwise, because it renders as text.
- `TestRejectTraversal` in `test_storage.py` — a separator is rejected, `..`/absolute paths still are as well.

### Docs

- `README.md`/`README.public.md`: the claim "full UI translation (692 keys)" was wrong on both counts — there are 703 keys, and coverage was not complete (444 hardcoded strings in 57 templates, see I18N-01). Wording corrected accordingly.
- `ROADMAP.md`: i18n phase 4 and the lint backlog added as open items.

---

## 2026-08-19 — Fix: untranslated strings in widget templates

### Fixed

- **Seven widget templates contained hardcoded English UI text** — with German selected, "Total"/"Used"/"Planned"/"Remaining" (vacation balance), "High" (tasks due/overdue), "Starts today"/"Starts tomorrow"/"work days to go"/"until …" (next vacation), "Off" plus the CA/GPG tooltips (repos) and "New task…"/"Medium"/"High"/"Low"/"Add" (quick capture) stayed English while every surrounding string was translated. Nothing failed; the strings were simply rendered unchanged.
- Most keys already existed (`priority.*`, `vacation.stat.*`, `action.add`) and were merely unused; eight keys were added (EN + DE).

### Tests

- New `tests/test_widget_templates_i18n.py`: checks every template under `templates/widgets/` individually (parametrised) for bare text nodes and `placeholder`/`title`/`aria-label` values. Acronym badges (RW, RO, CA, GPG) remain allowed, because only words containing at least one lowercase letter count as text.
- On its first real run the test found three places a grep search had missed (`title` attributes and an "until" fragment).

---

## 2026-08-19 — CI: E2E test repos were never fully reset

### Fixed

- **The `e2e` job was red on `main` and therefore skipped `build`, `publish` and `deploy`** — `test_delete_meme` failed (`assert 1135 == 1134`). Cause: the "Reset E2E test repos" step in `.gitea/workflows/image_build.yml` deleted only `*.yaml` and `*.md`. Meme and POTD images (`.png`/`.jpg`) survived every reset and accumulated to more than 1100 files across CI runs. The reset now deletes everything except `.git` instead of maintaining an extension allowlist — that allowlist was the defect.

---

## 2026-08-19 — Fix: EOL tracker tile always showed 0

### Fixed

- **The `stats_eol` widget showed 0 entries although entries existed.** `_load_counts()` in `modules/widgets/router.py` simply had no `eol` branch — the widget was registered in `WIDGET_REGISTRY` and `_DEFAULT_LAYOUT`, but its count was never computed. The template reads `counts.get(mod, 0)`, so it fell back to 0 without an error or a log entry. Added: `"eol": lambda: _count_all("eol", "eol")` (flat `eol/{id}.yaml` structure, multi-repo via `get_module_stores`).

### Tests

- `test_eol_entries_are_counted` — regression test for exactly this case.
- `test_every_stats_widget_module_is_counted` — derives the modules to check from `WIDGET_REGISTRY` instead of hardcoding them. A future `stats_*` widget without a counter fails the test instead of silently showing a 0.

---

## 2026-08-19 — Fix: repo check against a self-hosted Gitea on the LAN

### Fixed

- **"Check permissions" and "Test connection" failed for every repo on a private address** (`URL resolves to a non-public address: 10.x.x.x`). The SSRF guard added to `permission_checker.py` on 2026-07-27 called `assert_public_http_url()` on the API URL derived from the repo URL — but a self-hosted Gitea/GitLab on a LAN address is the normal case for this app, and the operator enters the repo URL in settings themselves; it is not untrusted input. The guard was therefore in the wrong place: it prevented no attack scenario and blocked the core function instead.
- New: `assert_http_or_https()` in `core/net_guard.py` — validates the scheme and the presence of a host, nothing else. `permission_checker` uses it both for the initial API URL and per redirect hop in `_SafeRedirectHandler`. The protection that matters here remains: a compromised git host still cannot redirect the request to `file://` or similar via a 302.

### Tests

- `TestAssertHttpOrHttps` in `test_net_guard.py` (accepts private/loopback/public hosts, rejects `file://` and a missing host).
- `TestCheckPermissionsSSRF` → rewritten as `TestCheckPermissionsUrlGuard`: the old tests encoded the wrong intent ("a private address must be rejected"). Now: a LAN IP and `localhost` have to work, a `file://` redirect still has to fail.

---

## 2026-07-28 — CI Fixes: RSS Save Regression, Async Test Compatibility

Both issues were introduced by the 2026-07-27 round and only surfaced in CI (the `test` and `e2e` jobs were red on `dev` and `main`); local runs passed because the local environment happens to have packages the test image does not.

### Fixed

- **RSS feeds could no longer be added or edited when the host was unresolvable** — the new SSRF guard called `assert_public_http_url()` (which resolves DNS) on the *save* path. Saving a feed performs no request, so requiring resolvability turned a temporary DNS outage or a briefly-down feed host into a hard save blocker. Added `assert_http_scheme()` for store-only validation: it checks the scheme and rejects literal internal IPs (no DNS needed to spot those) but does not resolve hostnames. The full SSRF check remains on the fetch path (`_fetch_feed`), which is where a request is actually made — so this is no loss of protection.
- **`tests/test_net_guard.py` failed in CI** — two tests used `@pytest.mark.asyncio`, but `image/Dockerfile.test` installs only `pytest httpx` (no `pytest-asyncio`). Rewritten to drive the coroutines via `asyncio.run()`, matching how `test_eol.py` already does it — no new test dependency.

### Tests

- New `TestAssertHttpScheme` covering the store-path validator (accepts unresolvable hostnames, still rejects bad schemes and literal loopback/private/link-local IPs).
- New `TestFeedSaveValidation` in `test_rss.py` — regression guard: adding a feed with an unresolvable host must succeed, while a literal internal IP or a non-http scheme must still be rejected.
- Verified the whole unit suite under CI-like conditions (`pytest -p no:asyncio`).

### Docs

- `MERGE_CHECKLIST.md`: added "CI green, not just locally" (with the job-log API path) and "SSRF guard at the right point" (full resolution only where a fetch happens) — both derived directly from these two failures.

---

## 2026-07-27 — Second Full Codebase Review: Critical Bugfixes, SSRF Hardening, Storage Consolidation

Follow-up to a second 5-agent review (code quality, security, architecture, performance, test coverage) of the app. This round found and fixed several real correctness bugs beyond the prior pass's scope.

### Critical

- **Fixed: path traversal + reflected XSS in `POST /settings/backup-to-repo`** — `backup_path` was taken from the POST form with no validation, unlike every other path-accepting call in the codebase; `Path(base) / "/abs/path"` silently discards `base` for absolute paths. Now validated via `GitStorage._reject_traversal()`; the error-message interpolation is now `html.escape()`d too.
- **Fixed: failed `git commit` could roll back the previous, already-pushed commit** — `_revert_working_tree()` unconditionally ran `git reset --soft HEAD~1` on any commit-phase failure, even when no commit had actually happened yet, discarding the prior legitimate commit instead. Added an `undo_commit` flag so the commit-failure path skips the reset while the push-failure path (where a local-only commit genuinely needs undoing) keeps it.
- **Fixed: `read_committed()`/`list_committed()` queried different git refs** (`origin/main` vs `HEAD`), causing a file just committed locally (but not yet pushed) to appear in a directory listing while reading back as `None` — silent data loss for notes/links during exactly the offline/pending-push window the app's resilience design is meant to survive. Both now consistently use `HEAD`.
- **Fixed: Knowledge category-only browsing bypassed module_repos scoping** — `GET /knowledge/search?category=…` (no query text) called `MultiRepoStorage.get_entries()` directly, iterating every configured repo regardless of the knowledge module's repo assignment. Same bug class as the calendar/tasks fix from the prior round, missed here.

### Security

- **Fixed: RSS fetch bypassed the redirect-hop SSRF revalidation** — `_fetch_feed()` called `feedparser.parse(url)` directly, which does its own HTTP fetch and follows redirects internally with zero SSRF re-checking (the same bypass class `fetch_public_url()` was built to close for memes/POTD, just left open here). Now fetches the body via `httpx` + `fetch_public_url()` and hands the bytes to `feedparser.parse()`.
- **Fixed: `core/permission_checker.py` had no SSRF guard at all** — the "check repo permissions"/"test connection" flow built an API URL from a user-supplied repo URL + PAT and fetched it via `urllib.request.urlopen` with no scheme/host/private-IP validation and default redirect-following. Added `assert_public_http_url()` on the initial URL plus a `_SafeRedirectHandler` that re-validates every redirect hop before following it.
- **Fixed: `net_guard` missed CGNAT space (100.64.0.0/10)** — `ipaddress.is_private` doesn't cover RFC 6598 Carrier-Grade NAT addresses; added an explicit check.
- **Documented (not fixed): DNS-rebinding TOCTOU in `net_guard`** — the guard resolves+validates a hostname once, then hands the hostname (not the pinned IP) back to httpx/urllib, which re-resolve independently on connect. A DNS-rebinding attacker could flip the answer between check and connect. Fixing this fully requires IP-pinning the actual connection (custom transport/resolver, with its own SNI/Host-header complexity) for a threat model where the attacker already needs the user to add the URL themselves on a single-user internal tool — documented as an accepted residual risk in `core/net_guard.py` rather than adding a fragile mitigation.

### Performance

- **Fixed: 5 modules pulled + read the working tree directly on every read, uncached** — `motd`, `runbooks`, `snippets`, `mail_templates`, `ticket_templates` now read via `list_committed`/`read_committed` (git objects, Redis-cached) like every other content module; MOTD in particular loads on nearly every dashboard view.
- **Fixed: `GitStorage._pull()`/`_ensure_fetched()` had no subprocess timeout** — a slow/hung remote could block the sole event loop indefinitely; both now bounded to 15s.
- **Fixed: EOL enrichment fetched each tracked product serially** — `_enrich_entries()` now fetches all distinct products concurrently via `asyncio.gather` + `asyncio.to_thread`; the single-product routes (`/eol/search`, `/eol/product/{p}`, `/eol/timeline/{p}`) also moved off the event loop.
- **Fixed: Links page scanned the directory twice per load** (`list_links()` + `get_categories()`, each a full scan) — now a single unfiltered scan per store, with filtering and category derivation done in Python.
- **Fixed: `du -sb` ran uncached on every dashboard load** for the Repos and /tmp Usage widgets — now cached 5 minutes via Redis, matching every other widget data loader's caching convention.
- Wrapped remaining blocking calls in `asyncio.to_thread`: PDF→PNG conversion in POTD upload/fetch, ZIP tree-walk+compress in `operations/export`.

### Code quality

- New `core/yaml_dir_storage.py` base class collapses the identical read/write/delete plumbing shared by `runbooks`/`snippets` and `mail_templates`/`ticket_templates` — while doing so, fixed a real search-quality drift bug: `runbooks.list_runbooks()` only matched title/description, never step content, unlike `snippets` which already searched step text.
- `eol` module repo-assignment was unreachable from the settings UI (missing from both `main.py`'s module list and `settings.html`'s checkbox loop) — added.
- Operations bulk copy/move only ever saw the "default" link section — links in other configured sections were invisible to and unreachable from the UI. Item IDs are now `{section_id}/{link_id}` and every configured section is listed.
- `core/favorites.py::_get_primary_git` claimed ("prefer writable") but didn't filter by write access at all — now delegates to `module_repos.get_primary_store()`, the same primary-repo resolution every other module uses.
- Removed dead fallback code in `links/storage.py::bulk_delete_links` (searched nested subdirectories that can never exist — sections are siblings, not nested).
- `datetime.utcnow()` → `datetime.now(timezone.utc)` (last straggler); deduplicated two stale, already-out-of-sync `modules_enabled` fallback defaults down to referencing `DEFAULTS`; added logging to `main.py::global_search`'s 11 previously-silent `except Exception: pass` blocks.

### Tests

- New `tests/test_net_guard.py`, `tests/test_permission_checker.py` (previously zero direct coverage — resolves tracked debt item CORE-13).
- New regression tests for every critical/security fix above: traversal rejection in `backup_to_repo`, no-rollback-on-failed-commit, `read_committed`/`list_committed` ref agreement, knowledge category scoping, RSS SSRF redirect handling.
- Tightened weak `status_code in (x, y)` assertions to exact expected codes in `test_vacations_router.py`, `test_ticket_templates_router.py`, `test_floccus_api.py`.
- New `tests/e2e/test_settings_module_repos.py` — the EOL module-repo-assignment checkbox row is now e2e-covered (visible + persists across reload), per `MERGE_CHECKLIST.md`'s "every UI interaction needs an e2e test" rule.
- `TECH_DEBT_AUDIT.md`: TIME-07 (was stale — the test file already existed) and CORE-13 marked `[RESOLVED]`.

### Docs

- Fixed README.md/README.public.md contradiction on UI translation scope (both wrongly said "404 keys"; actual is 692, verified against `locales/en.json`).
- `docs/api.md`: corrected `GET /` (redirects to `/widgets`, not a separate "home dashboard"); added a missing `/widgets` endpoints section for the largest, most-used module in the app.

**Deferred** (documented, not started — same reasoning as the prior round: large/speculative refactors or exhaustive backfill, not surgical fixes)

- N+1 `git show` subprocess pattern across ~15 modules; uncached `GitStorage.get_history()`; synchronous `git ls-remote` in `repo_health()`.
- Storage-boilerplate dedup for the remaining modules with genuine domain divergence (tasks, notes, vacations, appointments, links) — assessed and intentionally *not* forced into a shared base, unlike the two pairs above, per this project's simplicity-first convention.
- Full test-coverage backfill for `widgets/router.py`'s ~15 still-untested loader functions, and offline/mocked-subprocess unit tests for `GitStorage`'s core git mechanics (currently only covered by an integration test requiring a live Gitea deploy key).
- `main.py::global_search`'s 440-line/11-near-duplicate-block structure and `core/storage.py::_parse_history_path`'s 325-line if/elif chain — logging added, full data-driven refactor not attempted (large, risk of regression, no functional bug).
- `tests/e2e/test_mail_templates.py`; knowledge-router happy-path unit tests; README.md/README.public.md stylistic (non-contradictory) divergence beyond the UI-translation-count fix.

---

## 2026-07-24 — Full Codebase Deep-Dive: Security, Performance, Code Quality

Follow-up to a full 5-agent review (code quality, security, architecture, performance, test coverage) of the app outside the widgets module. Authentication was scoped down to a documentation note by the maintainer (no in-app login/session infrastructure — reverse-proxy Basic Auth is the intended deployment model, per README).

### Security

- **Fixed: SSRF in memes/POTD "fetch from URL" and RSS feed URLs** — new `core/net_guard.py` (`assert_public_http_url`) rejects non-http(s) schemes and hostnames resolving to private/loopback/link-local/reserved addresses. Applied to `memes/router.py::fetch_meme`, `potd/router.py::fetch_potd`, and RSS feed add/edit/fetch in `rss/router.py`.
- **Fixed: SSRF guard bypass via HTTP redirect** — `memes`/`potd` used `httpx.AsyncClient(follow_redirects=True)`, which only validates the initial URL; a malicious server could 302-redirect to an internal address afterwards. New `fetch_public_url()` helper re-validates every redirect hop (max 5) before following it.
- **Fixed: reflected XSS in repo permission check** — `main.py::check_repo_permissions` interpolated `result["error"]` into an HTMX-swapped fragment unescaped; now `html.escape()`d like the sibling `/test` route.
- **Hardened: knowledge `get_entry`** now calls `_reject_traversal` on `category`/`slug`, matching `save_entry` and the attachment-dir logic (defense in depth; git itself already refused to resolve outside-tree paths).
- **Added: stateless CSRF mitigation** — `core/csrf_guard.py`'s `CsrfOriginMiddleware` rejects cross-origin POST/PUT/PATCH/DELETE requests by comparing `Origin`/`Referer` against the request's own `Host`. Session-tied CSRF tokens weren't applicable since the app has no session infrastructure by design.
- Documented in README/README.public: no built-in auth, SSRF guarding, and the CSRF mitigation, with a recommendation to front the app with a reverse-proxy Basic Auth if exposed beyond a trusted network.

### Performance

- `core/settings_store.py::load()` now memoizes the decrypted config in-process, keyed on `settings.json`'s mtime, invalidated on `save()` — previously re-parsed and Fernet-decrypted every secret on every call (~30x per request).
- RSS feed fetch (`feedparser.parse`, blocking) now runs via `asyncio.to_thread` instead of blocking the event loop for every request that misses the Redis cache.
- `vacations/holidays_helper.get_holidays()` is now `lru_cache`d — `count_work_days()` re-instantiated `holidays.Germany()` for the same year/state once per vacation entry.
- `core/cache.py`'s `invalidate_repo()` and `get_stats()` now use `SCAN` (`scan_iter`) instead of blocking `KEYS`.

### Code quality

- **Fixed: `modules/eol/storage.py`** read directly from the git working tree (`Path.glob`) instead of `read_committed`/`list_committed` like every sibling module; now consistent.
- **Fixed: `modules/calendar/router.py`** loaded task entries from *all* repos regardless of the "tasks" module's repo assignment, unlike the vacation/appointment entries loaded alongside it; now uses `get_module_stores("tasks", storage)`.
- Deduplicated the 3x-repeated ICS-profile upsert loop in `core/settings_store.py` into a shared `_upsert_profile()` helper.
- Replaced several bare `except Exception: pass` blocks with `logger.warning`/`logger.debug` calls (RSS cache read/write/clear, calendar entry loading, permission-checker temp-file cleanup, storage pending-push marker) so failures are visible instead of silent.

### Tests

- Added `test_appointments.py::test_list_dedups_same_id_across_repos`, exercising the real multi-repo dedup loop in `appointment_list()` instead of a mocked single-store shortcut.
- Fixed weak `status_code in (400, 503)` / `(404, 503)` assertions in `test_tasks_router.py` to assert the actual, deterministic status code.
- `test_cache.py` updated to mock `scan_iter` instead of `keys`.
- `test_eol_storage.py`'s `FakeGit` now implements `list_committed`/`read_committed` to match the storage rewrite.

**Deferred** (flagged by the review but out of scope for this batch, per Simplicity First — noted for future work in `TECH_DEBT_AUDIT.md`/`HANDOVER.md`): N+1 `git show` pattern across ~15 modules' `list_*()` methods, uncached `GitStorage.get_history()`, synchronous `git ls-remote` inside `repo_health()`, the 9-module shared storage-boilerplate duplication, dedup tests for the remaining ~13 modules, a dedicated `mail_templates` e2e test, and knowledge-router happy-path unit tests.

---

## 2026-07-24 — Widget Dashboard: In-Depth Review Fixes

Follow-up review of the widget dashboard rework below, requested by the maintainer; all 12 findings addressed.

- **Fixed: widgets no longer collapsed to full width on mobile/tablet** — `_packWidgets()` sets `gridColumn` as an inline style, which always beat the responsive `.widget-third`/`.widget-half`/`.widget-full` breakpoint rules in `style.css` (900px/600px), pinning widgets to their desktop width on narrow viewports. `_packWidgets()` now recomputes the effective column span per current viewport width before packing.
- **Fixed: `GET /widgets/calendar-partial` could 500 on an out-of-range `month`** (e.g. `month=13`) — now validates `month` (1-12) and `year` (1-9999) and returns 400, with the calendar load wrapped in a try/except.
- **Fixed: tasks and appointments were loaded from storage independently by every widget that needed them** — extended the existing per-request vacation cache pattern (`_vacation_entries_cached`) with `_tasks_cached()`/`_appointments_cached()`, threaded through `tasks_due`, `tasks_overdue`, `calendar_mini`, `calendar_widget`, `appointments_upcoming`. `next_vacation` now shares the vacation cache too instead of loading entries separately.
- **Fixed: removing widgets in edit mode left gaps** — `removeWidget`/`removeSelected`/`removeAll` now re-run `_packWidgets()` after removal.
- **Fixed: layout-saving requests failed silently** — `_autoArrange`, `_fitWidget`, `_fitAllWidgets`, `_onResizeEnd` now log a console error if the `/widgets/layout` save fails instead of swallowing the failure.
- **Fixed: RSS feed fetches had no timeout** — a cold cache or unreachable feed could block the `/widgets` request indefinitely; `_fetch_feed` now applies a 10s socket timeout.
- **Fixed: potential `javascript:` URI injection from a compromised RSS feed** — article links are now restricted to `http(s)://` schemes.
- Reduced layout flash on load: `#widget-grid` stays hidden until `_packWidgets()` completes once.
- Added touch event support (`touchstart`/`touchmove`/`touchend`) to the widget resize handle, for parity with mouse-based resizing.
- Replaced the hardcoded row height in `_packWidgets()` with a value read from `getComputedStyle`, so it can't silently desync from `style.css`'s `grid-auto-rows`.
- `_load_countdown` now has a top-level try/except like every other widget loader, guarding against non-string settings values reachable via direct API calls.
- Expanded test coverage: the widget-render-crash test now covers all ~38 registered widget types (was 13), added tests for `_valid_settings` rejection paths and `/widgets/calendar-partial` invalid month/year, and an e2e test verifying the mobile-breakpoint packing fix.

---

## 2026-07-24 — Widget Dashboard: Unified Masonry Placement

- **Fixed: the layout shown while editing didn't match the saved dashboard** — edit mode packed widgets into equal-height "shelves" by column width alone (ignoring each widget's actual content height), while the normal view computed real height-based row spans but couldn't backfill gaps left by shorter widgets (browser's default non-dense CSS auto-placement). The two algorithms diverged whenever widgets in the same row had different heights. Replaced both with a single function, `_packWidgets()` in `widgets.html`, used identically in edit mode and the normal view: it tracks each of the 24 columns' current height and drops every widget into the column range that leaves the least unused vertical space, using the widget's real content height. Same inputs (DOM order, column widths, content height) always produce the same layout, so what you see while dragging is exactly what gets saved and rendered afterwards.
- **Fixed: wasted vertical space between widgets of different heights** — a direct consequence of the unified algorithm: shorter widgets no longer leave permanent gaps that later widgets can't fill.
- Removed the red/green drag-hover outline (`drop-ok`/`drop-bad`), which was tied to the old shelf model's "same row" concept and has no equivalent meaning under real per-column masonry packing.

---

## 2026-07-24 — Wider Content Area on Large Viewports

- **Fixed: main content was capped at a fixed 900px, wasting space on wide browser windows** — `.content` now uses a relative `max-width: 95%` instead of a fixed pixel cap, so the usable width scales with the actual browser window instead of stalling at a fixed value.

---

## 2026-07-24 — Knowledge Base: Show All Entries as Tiles

- **Changed: the knowledge base index only showed the 10 most recently added entries as tiles**, with older entries reachable only via search. It now lists all non-pinned entries as tiles, in addition to the search box.

---

## 2026-07-23 — Repo-Wide Review: Security, Performance and Test-Coverage Fixes

Comprehensive review (3 parallel passes: code-quality/security, performance/architecture, test-coverage/docs) requested by the maintainer; all findings addressed.

### Security

- **Plaintext secrets in repo backups weren't disclosed** (`settings.hint.backup_repo` in `locales/en.json`/`de.json`) — hint text now warns the encrypted backup includes all decrypted secrets (SSH keys, PATs, GPG keys, passwords); safety depends entirely on the backup password and the chosen repository's visibility
- **CA-cert tempfile lived outside `DATA_DIR`** (`core/permission_checker.py`) — now created under `DATA_DIR/run`, consistent with the rest of the codebase, instead of the system tempdir
- **Raw exception messages reflected to the client** (`main.py`: `check_repo_permissions`, `import_settings`) — errors are now logged server-side; the client gets a generic message instead of the raw exception (potential info leak of internal paths/config)
- **Widget settings payload committed to git unvalidated** (`modules/widgets/router.py`) — `POST /widgets/layout` and `POST /widgets/{id}/settings` now validate settings as a JSON object under 10 KB before it's written to `settings.json`

### Performance

- **`_load_counts` always computed all ~13 module counters** whenever any stats widget was active — now only computes counts for the actually active `stats_*` widgets
- **Knowledge count fully parsed every entry** just to count them — now uses a cheap recursive listing count (incidentally also fixes a multi-repo inconsistency, since it now uses `get_module_stores`)
- **Vacation entries were reloaded independently by 3 of 4 widget loaders** (calendar mini, calendar widget, vacation balance) — new shared, per-request memoized helper `_vacation_entries_cached()`

### Documentation

- **Stale route reference in `ROADMAP.md`** — audit-log entry still pointed at `/audit`, actual route is `/history`

### Tests

- New 503 tests for missing storage configuration (MOTD create/import/import-file, Notes create, Runbooks create, Links create)
- New unit tests for `_load_counts` (gating via `needed`, knowledge counting) and `_vacation_entries_cached` (memoization, year isolation)
- Strengthened content assertions in `test_calendar_with_year_month` and `test_no_events_empty_state` (History)

### Reviewed and confirmed correct (no change)

- `history`/`operations` "multi-repo inconsistency": both are correct by design — `history` deliberately aggregates all repos and filters afterwards, `operations` uses an explicit user repo selection instead of automatic module resolution
- Bare `except Exception` in ~14+ widget loaders (DASH-07): already tracked in `TECH_DEBT_AUDIT.md` with its own larger planned refactor — deliberately not folded into this batch

---

## 2026-07-23 — Widget Dashboard: Dense Packing While Dragging

- **Fixed: dragging a widget couldn't use free space to the right of another widget** — the grid relied on the browser's default (non-dense) CSS auto-placement together with Sortable.js reordering the DOM; once a row wrapped, later widgets could never backfill into an earlier row's leftover columns even if they'd fit. Edit mode now runs a dense shelf-packing pass (`_repackWidgets()` in `widgets.html`) that places every widget into the first row with enough remaining columns, on every drag change, on "Auto", and after any resize/"Fit"/"Fit All" action.
- **Fixed: the drag preview could show a different result than what you got after dropping** — the live view during a drag is now produced by the same packing pass that runs right before saving, so there's no separate preview step that can diverge from the final layout.
- **New: red/green outline while dragging** — the dragged widget is outlined green when it will land in the row your cursor is currently over, red when dense packing will actually place it in a different row than where you're hovering.

---

## 2026-07-21 — All-Day ICS Exports: One Event Per Range, Not Per Day

- **Fixed: all-day Vacation/Appointment ICS exports created one VEVENT per day** — a multi-day all-day export (e.g. a 7-workday vacation) generated one separate all-day event per day, so calendar apps (Outlook, etc.) imported it as several individual daily entries instead of one contiguous block. When the export profile's "All-day event" checkbox is enabled, `generate_ics()` in both `modules/vacations/ics_generator.py` and `modules/appointments/ics_generator.py` now emits a single VEVENT spanning the full `start_date`–`end_date` range (weekends included for vacations). Timed exports (checkbox off) are unaffected — they still need one event per day since each day has its own start/end time.

---

## 2026-07-20 — "Fit All" Button for Widget Dashboard

- **New "Fit All" button** (Dashboard edit mode) — resizes every widget to its natural content width in one click, next to the existing per-widget "Fit to content" button and the "Auto" (auto-arrange) button. Reuses the same fit-to-content sizing logic as the per-widget button.
- **Fixed: "Fit to content" couldn't actually shrink widgets** — the sizing measurement read `scrollWidth` on a normal block element, which just reports the element's current (stretched) width when its content doesn't overflow, not the content's true intrinsic width. Both "Fit to content" and the new "Fit All" now briefly switch the widget body to shrink-to-fit sizing (`display: inline-block; width: max-content`) to measure the real minimum width before restoring the original styles. Caught by the new "Fit All" e2e test, which force-widened a widget and found it never shrank back.

---

## 2026-07-20 — Tech Debt Audit Fixes (Security, Test Coverage, Cleanup)

Full codebase audit (`TECH_DEBT_AUDIT.md`) produced 72 findings; this session fixed all Critical/High security findings plus a batch of Quick Wins and bounded Medium fixes. See the audit doc for what's intentionally deferred (large architectural refactors).

### Security

- **Reflected XSS in Floccus login** (`links/floccus_api.py`) — `token`/`username` are now `html.escape()`d before being embedded in the login/grant HTML forms; previously exploitable via a plain `GET /index.php/login/v2/grant?token=...` with no valid token required
- **JS-injection via link URL** (`templates/modules/links/list.html`) — copy-URL button now uses `link.url | tojson` instead of raw interpolation inside a single-quoted `onclick` JS string
- **Floccus sync bypassed URL scheme validation** — `create_bookmark`/`update_bookmark` now run the same `_validate_url()` scheme whitelist as the web UI, closing a path for `javascript:`-scheme links to enter via sync
- **Path traversal in Operations Copy/Move** (`operations/router.py`) — item IDs from the client are now validated against the source repo's actual listing (`_get_items`) before being turned into filesystem paths, for all 10 content types
- **CRLF injection in ICS export** (`vacations/ics_generator.py`, `appointments/ics_generator.py`, and the profile-less vacation fallback in `vacations/router.py`) — `_escape_ics()` now normalizes `\r`/`\r\n` before escaping, so a note containing a bare CR can no longer inject fake ICS properties
- **Attachment path traversal defense-in-depth** (`core/storage.py`) — `save_attachment`/`get_attachment`/`delete_attachment` now validate category/slug/filename at the storage layer itself, not only via the router's `_safe_filename` helper
- **Settings import no longer accepts arbitrary top-level keys** — `POST /settings/import` now drops any key not in `settings_store.DEFAULTS` before persisting, closing the largest unvalidated trust boundary in the app

### Fixed

- **Holiday calendar view re-instantiated `holidays.Germany()` per day** (up to 31× per month view) — `get_calendar_data()` now builds the holiday-name map once per request
- **Copy-URL button silently stopped working** — the JS-injection fix above wrapped `onclick="copyUrl({{ link.url | tojson }})"` in double quotes, but `tojson`'s own output is double-quoted JSON, which prematurely terminated the HTML attribute and truncated the handler; switched the attribute to single quotes (`tojson` already escapes both quote types, so this is safe). Caught by CI (`test_copy_url_button_copies_link_url`); added a unit-level regression test so it doesn't require a live browser to catch again

### Changed

- SSH key and CA cert credential temp files now live in `DATA_DIR/run/` instead of the default `/tmp`, consistent with the existing Basic-Auth askpass script
- `ruff check --fix` applied repo-wide (import sorting, unused imports, redundant re-imports); manually fixed remaining `raise ... from e`, ambiguous variable names, mutable default arguments, and dead code the autofixer couldn't handle
- README: fixed stale claims (orphaned-clone path, module diagram missing 5 modules, Operations content-type list, credential temp-file location), documented `REPO_RETRY_INTERVAL_SECONDS`

### Tests

- Added `test_vacation_ics.py` (23 tests) — the Vacations ICS generator had no dedicated test file before this session
- Added path-traversal regression tests for Operations Copy/Move and Knowledge attachments
- Added CRLF-injection regression tests for both ICS generators
- Added a rendered-HTML assertion test for the copy-URL button's `onclick` quoting
- 1308 → 1346 passing tests

---

## 2026-07-20 — Repo Clones Persisted, Auto-Recovery from Network Outages

### Changed

- **Repo clones moved from `/tmp` to `$DATA_DIR/repos`** (persistent volume) — clones now survive container restarts; a restart no longer requires re-cloning, so a VPN/network outage at boot no longer strands the app in a broken state
- **Repo status banner** (`/api/repos-status-banner`) now also reports repos that failed to initialize (unreachable), not just pending offline pushes

### Fixed

- **Repos that failed to init (e.g. VPN not connected yet) were dropped permanently** — previously required a manual repo sync, cache flush, and app restart to recover. `MultiRepoStorage` now tracks failed repos and retries them automatically via the existing background maintenance loop (first pass after 10 s, then every 60 s, retrying each repo at most once per 30 s); no manual intervention needed once connectivity returns

---

## 2026-05-27 — Widget Resize, EOL Expiring Widget, PotD PDF→PNG, Holiday ICS Times

### Added

- **Widget grid: 24 columns** — grid doubled from 12 to 24 columns for denser layout; `third` = 4 cols, `half` = 12 cols, `full` = 24 cols; mobile collapses to 24 cols
- **Widget resize by drag** — drag handle (bottom-right triangle) in edit mode to resize widget width; snaps to nearest column boundary
- **Grid overlay in edit mode** — CSS square-cell grid background visible while editing widgets; `--grid-cell-step` variable keeps cells square regardless of viewport
- **Fit-to-content button** — button in widget edit mode header auto-sizes widget to minimum columns needed for its content (uses `scrollWidth` measurement)
- **EOL Expiring widget** — new widget showing tracked products whose EOL date is within a configurable number of days (default 90); expired items shown in red; threshold configurable in widget settings
- **Holiday ICS: start/end time fields** — time inputs in ICS profile settings (new and edit forms) are shown/hidden based on "all day" checkbox; values are saved and applied to generated ICS events

### Changed

- **PotD: PDFs converted to PNG on upload** — no PDFs stored; each page becomes a separate PNG (150 dpi via `pdf2image`/poppler); existing PDFs migrated lazily on first module access; `pdf.js` removed from frontend
- **Stats widgets: count centered** — number is horizontally centered in the widget on desktop
- **Stats widgets: module label removed** — only icon + count shown (no text label below count)
- **Vacation list: status badge removed** — redundant status text badge removed; status is visible in the dropdown

### Fixed

- **`_load_eol_expiring`**: missing `get_primary_store` import caused `NameError` at runtime
- **Vacation E2E tests** after badge removal: assertions updated from `get_by_text()` to `to_have_value()` on the status select

---

## 2026-05-21 — Widget Masonry, EOL Integration, PotD Daily Image, Stats Compact

### Added

- **Widget dashboard masonry layout** — widgets now pack tightly using CSS `grid-auto-rows: 10px` + JS dynamic `grid-row-end: span N`; no more empty space between widgets of different heights in the same row; edit mode reverts to standard flow for drag-and-drop
- **EOL Tracker in History** — tracked entries now appear in the History view with `product cycle` as title; "EOL Tracker" added to the module filter dropdown
- **EOL Tracker in Global Search** — `/search` queries product name, cycle, label, and notes; results link to the product cycle page
- **EOL Tracker in Operations** — copy/move EOL entries between repos; dedicated tab in the Operations type selector
- **PotD: daily image at top of page** — `/potd` now shows today's entry (image or PDF canvas) at the top with lightbox + copy + open buttons, matching the Memes module layout

### Changed

- **Stats widgets compact on desktop** — `third` (4/12 col) → `span 2/12`; horizontal layout (icon + count + label in one row); font size halved; 6 widgets per row instead of 3; mobile layout unchanged

### Fixed

- **Global search and History** previously had no EOL Tracker entries

---

## 2026-05-18 — Sprint Widget Breakdown, Links Move, Storage & Widget Fixes

### Added

- **Sprint widget** now shows full work-day breakdown: total work days, holidays (−), approved vacation (−), blocked appointments (−), available days with % capacity, and remaining days from today — using the same `capacity_for_sprint()` calculation as the calendar capacity view
- **Links: move between sections** — in bulk-select mode, a section dropdown + Move button appears (when multiple sections are configured); selected links are moved in one commit

### Changed

- **PotD widget** — images now open in lightbox (click to zoom) with copy button; PDFs show a button link to open the file directly (matching the Meme widget behaviour)
- **Meme widget** — click on image opens full-screen lightbox instead of navigating away
- **Meme module page** (`/memes`) — daily meme displayed at the top of the page with lightbox + copy + Next buttons
- **Dashboard link** removed from top navbar (still accessible via sidebar)
- **RSS "Articles on home" setting** (`rss_home_limit`) removed — the RSS widget has its own `max_items` setting

### Fixed

- **`list_committed` / `list_committed_recursive`** now read from `HEAD` instead of `origin/main`; cache is invalidated immediately after commit (not only after successful push) — fixes delete/edit not reflecting immediately in the UI
- **Vacation Balance widget** — `vacation_carryover` is now added to the total days (matching the Vacations module account page)

---

## 2026-05-13 — Widget Dashboard v2, i18n, Home Removal, Bug Fixes

### Added

- **8 new widgets**: `/tmp Usage` (disk bar + repo breakdown), `App Version` (commit hash from `APP_VERSION`), `Repositories` (name, RW/RO, CA/GPG/identity badges, disk size), `Countdown` (configurable date + label, settings popover), `Calendar` (full month grid, HTMX prev/next navigation via `/widgets/calendar-partial`)
- **Copy-to-clipboard button** on Meme and PotD widgets (Clipboard API, `ClipboardItem`)
- **Widget i18n**: 116 new keys in `widget.*` namespace — all 23 widget templates and settings popovers fully translated (EN/DE)
- **Merge checklist**: added i18n completeness check, mobile responsive check, and "New Widget" integration checklist

### Changed

- `sprint` and `vacation_balance` widgets widened: `third` → `half`
- `redis_status` widget widened: `third` → `half`
- `repos` widget now shows CA, GPG, and identity badges (matching Home page)
- `app_version` widget displays `APP_VERSION` env var (short Git commit hash from Docker build arg `GIT_COMMIT`) prominently

### Fixed

- Redis widget showed `dict.keys()` method instead of key count — renamed dict key `keys` → `key_count` (Jinja2 method collision)
- Widget remove-all not persisting — save no longer re-adds omitted widgets
- Available widget panel empty after remove-all — now built from `WIDGET_REGISTRY` instead of layout
- Meme and PotD widgets showed broken images — corrected URL pattern to `/{id}/raw`
- Quick-Add row overflowing on mobile — added `flex-wrap`
- Settings popovers transparent — fixed CSS variable `--card-bg` → `--bg-card`
- EOL mobile overflow — `overflow-x: clip` replaced with `hidden` (clip does not create BFC)
- E2E push-rejected race condition — added `push_retry_count: 3` with random backoff

### Removed

- **Home page** (`/`) replaced by the Widget Dashboard — `/` now redirects to `/widgets`; `home.html` template and all `/api/home/*` HTMX partials removed

### Tests

- `test_widgets_router.py`: 15 → 60 tests; loader unit tests, calendar partial, parametrized rendering
- `test_eol.py`: fixed `DATA_DIR` setup, added coverage for add-page, enrich, and caching
- E2E `test_home.py`: updated to test dashboard redirect and widget grid

---

## 2026-05-10 — Widget Dashboard Expansion

### Added

- **14 new content widgets** for the `/widgets` dashboard: Overdue Tasks, Sprint Countdown, Vacation Balance, Next Vacation, Upcoming Appointments, Favorites, Recent Activity, RSS Feed, Runbooks Overview, Quick Capture, Bookmarks, Picture of the Day, Meme of the Day, System Health, Recent Notes
- Widget registry now covers 31 widgets total (14 stats + 17 content); new widgets default to disabled and can be added via Edit mode

---

## 2026-05-08 — Multilingual Help Pages

### Added

- **Multilingual in-app help** — all 17 module help pages (`/help/{module}`, accessible via `?` shortcut) are now available in English and German; `app/help/en/` contains the English originals, `app/help/de/` the German translations; the route serves the language matching the current UI language setting with automatic fallback to English

---

## 2026-05-08 — Holiday ICS All-Day Flag

### Added

- **Holiday ICS profiles — All-day checkbox** — Settings → Holiday ICS profiles now have an "All-day event" checkbox (create + edit); `all_day: true` is stored in the profile YAML and shown in the card summary

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

- **Picture of the Day (PotD)** — daily content on the start page; file from the data repo (`potd/YYYY-MM-DD.{ext}`); images (JPG/PNG/WebP/GIF) shown inline, PDFs in an embedded viewer (`<iframe>`); falls back to the most recent available file; upload form on the PotD page (max 25 MB); re-uploading for the same date replaces the previous file; delete button per entry; module toggle + repo assignment; home widget lazy-loaded via HTMX (`/api/home/potd`)
- **33 unit tests for PotD** — `_list_files`, `_find_today_or_latest`, router (list, upload, serve, delete, home widget)

### Changed

- **History and audit merged** — `/audit` route and audit module removed; `/history` takes over all of it; time tabs (Today / This Week / This Month / 30d / 90d / 365d / All) with HTMX partial reload; filter bar (module, author, date range) integrated; switching tabs keeps the active filters; commit view grouped (author, timestamp, subject, hash, per-change badges)

---

## 2026-04-30 — MOTD module

### Added

- **MOTD (Message of the Day)** — a daily rotating message at the top of the home page; deterministic by date (same message all day), advanced with the `→` button (HTMX, no reload); offset stored in Redis (expires at midnight)
- **MOTD CRUD** — `GET/POST /motd`, `/motd/new`, `/motd/{id}/edit`, `/motd/{id}/delete`; messages carry an `active` flag (can be disabled without deleting)
- **Mass import** — `GET /motd/import`: textarea (one line = one message) + file upload (`.txt`); a single git commit for the whole import
- **Home widget** — HTMX lazy-load (`/api/home/motd`); accent-coloured left border; next button inside the widget
- **Module toggle + repo assignment** — configurable in settings like every other module
- **Online help** — `GET /help/motd`; `?` button on the list page
- **32 unit tests** — storage (CRUD, bulk_import, get_daily, active filter), router (list, create, edit, delete, import, next)

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

### Modules

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

### Knowledge

- **File attachments** — upload files to any knowledge entry (max 25 MB); download links on detail page; stored in git at `knowledge/{category}/{slug}/{filename}`; deleted with entry; `_safe_filename()` prevents path traversal
- **Category name validation** — `/` blocked in new category names (frontend `pattern` + backend redirect with error)
- **Category-only search** — selecting a category filter with an empty query returns all entries in that category (`GET /knowledge/search?category=X`)

### Notes

- **Archive / Restore** — archive a note to move it out of the active list; `/notes/archive` page with restore button; stored in `notes/archive/{id}.yaml`; `list_committed` is non-recursive so archived notes never appear in the active list
- **Line numbers** — toggleable in Settings → Notes; both detail view and edit form show a scroll-synced gutter; Tab key inserts 2 spaces; ResizeObserver keeps gutter height in sync
- **Jump buttons** — "↓ End" at top and "↑ Top" at bottom of detail view for one-click navigation in long notes
- **Full-width on desktop** — detail and edit expand to full available width on screens wider than 768 px
- **Double-click to edit** — single click opens detail, double-click navigates directly to edit form; `window.getSelection().removeAllRanges()` prevents text-selection from blocking navigation
- **Note encryption** — individual notes encrypted at rest with Fernet; `encrypt` checkbox on form; storage saves `enc:<base64>` + `encrypted: true`; detail/list/search always receive plaintext (transparent decrypt)
- **Cursor-at-end** — edit form positions cursor at end of body textarea via `setSelectionRange(len, len)` after focus

### Tasks

- **Task search** — search bar on `/tasks` filters open and done tasks by title and description via `GET /tasks?q=`; clear button; result count shown
- **Task deadlines in calendar** — open tasks with a due date appear as ✅ markers on the calendar day; high-priority tasks flagged 🔴; legend entry added when tasks are present
- **Success flash** — creating or updating a task redirects to `/tasks?saved=1` with a "Task saved." banner

### Vacations

- **Vacation mail template** — configure a reusable vacation request email in Settings → Vacation → Mail Template (To, CC, Subject, Body); placeholders `{{from}}`, `{{to}}`, `{{working_days}}` replaced at use time; 📧 button on each vacation card when a template is configured; mail preview page (`GET /vacations/{id}/mail`) shows all fields with copy-to-clipboard buttons, "Open in Mail Client" `mailto:` link and "Download .eml" button
- **Vacation EML export** — `GET /vacations/{id}/mail.eml` generates an RFC 2822 `.eml` with placeholders replaced; opens as draft in Outlook, Thunderbird and Apple Mail
- **Sprint capacity bars** — `/calendar/capacity` shows three progress bars per sprint: Gesamt (total work days, Bitcoin Orange), Verfügbar (after vacations/holidays/blocked appointments), Verbleibend (remaining from today); all relative to Gesamt = 100%; auto-scroll to current sprint on load
- **Calendar: hide weekends** — "Show weekends in calendar" in Settings → Vacation; when disabled, calendar renders a 5-column Mon–Fri grid

### Calendar

- **Central Calendar module** — unified `/calendar` aggregating public holidays, vacations and appointments in a single monthly grid; event list below the grid; `/vacations/calendar` and `/appointments/calendar` redirect 301 to `/calendar`; Calendar nav tab visible when Vacations or Appointments enabled
- **Cross-calendar display** — Vacation calendar shows appointment markers (📆); Appointments calendar shows vacation entries (🏖); both show public holidays
- **Today highlight** — current day shown with red background, red border and bold red day number in all calendar views

### History

- **History module** — `/history` filterable git log of all changes; tabs: Today / This Week / This Month / 30d / 90d / 365d / All; deleted entries strikethrough (no link); Redis-cached per range (60–600 s); HTMX tab switching
- **Entry-Versionshistorie (all modules)** — every object has a `/history` page with the full `git log --follow` of its file; commit list with SHA, date, author and message; each entry is expandable showing the unified diff; History button on Knowledge entries, Notes, Tasks (form), Runbooks (detail), Snippets (detail), Mail Templates (list), Ticket Templates (list); `GitStorage.get_file_history()` and `get_file_diff()` with SHA validation against injection; shared partial `partials/history_view.html` for all modules

### Settings & Auth

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

### UI / UX

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

### Testing

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
- UID/GID 1005 in container (matches the deploy user on the host)
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
