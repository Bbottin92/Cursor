import "dotenv/config";

import cors from "cors";
import express from "express";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { InterpretRequestSchema, InterpretResponseSchema } from "@nlui/shared";

import { interpretInstruction } from "./interpret/interpretInstruction.js";

const app = express();

app.use(cors());
app.use(express.json({ limit: "1mb" }));

app.get("/api/health", (_req, res) => {
  res.json({ ok: true });
});

app.post("/api/interpret", async (req, res) => {
  const parsed = InterpretRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: "Invalid request body",
      details: parsed.error.flatten(),
    });
    return;
  }

  try {
    const result = await interpretInstruction(parsed.data);
    const response = InterpretResponseSchema.parse(result);
    res.json(response);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    res.status(500).json({ error: message });
  }
});

// In production, serve the built web app (apps/web/dist).
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webDist = path.resolve(__dirname, "../../web/dist");
const webIndex = path.join(webDist, "index.html");

if (fs.existsSync(webIndex)) {
  app.use(express.static(webDist));
  app.get("*", (_req, res) => res.sendFile(webIndex));
}

const port = Number(process.env.PORT ?? 8787);
app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`[server] listening on http://localhost:${port}`);
});
