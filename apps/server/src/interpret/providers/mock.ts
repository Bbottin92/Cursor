import type {
  Anchor,
  ElementStylePatch,
  InterpretRequest,
  LLMPlan,
  UnresolvedEditorAction,
} from "@nlui/shared";

const COLOR_WORDS: Record<string, string> = {
  green: "#22c55e",
  red: "#ef4444",
  blue: "#3b82f6",
  yellow: "#eab308",
  orange: "#f97316",
  purple: "#a855f7",
  pink: "#ec4899",
  black: "#111827",
  white: "#ffffff",
  gray: "#6b7280",
  grey: "#6b7280",
};

function parseAnchor(text: string): Anchor | undefined {
  const t = text.toLowerCase();
  if (t.includes("top") && t.includes("right")) return "top_right";
  if (t.includes("top") && t.includes("left")) return "top_left";
  if (t.includes("bottom") && t.includes("right")) return "bottom_right";
  if (t.includes("bottom") && t.includes("left")) return "bottom_left";
  if (t.includes("center") || t.includes("middle")) return "center";
  return undefined;
}

function parseFirstColor(text: string): string | undefined {
  const t = text.toLowerCase();
  for (const [word, value] of Object.entries(COLOR_WORDS)) {
    const re = new RegExp(`\\b${word}\\b`, "i");
    if (re.test(t)) return value;
  }
  return undefined;
}

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

export async function interpretMock(req: InterpretRequest): Promise<LLMPlan> {
  const raw = req.instruction.trim();
  const text = raw.toLowerCase();
  const actions: UnresolvedEditorAction[] = [];

  const hasButtonWord = /\bbutton\b/i.test(text);
  const wantsNew =
    hasButtonWord &&
    /\b(add|create|insert|new|place|put|want|need|make)\b/i.test(text);

  const wantsRound = /\b(round|circle|circular)\b/i.test(text);
  const wantsSquare = /\b(square|sharp corners)\b/i.test(text);

  const color = parseFirstColor(text);
  const style: ElementStylePatch = {};
  if (color) style.backgroundColor = color;
  if (wantsRound) style.borderRadius = 9999;
  if (wantsSquare) style.borderRadius = 0;

  // --- Create ---
  if (wantsNew) {
    const anchor = parseAnchor(text);
    const isRound = wantsRound;

    const w = isRound ? 56 : 120;
    const h = isRound ? 56 : 44;

    actions.push({
      type: "add",
      select: true,
      element: {
        kind: "button",
        anchor,
        w,
        h,
        text: isRound ? "+" : "Button",
        style: Object.keys(style).length ? style : undefined,
      },
    });
  }

  // --- Moves / nudges ---
  const isRightThere = /\bright there\b/i.test(text);
  const stepBase = /\bfurther\b/i.test(text) || /\bmuch\b/i.test(text) ? 64 : 32;

  let dx = 0;
  let dy = 0;

  if (!isRightThere) {
    if (/\b(to the )?left\b/i.test(text)) dx -= stepBase;
    if (/\b(to the )?right\b/i.test(text)) dx += stepBase;
    if (/\b(down|lower|below)\b/i.test(text)) dy += stepBase;
    if (/\b(up|higher|above)\b/i.test(text)) dy -= stepBase;
  }

  if (dx !== 0 || dy !== 0) {
    actions.push({
      type: "update",
      id: "__selected__",
      patch: {
        nudge: { dx, dy },
      },
    });
  }

  // --- Absolute placement (e.g. "top right corner") for selected element ---
  // Only applies when NOT creating a new element in this instruction.
  if (!wantsNew) {
    const anchor = parseAnchor(text);
    const margin = 16;
    if (anchor) {
      const selected =
        req.state.elements.find((e) => e.id === req.state.selectedId) ??
        req.state.elements.at(-1);
      if (selected) {
        const x =
          anchor === "top_right" || anchor === "bottom_right"
            ? req.state.canvas.width - selected.w - margin
            : anchor === "center"
              ? (req.state.canvas.width - selected.w) / 2
              : margin;
        const y =
          anchor === "bottom_left" || anchor === "bottom_right"
            ? req.state.canvas.height - selected.h - margin
            : anchor === "center"
              ? (req.state.canvas.height - selected.h) / 2
              : margin;

        actions.push({
          type: "update",
          id: "__selected__",
          patch: {
            x: clamp(x, 0, req.state.canvas.width - selected.w),
            y: clamp(y, 0, req.state.canvas.height - selected.h),
          },
        });
      }
    }
  }

  // --- Resizing ---
  const wantsBigger = /\b(bigger|larger|increase size)\b/i.test(text);
  const wantsSmaller = /\b(smaller|decrease size)\b/i.test(text);
  if (wantsBigger || wantsSmaller) {
    const delta = wantsBigger ? stepBase : -stepBase;
    actions.push({
      type: "update",
      id: "__selected__",
      patch: {
        resizeDelta: { dw: delta, dh: delta },
      },
    });
  }

  // --- Styling ---
  if (Object.keys(style).length) {
    actions.push({
      type: "update",
      id: "__selected__",
      patch: { style },
    });
  }

  const assistantMessage =
    actions.length === 0
      ? "Mock: I didn't recognize an edit. Try: 'add a button', 'move left', 'make it green'."
      : `Mock: applied ${actions.length} action${actions.length === 1 ? "" : "s"}.`;

  return { assistantMessage, actions };
}
