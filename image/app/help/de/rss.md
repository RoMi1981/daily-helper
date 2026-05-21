# RSS-Reader

Das **RSS-Reader**-Modul zeigt Beiträge aus konfigurierten RSS- und Atom-Feeds.

## Feeds hinzufügen

Unter **Einstellungen → RSS-Feeds** auf **Feed hinzufügen** klicken:
- **Name** — wird als Feed-Titel im Reader angezeigt
- **Feed-URL** — direkte URL zum RSS- oder Atom-Feed (z. B. `https://www.heise.de/rss/heise-atom.xml`)

Feeds können einzeln aktiviert oder deaktiviert werden, ohne sie zu löschen.

## Aktualisieren

Jeder Feed lädt automatisch beim Öffnen der Seite. Beiträge werden **15 Minuten** gecacht.

Den **Aktualisieren**-Button (↻) neben einem Feed-Header anklicken, um einen manuellen Abruf zu erzwingen und den Cache für diesen Feed zu leeren.

## Caching

Feed-Inhalte werden in Redis mit einem 15-Minuten-TTL gespeichert. Falls Redis nicht verfügbar ist, werden Feeds bei jedem Seitenaufruf direkt abgerufen.
