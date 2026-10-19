# RSS Reader

The **RSS Reader** module displays items from configured RSS and Atom feeds.

## Adding Feeds

Feeds are managed on the RSS Reader page itself. Click **Add Feed** at the top:

- **Name** — displayed as the feed title in the reader
- **Feed URL** — direct URL to the RSS or Atom feed (e.g. `https://www.heise.de/rss/heise-atom.xml`)

Feeds are stored in the repository assigned to RSS under **Settings → Module Repos**. Without one, the page says so instead of showing the button.

## Managing Feeds

The header of the open feed has these actions:

- **☆ Set as default** — the reader opens this feed first
- **Edit** — change name or URL, or untick **Enabled** to hide a feed without deleting it
- **Delete** — removes the feed after a confirmation

## Refreshing

Each feed loads automatically when you open the page. Items are cached for **15 minutes**.

Use the **refresh button** (↻) next to any feed header to force a fresh fetch and clear the cache for that feed.

## Caching

Feed content is stored in Redis with a 15-minute TTL. If Redis is unavailable, feeds are fetched directly on every page load.
