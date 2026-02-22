# Natural-language UI editor (voice + typing)

Prototype that lets you visually edit a UI canvas by typing commands or speaking them, e.g.:

- "I want a round button in the top right corner"
- "No, further down"
- "To the left"
- "Right there! now make it bigger and green"

## Quickstart

```bash
npm install
cp .env.example .env
npm run dev
```

Then open:

- Web app: http://localhost:5173
- Server API: http://localhost:8787/api/health

## LLM modes

By default it runs without any API key (`LLM_PROVIDER=mock`) and uses a simple rule-based interpreter.

To use an OpenAI-compatible LLM, set in `.env`:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
```

## Repo layout

- `apps/web`: Vite + React editor UI
- `apps/server`: Express API (`/api/interpret`)
- `packages/shared`: shared schemas/types for editor state + actions
