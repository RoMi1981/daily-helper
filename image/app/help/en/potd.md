# Picture of the Day

Displays one entry from the collection on the home page each day. The selection is deterministic — the same day always shows the same entry.

## Supported formats

| Format | Display |
|--------|---------|
| JPG / JPEG | Inline image |
| PNG | Inline image |
| WebP | Inline image |
| GIF | Inline image (incl. animation) |
| PDF | Embedded viewer (`<iframe>`), jumps directly to the correct page |

Maximum file size: **25 MB**.

## Upload

Select a file on the PotD page and click **Upload**. Images are saved as a single collection entry. PDFs are automatically split into individual pages — each page becomes its own collection entry (page count is detected automatically).

## Collection

The collection shows all entries as a grid. Virtual entries (PDF pages) have a dashed border and reference the source PDF. Deleting a sidecar entry removes only that page, not the entire PDF.

## Storage

- Image files: `potd/{id}.{ext}` in the data repo
- PDF pages: `potd/{page_id}.yaml` (sidecar referencing `{source_id}.pdf`)
