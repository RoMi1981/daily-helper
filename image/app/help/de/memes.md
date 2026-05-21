# Memes

Zeigt täglich ein Meme aus der Sammlung auf der Startseite. Die Auswahl ist deterministisch — derselbe Tag zeigt immer dasselbe Meme.

## Unterstützte Formate

| Format | Anzeige |
|--------|---------|
| JPG / JPEG | Inline-Bild |
| PNG | Inline-Bild |
| WebP | Inline-Bild |
| GIF | Inline-Bild (inkl. Animation) |

Maximale Dateigröße: **25 MB**.

## Hochladen

Auf der Memes-Seite eine Datei auswählen und **Hochladen** klicken, oder eine URL einfügen und **Von URL laden** klicken, um ein Bild direkt herunterzuladen und zu speichern.

## Sammlung

Die Sammlung zeigt alle Memes als Raster mit Vorschaubild. Jeder Eintrag hat einen Ansehen-Button (öffnet das Originalbild) und einen Löschen-Button.

## Tagesanzeige

Auf der Startseite wird das heutige Meme angezeigt. Den **›**-Button anklicken, um für heute zum nächsten Meme zu wechseln — der Offset wird in Redis gespeichert und setzt sich um Mitternacht zurück.

## Speicherung

- Bilddateien: `memes/{id}.{ext}` im Daten-Repo
