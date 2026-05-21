# EOL-Tracker

Das **EOL-Tracker**-Modul hilft dabei, den End-of-Life-Status von Software-Produkten und deren Release-Zyklen zu überwachen — Daten kommen von [endoflife.date](https://endoflife.date).

## Software tracken

Auf **Track Software** klicken, um die Suchseite zu öffnen. Einen Produktnamen eingeben (z. B. `python`, `ubuntu`, `nodejs`) — Ergebnisse erscheinen nach 300 ms.

Ein Produkt anklicken, um alle Release-Zyklen mit Status, aktueller Version und EOL-Datum zu sehen. Neben einem Zyklus auf **Track** klicken, um ihn hinzuzufügen.

## Status-Badges

| Badge | Bedeutung |
|-------|-----------|
| **Active** | Unterstützt, EOL-Datum mehr als 90 Tage entfernt |
| **EOL Soon** | EOL-Datum innerhalb der nächsten 90 Tage |
| **EOL** | End of Life erreicht |
| **Unknown** | Keine EOL-Daten von der API verfügbar |

## Timeline

Auf der EOL-Listenseite (gruppiert nach Produkt) auf **Timeline** klicken, um ein Gantt-Diagramm aller getrackten Zyklen zu öffnen:

- **Dunkelblau** — aktiver Support
- **Hellblau** — Sicherheits-Support
- **Orange** — erweiterter Support
- **Rote Linie** — heute

## Notizen

Jeder Eintrag hat ein **Notizen**-Feld. Den Stift-Button anklicken, um Freitext-Notizen hinzuzufügen (z. B. Upgrade-Pläne, interne Ticket-Nummern).

## Einstellungen

Das EOL-Tracker-Modul unter **Einstellungen → Module** aktivieren oder deaktivieren. Ein Daten-Repository unter **Einstellungen → Repositories** zuweisen.

Daten werden als `eol/{id}.yaml` im zugewiesenen Git-Repository gespeichert. API-Antworten werden 24 Stunden in Redis gecacht.
