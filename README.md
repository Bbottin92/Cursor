# Website Recovery Baseline

This repository now includes a minimal static website so hosting platforms have
valid content to serve.

## Files added

- `index.html` - main page entrypoint
- `styles.css` - basic responsive styling
- `script.js` - simple page health indicator

## Run locally

From this directory:

```bash
python3 -m http.server 8080
```

Then open `http://localhost:8080`.

## Deploy

Any static host can serve this repository as-is (GitHub Pages, Netlify, Vercel
static output, S3 static hosting, etc.).
