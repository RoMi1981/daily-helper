# EOL Tracker

The **EOL Tracker** module helps you monitor the end-of-life status of software products and their release cycles, using data from [endoflife.date](https://endoflife.date).

## Tracking Software

Click **Track Software** to open the search page. Start typing a product name (e.g. `python`, `ubuntu`, `nodejs`) — results appear after 300 ms.

Click a product to see all its release cycles with status, latest version, and EOL date. Click **Track** next to any cycle to add it to your dashboard.

## Status Badges

| Badge | Meaning |
|-------|---------|
| **Active** | Supported, EOL date is more than 90 days away |
| **EOL Soon** | EOL date is within the next 90 days |
| **EOL** | End of life reached |
| **Unknown** | No EOL data available from the API |

## Timeline

Click **Timeline** on the EOL list page (grouped by product) to open a Gantt chart showing all tracked cycles for that product:

- **Dark blue** — active support phase
- **Light blue** — security-only support phase
- **Orange** — extended support phase
- **Red line** — today

## Notes

Each tracked entry has a **Notes** field. Click the pencil button on any entry to add or edit free-text notes (e.g. upgrade plans, internal ticket numbers).

## Settings

Enable or disable the EOL Tracker module under **Settings → Modules**. Assign a data repository under **Settings → Repositories**.

Data is stored as `eol/{id}.yaml` in the assigned git repository. API responses are cached in Redis for 24 hours.
