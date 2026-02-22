import type { EditorAction, InterpretRequest, LLMPlan } from "@nlui/shared";

import { normalizeActions } from "./normalizeActions.js";
import { interpretMock } from "./providers/mock.js";
import { interpretOpenAI } from "./providers/openai.js";

function pickProvider(): "mock" | "openai" {
  const explicit = (process.env.LLM_PROVIDER ?? "").trim().toLowerCase();
  if (explicit === "mock" || explicit === "openai") return explicit;

  // Default: if an API key exists, try OpenAI; otherwise mock.
  return process.env.OPENAI_API_KEY ? "openai" : "mock";
}

export async function interpretInstruction(
  req: InterpretRequest,
): Promise<{ assistantMessage: string; actions: EditorAction[] }> {
  const provider = pickProvider();

  let plan: LLMPlan;
  if (provider === "openai") {
    try {
      plan = await interpretOpenAI(req);
    } catch (err) {
      const fallback = await interpretMock(req);
      const message = err instanceof Error ? err.message : String(err);
      plan = {
        assistantMessage: `[openai failed, used mock] ${message}\n\n${fallback.assistantMessage}`,
        actions: fallback.actions,
      };
    }
  } else {
    plan = await interpretMock(req);
  }

  const actions = normalizeActions(plan.actions, req.state);
  return { assistantMessage: plan.assistantMessage, actions };
}
