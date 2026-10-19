# Vendored front-end libraries

Served from here instead of a CDN so the UI works without internet access and
cannot change underneath the app: `lucide` was loaded as `@latest` from unpkg,
so every new release reached the page unreviewed, and none of the CDN files had
an integrity check.

| File | Library | Version | Source | License |
| --- | --- | --- | --- | --- |
| `htmx-2.0.4.min.js` | htmx | 2.0.4 | `https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js` | 0BSD |
| `lucide-1.48.0.min.js` | Lucide | 1.48.0 | `https://unpkg.com/lucide@1.48.0/dist/umd/lucide.min.js` | ISC |
| `highlight-11.11.1.min.js` | highlight.js | 11.11.1 | `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/highlight.min.js` | BSD-3-Clause |
| `highlight-11.11.1-github.min.css` | highlight.js theme | 11.11.1 | `…/highlight.js/11.11.1/styles/github.min.css` | BSD-3-Clause |
| `highlight-11.11.1-github-dark.min.css` | highlight.js theme | 11.11.1 | `…/highlight.js/11.11.1/styles/github-dark.min.css` | BSD-3-Clause |

To update: download the new version under its versioned file name, change the
reference in `templates/base.html`, and update this table.
