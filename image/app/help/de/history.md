# Verlauf

Zeigt alle Änderungen über alle Repos und Module hinweg — gruppiert nach Git-Commit.

## Zeitbereichs-Tabs

| Tab | Zeitraum |
|-----|----------|
| Heute | Commits seit Mitternacht |
| Diese Woche | Seit Montag der aktuellen Woche |
| Dieser Monat | Seit dem 1. des aktuellen Monats |
| Letzte 30 Tage | Gleitendes 30-Tage-Fenster |
| Letzte 3 Monate | 90 Tage |
| Dieses Jahr | Seit dem 1. Januar |
| Alle | Alle verfügbaren Commits (max. 500) |

## Filter

| Filter | Beschreibung |
|--------|--------------|
| **Modul** | Nur Commits eines bestimmten Moduls anzeigen (Wissensdatenbank, Aufgaben, Notizen …) |
| **Autor** | Nach Git-Commit-Autor filtern |
| **Von / Bis** | Auf einen Datumsbereich einschränken (basierend auf dem Commit-Zeitstempel) |

**Zurücksetzen** entfernt alle aktiven Filter, behält aber den aktuellen Zeitbereichs-Tab.

## Zeitstrahl lesen

Jede Zeile ist ein Git-Commit. Pro Commit angezeigt:
- **Autor** — wer die Änderung vorgenommen hat
- **Zeitstempel** — wann der Commit erstellt wurde
- **Betreff** — die Git-Commit-Nachricht (bis 80 Zeichen)
- **Hash** — kurzes Commit-SHA zur Referenz
- **Änderungen** — jede geänderte Datei mit Modul-Badge und Aktion (Hinzugefügt / Geändert / Gelöscht)

Ein Klick auf den Titel navigiert direkt zum Eintrag (nicht verfügbar für gelöschte Einträge).

## Repository-Gesundheit (Einstellungen)

Unter **Einstellungen → Repositories** prüft der **Gesundheits**-Button jedes Repo:

| Feld | Bedeutung |
|------|-----------|
| Erreichbar | Ob der Remote-Git-Host erreichbar ist |
| Letzter Commit | Zeitstempel des letzten lokalen Commits (Warnung bei > 24 h) |
| Dateien | Gesamtanzahl der versionierten Dateien |
| Commits (7 Tage) | Anzahl der Commits in den letzten 7 Tagen |
