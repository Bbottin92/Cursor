import OpenAI from "openai";
import type { InterpretRequest, LLMPlan } from "@nlui/shared";
import { LLMPlanSchema } from "@nlui/shared";

const SYSTEM_PROMPT = `
You translate natural-language UI editing commands into a structured action plan.

You are controlling a simple 2D UI canvas.
- Coordinate system: (0,0) is top-left of the canvas.
- Increasing x moves right, increasing y moves down.
- Elements are absolutely positioned rectangles with {x,y,w,h}.

Return a plan with:
- assistantMessage: short, user-facing
- actions: array of actions

Action types you may return:
- add: create a new element. Provide element.kind="button" and optionally:
  - anchor: one of top_left, top_right, bottom_left, bottom_right, center
  - margin: number (px)
  - x,y,w,h
  - text
  - style: backgroundColor, borderRadius, color, borderColor, borderWidth, fontSize, fontWeight
- update: modify an existing element:
  - id can be a real id from state OR "__selected__" to refer to selectedId
  - patch can set x,y,w,h,text,style
  - patch can also include nudge {dx,dy} and/or resizeDelta {dw,dh} for relative adjustments
- select: { id: string | null | "__last_added__" | "__selected__" }
- delete: { id: string | "__selected__" }

Guidance:
- For "left/right/up/down/further down", prefer update with patch.nudge.
- For "bigger/smaller", prefer update with patch.resizeDelta.
- For "round button", set borderRadius to a large value (e.g. 9999) and consider w ~= h.
- If user refers to "it", target the selected element using id="__selected__".
- Keep actions minimal and do not invent element ids not present in state.
`.trim();

const PLAN_TOOL_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["assistantMessage", "actions"],
  properties: {
    assistantMessage: { type: "string" },
    actions: {
      type: "array",
      items: {
        anyOf: [
          {
            type: "object",
            additionalProperties: false,
            required: ["type", "element"],
            properties: {
              type: { const: "add" },
              select: { type: "boolean" },
              element: {
                type: "object",
                additionalProperties: false,
                required: ["kind"],
                properties: {
                  kind: { const: "button" },
                  x: { type: "number" },
                  y: { type: "number" },
                  w: { type: "number", minimum: 1 },
                  h: { type: "number", minimum: 1 },
                  anchor: {
                    type: "string",
                    enum: [
                      "top_left",
                      "top_right",
                      "bottom_left",
                      "bottom_right",
                      "center",
                    ],
                  },
                  margin: { type: "number" },
                  text: { type: "string" },
                  style: {
                    type: "object",
                    additionalProperties: false,
                    properties: {
                      backgroundColor: { type: "string" },
                      borderRadius: { type: "number" },
                      color: { type: "string" },
                      borderColor: { type: "string" },
                      borderWidth: { type: "number" },
                      fontSize: { type: "number" },
                      fontWeight: { type: "number" },
                    },
                  },
                },
              },
            },
          },
          {
            type: "object",
            additionalProperties: false,
            required: ["type", "id", "patch"],
            properties: {
              type: { const: "update" },
              id: { type: "string" },
              patch: {
                type: "object",
                additionalProperties: false,
                properties: {
                  x: { type: "number" },
                  y: { type: "number" },
                  w: { type: "number", minimum: 1 },
                  h: { type: "number", minimum: 1 },
                  text: { type: "string" },
                  style: {
                    type: "object",
                    additionalProperties: false,
                    properties: {
                      backgroundColor: { type: "string" },
                      borderRadius: { type: "number" },
                      color: { type: "string" },
                      borderColor: { type: "string" },
                      borderWidth: { type: "number" },
                      fontSize: { type: "number" },
                      fontWeight: { type: "number" },
                    },
                  },
                  nudge: {
                    type: "object",
                    additionalProperties: false,
                    properties: {
                      dx: { type: "number" },
                      dy: { type: "number" },
                    },
                  },
                  resizeDelta: {
                    type: "object",
                    additionalProperties: false,
                    properties: {
                      dw: { type: "number" },
                      dh: { type: "number" },
                    },
                  },
                },
              },
            },
          },
          {
            type: "object",
            additionalProperties: false,
            required: ["type", "id"],
            properties: {
              type: { const: "select" },
              id: {
                anyOf: [
                  { type: "string" },
                  { type: "null" },
                  { const: "__last_added__" },
                  { const: "__selected__" },
                ],
              },
            },
          },
          {
            type: "object",
            additionalProperties: false,
            required: ["type", "id"],
            properties: {
              type: { const: "delete" },
              id: { type: "string" },
            },
          },
        ],
      },
    },
  },
} as const;

export async function interpretOpenAI(req: InterpretRequest): Promise<LLMPlan> {
  if (!process.env.OPENAI_API_KEY) {
    throw new Error("OPENAI_API_KEY is not set");
  }

  const client = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY,
    baseURL: process.env.OPENAI_BASE_URL,
  });

  const model = process.env.OPENAI_MODEL || "gpt-4o-mini";

  const completion = await client.chat.completions.create({
    model,
    temperature: 0.2,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      {
        role: "user",
        content: [
          "Editor state JSON:",
          JSON.stringify(req.state),
          "",
          "User instruction:",
          req.instruction,
        ].join("\n"),
      },
    ],
    tools: [
      {
        type: "function",
        function: {
          name: "plan_editor_actions",
          description:
            "Return a structured editor action plan (assistantMessage + actions).",
          // The OpenAI SDK expects JSON schema here.
          parameters: PLAN_TOOL_SCHEMA,
        },
      },
    ],
    tool_choice: { type: "function", function: { name: "plan_editor_actions" } },
  });

  const call = completion.choices[0]?.message?.tool_calls?.[0];
  if (!call || call.type !== "function" || call.function.name !== "plan_editor_actions") {
    throw new Error("Model did not return a plan tool call");
  }

  let args: unknown;
  try {
    args = JSON.parse(call.function.arguments || "{}");
  } catch {
    throw new Error("Model tool arguments were not valid JSON");
  }

  const parsed = LLMPlanSchema.safeParse(args);
  if (!parsed.success) {
    throw new Error(`Invalid plan schema from model: ${parsed.error.message}`);
  }

  return parsed.data;
}
