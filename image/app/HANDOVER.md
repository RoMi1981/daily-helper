# HANDOVER

## Stand — 2026-05-06

### Erledigt (Session 26)

- **E2E-Fix**: `test_countdown_vacation_tomorrow` — days=0 (today) / days=1 (tomorrow) korrekt behandelt
- **Settings-Subnav**: ICS Profiles, Appointment ICS, Holiday ICS als neue Sektionen
- **Holiday ICS Profiles**: Vollständiges Feature — Settings-CRUD, `generate_holiday_ics()`, `/calendar/holiday.ics`, Multi-Download wie bei Vacations
- **Task Dependencies**: `blocked_by` Relation — YAML-Feld, UI in Form (Checkbox-Liste), Badge in `_task_row.html`
- **UI-Normalisierung**: Button-Klassen vereinheitlicht, `page-header` Flex-Layout, Card-Padding standardisiert
- **Docs**: README, user-guide, api.md, MERGE_CHECKLIST.md aktualisiert
- **E2E-Fixes**: Clipboard-Test und Knowledge-Test mit `wait_for` robustifiziert
- **Unified Design System** (`.mod-card`):
  - CSS-Klassen: `.mod-card`, `.mod-card-info`, `.mod-card-title`, `.mod-card-meta`, `.mod-card-actions`
  - Mobile ≤600px: Actions wrappen als volle Zeile unter Content mit Trennlinie
  - notes, runbooks, snippets, links, mail-templates, ticket-templates, motd → alle `.mod-card`
  - task-card / vacation-card: Padding auf `1rem 1.25rem` angehoben, Mobile-Breakpoint ergänzt
  - "New"-Button überall im `page-header`

### Offen / Nächste Schritte

- CI prüfen (letzter Push: `8baa3bc`)
- Knowledge-Modul könnte noch auf gleiche `page-header`-Struktur angepasst werden (hat aber eigenes Grid-Layout)
- PotD/Memes/RSS haben Sonder-Layouts (Bild-Grid, Feed-Reader) — bewusst nicht angefasst

### Wichtige Entscheidungen

- `.mod-card` ist der Standard für alle Text-Listen-Module
- Tasks/Vacations/Appointments behalten `.task-card`/`.vacation-card` (funktionale Spezial-UI), aber gleiche Padding/Gap
- Mobile: `justify-content: flex-start` für Actions (nicht `flex-end`) — Buttons links bündig auf Mobile
- Alle `<form style="margin:0">` in mod-card-actions bleiben inline — kein wrapper div nötig

### Letzte Commits

```
8baa3bc style: unified design system for all module list pages
a5da6d3 style: unify module list visual layout
9ba820b fix(e2e): robustify clipboard and knowledge tests with wait_for
5518c9a docs: add task dependencies + holiday ICS to READMEs; create api.md
8a6b946 refactor(ui): normalize button classes, page-header, card padding
```
