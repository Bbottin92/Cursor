import crypto from "node:crypto";
import type {
  AddElementSpec,
  EditorAction,
  EditorState,
  ElementPatch,
  UIElement,
  UnresolvedEditorAction,
} from "@nlui/shared";

import { applyEditorAction } from "./applyEditorAction.js";

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

function defaultButtonStyle(): UIElement["style"] {
  return {
    backgroundColor: "#2563eb",
    color: "#ffffff",
    borderRadius: 10,
    borderWidth: 0,
  };
}

function resolveTargetId(
  rawId: string,
  state: EditorState,
  lastAddedId: string | null,
): string | null {
  if (rawId === "__selected__") {
    return state.selectedId ?? lastAddedId ?? state.elements.at(-1)?.id ?? null;
  }
  if (rawId === "__last_added__") return lastAddedId;
  return rawId || null;
}

function computePositionForAdd(
  spec: AddElementSpec,
  state: EditorState,
  w: number,
  h: number,
): { x: number; y: number } {
  const margin = spec.margin ?? 16;

  if (typeof spec.x === "number" && typeof spec.y === "number") {
    return { x: spec.x, y: spec.y };
  }

  if (spec.anchor) {
    switch (spec.anchor) {
      case "top_left":
        return { x: margin, y: margin };
      case "top_right":
        return { x: state.canvas.width - w - margin, y: margin };
      case "bottom_left":
        return { x: margin, y: state.canvas.height - h - margin };
      case "bottom_right":
        return { x: state.canvas.width - w - margin, y: state.canvas.height - h - margin };
      case "center":
        return { x: (state.canvas.width - w) / 2, y: (state.canvas.height - h) / 2 };
    }
  }

  // If the user recently clicked, assume they meant "right there".
  if (state.lastPointer) {
    return { x: state.lastPointer.x - w / 2, y: state.lastPointer.y - h / 2 };
  }

  return { x: (state.canvas.width - w) / 2, y: (state.canvas.height - h) / 2 };
}

function normalizeAdd(spec: AddElementSpec, state: EditorState): UIElement {
  // Defaults tuned for a quick prototyping canvas.
  const inferredRound =
    (spec.style?.borderRadius ?? 0) >= 9999 || (spec.text ?? "") === "+";

  const w = clamp(spec.w ?? (inferredRound ? 56 : 120), 8, state.canvas.width);
  const h = clamp(spec.h ?? (inferredRound ? 56 : 44), 8, state.canvas.height);

  const pos = computePositionForAdd(spec, state, w, h);
  const x = clamp(pos.x, 0, state.canvas.width - w);
  const y = clamp(pos.y, 0, state.canvas.height - h);

  const baseStyle = defaultButtonStyle();
  const style = { ...baseStyle, ...(spec.style ?? {}) };
  if (inferredRound && style.borderRadius == null) style.borderRadius = 9999;

  const text = spec.text ?? (inferredRound ? "+" : "Button");

  return {
    id: crypto.randomUUID(),
    kind: spec.kind,
    x,
    y,
    w,
    h,
    text,
    style,
  };
}

function normalizeUpdate(
  element: UIElement,
  patch: {
    x?: number;
    y?: number;
    w?: number;
    h?: number;
    nudge?: { dx?: number; dy?: number };
    resizeDelta?: { dw?: number; dh?: number };
    text?: string;
    style?: Record<string, unknown>;
  },
  state: EditorState,
): ElementPatch {
  let x = element.x;
  let y = element.y;
  let w = element.w;
  let h = element.h;

  if (patch.nudge) {
    x += patch.nudge.dx ?? 0;
    y += patch.nudge.dy ?? 0;
  }

  if (patch.resizeDelta) {
    w += patch.resizeDelta.dw ?? 0;
    h += patch.resizeDelta.dh ?? 0;
  }

  if (typeof patch.x === "number") x = patch.x;
  if (typeof patch.y === "number") y = patch.y;
  if (typeof patch.w === "number") w = patch.w;
  if (typeof patch.h === "number") h = patch.h;

  w = clamp(w, 8, state.canvas.width);
  h = clamp(h, 8, state.canvas.height);
  x = clamp(x, 0, state.canvas.width - w);
  y = clamp(y, 0, state.canvas.height - h);

  const stylePatch = patch.style as UIElement["style"] | undefined;
  const out: ElementPatch = {};

  if (x !== element.x) out.x = x;
  if (y !== element.y) out.y = y;
  if (w !== element.w) out.w = w;
  if (h !== element.h) out.h = h;
  if (typeof patch.text === "string" && patch.text !== element.text) out.text = patch.text;
  if (stylePatch && Object.keys(stylePatch).length) out.style = stylePatch;

  return out;
}

export function normalizeActions(
  unresolved: UnresolvedEditorAction[],
  initialState: EditorState,
): EditorAction[] {
  const out: EditorAction[] = [];
  let working = initialState;
  let lastAddedId: string | null = null;

  for (const a of unresolved) {
    if (a.type === "add") {
      const element = normalizeAdd(a.element, working);
      lastAddedId = element.id;
      const action: EditorAction = { type: "add", element, select: a.select };
      out.push(action);
      working = applyEditorAction(working, action);
      continue;
    }

    if (a.type === "select") {
      const resolved =
        a.id === "__selected__"
          ? working.selectedId
          : a.id === "__last_added__"
            ? lastAddedId
            : a.id;
      const action: EditorAction = {
        type: "select",
        id: typeof resolved === "string" ? resolved : null,
      };
      out.push(action);
      working = applyEditorAction(working, action);
      continue;
    }

    if (a.type === "delete") {
      const id = resolveTargetId(a.id, working, lastAddedId);
      if (!id) continue;
      const action: EditorAction = { type: "delete", id };
      out.push(action);
      working = applyEditorAction(working, action);
      continue;
    }

    if (a.type === "update") {
      const id = resolveTargetId(a.id, working, lastAddedId);
      if (!id) continue;
      const element = working.elements.find((e) => e.id === id);
      if (!element) continue;

      const patch = normalizeUpdate(element, a.patch, working);
      if (Object.keys(patch).length === 0) continue;

      const action: EditorAction = { type: "update", id, patch };
      out.push(action);
      working = applyEditorAction(working, action);
      continue;
    }
  }

  return out;
}

