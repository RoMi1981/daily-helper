# Bild des Tages

Zeigt täglich einen Eintrag aus der Sammlung auf der Startseite. Die Auswahl ist deterministisch — derselbe Tag zeigt immer denselben Eintrag.

## Unterstützte Formate

| Format | Anzeige |
|--------|---------|
| JPG / JPEG | Inline-Bild |
| PNG | Inline-Bild |
| WebP | Inline-Bild |
| GIF | Inline-Bild (inkl. Animation) |
| PDF | Eingebetteter Viewer (`<iframe>`), springt direkt zur richtigen Seite |

Maximale Dateigröße: **25 MB**.

## Hochladen

Auf der BdT-Seite eine Datei auswählen und **Hochladen** klicken. Bilder werden als einzelner Sammlungseintrag gespeichert. PDFs werden automatisch in Einzelseiten aufgeteilt — jede Seite wird zu einem eigenen Sammlungseintrag (Seitenanzahl wird automatisch erkannt).

## Sammlung

Die Sammlung zeigt alle Einträge als Raster. Virtuelle Einträge (PDF-Seiten) haben einen gestrichelten Rahmen und verweisen auf das Quell-PDF. Das Löschen eines Seiteneintrags entfernt nur diese Seite, nicht das gesamte PDF.

## Speicherung

- Bilddateien: `potd/{id}.{ext}` im Daten-Repo
- PDF-Seiten: `potd/{page_id}.yaml` (Sidecar-Datei mit Verweis auf `{source_id}.pdf`)
