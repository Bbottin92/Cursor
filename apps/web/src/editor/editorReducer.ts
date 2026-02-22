import type { EditorAction, EditorState, UIElement } from "@nlui/shared";

function mergeStyle(
  base: UIElement["style"] | undefined,
  patch: UIElement["style"] | undefined,
): UIElement["style"] | undefined {
  if (!patch) return base;
  if (!base) return { ...patch };
  return { ...base, ...patch };
}

export function applyEditorAction(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "add": {
      const elements = [...state.elements, action.element];
      const selectedId =
        action.select === false ? state.selectedId : action.element.id;
      return { ...state, elements, selectedId };
    }
    case "update": {
      const idx = state.elements.findIndex((e) => e.id === action.id);
      if (idx === -1) return state;
      const prev = state.elements[idx]!;

      const next: UIElement = {
        ...prev,
        ...action.patch,
        style: mergeStyle(prev.style, action.patch.style),
      };

      const elements = state.elements.slice();
      elements[idx] = next;
      return { ...state, elements };
    }
    case "select":
      return { ...state, selectedId: action.id };
    case "delete": {
      const elements = state.elements.filter((e) => e.id !== action.id);
      const selectedId = state.selectedId === action.id ? null : state.selectedId;
      return { ...state, elements, selectedId };
    }
    case "setLastPointer":
      return { ...state, lastPointer: action.pointer };
    default: {
      const _exhaustive: never = action;
      return state;
    }
  }
}

export function applyEditorActions(state: EditorState, actions: EditorAction[]): EditorState {
  return actions.reduce(applyEditorAction, state);
}

