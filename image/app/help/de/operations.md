# Operationen

Inhalte zwischen zwei Repos kopieren oder verschieben. Sichtbar, wenn mindestens 2 Repos konfiguriert sind.

## Voraussetzungen

Mindestens 2 Repos unter **Einstellungen** konfigurieren. Der Link **🔀 Ops** erscheint dann in der Navigation.

## Inhalte kopieren oder verschieben

1. **Quell-Repo** auswählen
2. **Ziel-Repo** auswählen
3. **Modul** auswählen (Wissensdatenbank, Aufgaben, Urlaub, Termine, Mail-Vorlagen, Ticket-Vorlagen, Notizen, Links, Runbooks, Snippets, MOTD, RSS)
4. Einträge aus der Liste auswählen (für Wissensdatenbank: Kategorien oder einzelne Einträge)
5. **Kopieren** oder **Verschieben** klicken

Beim Verschieben wird der Eintrag aus dem Quell-Repo gelöscht und im Ziel-Repo angelegt. Beide Änderungen werden als separate Git-Commits gespeichert.

## ZIP-Export

Exportiert alle YAML/MD/TXT-Dateien eines Repos als ZIP-Archiv (`daily-helper_{repo}_export.zip`). Nützlich für Backups oder Migrationen.

## ZIP-Import

Importiert ein ZIP-Archiv in ein Repo:

| Modus | Verhalten |
|-------|-----------|
| **Zusammenführen** | Bestehende Einträge bleiben erhalten; neue Einträge aus dem ZIP werden hinzugefügt |
| **Überschreiben** | Alle bestehenden Daten im Ziel-Repo werden ersetzt |

Der Import schreibt automatisch einen Git-Commit. Path-Traversal-Angriffe werden blockiert.
