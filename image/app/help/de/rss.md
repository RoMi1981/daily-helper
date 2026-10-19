# RSS-Reader

Das **RSS-Reader**-Modul zeigt Beiträge aus konfigurierten RSS- und Atom-Feeds.

## Feeds hinzufügen

Feeds werden direkt auf der Seite des RSS-Readers verwaltet. Oben auf **Feed hinzufügen** klicken:

- **Name** — wird als Feed-Titel im Reader angezeigt
- **Feed-URL** — direkte URL zum RSS- oder Atom-Feed (z. B. `https://www.heise.de/rss/heise-atom.xml`)

Gespeichert werden die Feeds im Repository, das RSS unter **Einstellungen → Modul-Repositories** zugewiesen ist. Fehlt es, weist die Seite darauf hin, statt den Button zu zeigen.

## Feeds verwalten

Im Kopf des geöffneten Feeds stehen diese Aktionen:

- **☆ Als Standard setzen** — der Reader öffnet diesen Feed zuerst
- **Bearbeiten** — Name oder URL ändern, oder **Aktiviert** abwählen, um einen Feed auszublenden, ohne ihn zu löschen
- **Löschen** — entfernt den Feed nach einer Rückfrage

## Aktualisieren

Jeder Feed lädt automatisch beim Öffnen der Seite. Beiträge werden **15 Minuten** gecacht.

Den **Aktualisieren**-Button (↻) neben einem Feed-Header anklicken, um einen manuellen Abruf zu erzwingen und den Cache für diesen Feed zu leeren.

## Caching

Feed-Inhalte werden in Redis mit einem 15-Minuten-TTL gespeichert. Falls Redis nicht verfügbar ist, werden Feeds bei jedem Seitenaufruf direkt abgerufen.
