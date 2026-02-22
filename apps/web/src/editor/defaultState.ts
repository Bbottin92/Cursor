import type { EditorState } from "@nlui/shared";

export const DEFAULT_STATE: EditorState = {
  canvas: { width: 900, height: 520 },
  elements: [],
  selectedId: null,
  lastPointer: null,
};

