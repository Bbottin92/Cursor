# Cursor Website

This repository now contains a production-ready static website starter.

## Local preview

Run a local web server from the repository root:

```bash
python3 -m http.server 8000
```

Then open:

- http://localhost:8000

## Deploy to GitHub Pages

A workflow is included at `.github/workflows/deploy-pages.yml`.

After merging to `main`, GitHub Actions will publish the site to Pages.

## Files

- `index.html` - site entry page
- `styles.css` - styling
- `script.js` - tiny client-side status script
