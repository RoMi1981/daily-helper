# Message of the Day (MOTD)

The MOTD module displays a daily rotating message at the top of the home page — useful for motivational quotes, team announcements, or daily reminders.

## How it works

- Each day one message is shown deterministically (same message all day for all users)
- The **→** button on the home page advances to the next message for the rest of the day
- Messages rotate automatically the next day

## Managing messages

| Action | How |
|---|---|
| Add a message | **+ New Message** |
| Edit / deactivate | **Edit** button on a message |
| Delete | **Delete** button on a message |
| Import many at once | **Import list** button |

## Active / inactive

Uncheck **Active** when editing a message to exclude it from the daily rotation without deleting it. Inactive messages are shown with strikethrough in the list.

## Mass import

Click **Import list** to:
- **Paste messages** — enter one message per line in the text area
- **Upload file** — upload a plain text `.txt` file (UTF-8, one message per line)

Empty lines are ignored. All imported messages are saved in a single git commit.

## Module settings

Enable or disable the MOTD module under **Settings → Modules**. You can also assign it to a specific repository under **Settings → Module Repos**.
