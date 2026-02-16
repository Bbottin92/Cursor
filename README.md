# Cursor

A modern, responsive website built with HTML and CSS — deployed via GitHub Pages.

## Live Site

Once GitHub Pages is enabled, the site will be available at:
`https://bbottin92.github.io/Cursor/`

## Setup

### Enable GitHub Pages

1. Go to your repository **Settings** > **Pages**
2. Under **Source**, select **GitHub Actions**
3. The included workflow (`.github/workflows/deploy.yml`) will automatically deploy on every push to `main`

### Local Development

Simply open `index.html` in your browser:

```bash
open index.html
```

## Project Structure

```
.
├── index.html                  # Main website page
├── styles.css                  # All styles
├── .github/workflows/
│   └── deploy.yml              # GitHub Pages deployment workflow
└── README.md
```
