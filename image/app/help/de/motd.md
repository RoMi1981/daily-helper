# Nachricht des Tages (MOTD)

Das MOTD-Modul zeigt täglich eine rotierende Nachricht oben auf der Startseite — nützlich für Motivationszitate, Teamankündigungen oder tägliche Erinnerungen.

## Funktionsweise

- Jeden Tag wird eine Nachricht deterministisch angezeigt (den ganzen Tag dieselbe Nachricht für alle Nutzer)
- Der **→**-Button auf der Startseite wechselt zur nächsten Nachricht für den Rest des Tages
- Am nächsten Tag rotieren die Nachrichten automatisch weiter

## Nachrichten verwalten

| Aktion | Vorgehensweise |
|--------|----------------|
| Nachricht hinzufügen | **+ Neue Nachricht** |
| Bearbeiten / Deaktivieren | **Bearbeiten**-Button an einer Nachricht |
| Löschen | **Löschen**-Button an einer Nachricht |
| Viele auf einmal importieren | **Liste importieren**-Button |

## Aktiv / Inaktiv

Beim Bearbeiten einer Nachricht **Aktiv** deaktivieren, um sie aus der täglichen Rotation auszuschließen, ohne sie zu löschen. Inaktive Nachrichten werden in der Liste durchgestrichen angezeigt.

## Massenimport

**Liste importieren** anklicken:
- **Nachrichten einfügen** — eine Nachricht pro Zeile im Textfeld eingeben
- **Datei hochladen** — eine einfache `.txt`-Datei hochladen (UTF-8, eine Nachricht pro Zeile)

Leere Zeilen werden ignoriert. Alle importierten Nachrichten werden in einem einzigen Git-Commit gespeichert.

## Moduleinstellungen

Das MOTD-Modul unter **Einstellungen → Module** aktivieren oder deaktivieren. Unter **Einstellungen → Modul-Repos** einem bestimmten Repository zuweisen.
