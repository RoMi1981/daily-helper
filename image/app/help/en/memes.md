# Memes

Displays one meme from the collection on the home page each day. The selection is deterministic — the same day always shows the same meme.

## Supported formats

| Format | Display |
|--------|---------|
| JPG / JPEG | Inline image |
| PNG | Inline image |
| WebP | Inline image |
| GIF | Inline image (incl. animation) |

Maximum file size: **25 MB**.

## Upload

Select a file on the Memes page and click **Upload**, or paste a URL and click **Fetch from URL** to download and store an image directly.

## Collection

The collection shows all memes as a grid with thumbnail preview. Each entry has a View button (opens raw image) and a Delete button.

## Daily display

The home page shows today's meme. Click the **›** button to advance to the next meme for today — the offset is stored in Redis and resets at midnight.

## Storage

- Image files: `memes/{id}.{ext}` in the data repo
