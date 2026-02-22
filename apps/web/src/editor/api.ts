import type { EditorState, InterpretResponse } from "@nlui/shared";
import { InterpretResponseSchema } from "@nlui/shared";

export async function interpretInstruction(
  instruction: string,
  state: EditorState,
): Promise<InterpretResponse> {
  const res = await fetch("/api/interpret", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction, state }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Server error (${res.status}): ${text || res.statusText}`);
  }

  const json: unknown = await res.json();
  return InterpretResponseSchema.parse(json);
}

