# RSS Reader

The **RSS Reader** module displays items from configured RSS and Atom feeds.

## Adding Feeds

Go to **Settings → RSS Feeds** and click **Add Feed**:
- **Name** — displayed as the feed title in the reader
- **Feed URL** — direct URL to the RSS or Atom feed (e.g. `https://www.heise.de/rss/heise-atom.xml`)

Feeds can be enabled or disabled individually without deleting them.

## Refreshing

Each feed loads automatically when you open the page. Items are cached for **15 minutes**.

Use the **refresh button** (↻) next to any feed header to force a fresh fetch and clear the cache for that feed.

## Caching

Feed content is stored in Redis with a 15-minute TTL. If Redis is unavailable, feeds are fetched directly on every page load.
