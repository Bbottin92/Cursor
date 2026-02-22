import type { EditorAction, EditorState, UIElement } from "@nlui/shared";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { interpretInstruction } from "./api";
import { DEFAULT_STATE } from "./defaultState";
import { applyEditorAction } from "./editorReducer";
import { useSpeechRecognition } from "./useSpeechRecognition";

type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
};

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

function elementCss(e: UIElement): React.CSSProperties {
  const s = e.style ?? {};
  const borderWidth = s.borderWidth ?? 0;
  const borderColor = s.borderColor ?? "#000000";
  return {
    position: "absolute",
    left: e.x,
    top: e.y,
    width: e.w,
    height: e.h,
    backgroundColor: s.backgroundColor ?? "#2563eb",
    borderRadius: s.borderRadius ?? 10,
    color: s.color ?? "#ffffff",
    border: borderWidth ? `${borderWidth}px solid ${borderColor}` : "none",
    fontSize: s.fontSize,
    fontWeight: s.fontWeight,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    userSelect: "none",
  };
}

export function EditorApp() {
  const [state, dispatch] = useReducer(applyEditorAction, DEFAULT_STATE);
  const stateRef = useRef<EditorState>(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: crypto.randomUUID(),
      role: "system",
      content:
        'Try: "I want a round button in the top right corner" then "further down", "to the left", "make it bigger and green".',
    },
  ]);

  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);

  const selected = useMemo(
    () => state.elements.find((e) => e.id === state.selectedId) ?? null,
    [state.elements, state.selectedId],
  );

  const pushMessage = useCallback((m: Omit<ChatMessage, "id">) => {
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), ...m }]);
  }, []);

  const send = useCallback(async (text: string) => {
    const instruction = text.trim();
    if (!instruction) return;
    setInput("");
    pushMessage({ role: "user", content: instruction });
    setIsSending(true);

    try {
      const res = await interpretInstruction(instruction, stateRef.current);
      for (const a of res.actions) dispatch(a);
      pushMessage({ role: "assistant", content: res.assistantMessage });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      pushMessage({ role: "system", content: msg });
    } finally {
      setIsSending(false);
    }
  }, [pushMessage]);

  const speech = useSpeechRecognition({
    onFinal: (t) => {
      if (!t) return;
      setInput(t);
      void send(t);
    },
  });

  return (
    <div className="nlui-shell">
      <header className="nlui-header">
        <div className="nlui-title">Natural-language UI editor</div>
        <div className="nlui-subtitle">Type or speak commands; edits apply immediately.</div>
      </header>

      <main className="nlui-main">
        <section className="nlui-left">
          <Canvas state={state} dispatch={dispatch} selectedId={state.selectedId} />
          <Inspector state={state} selected={selected} dispatch={dispatch} />
        </section>

        <section className="nlui-right">
          <Chat messages={messages} />
          <CommandBar
            value={input}
            onChange={setInput}
            onSend={() => void send(input)}
            isSending={isSending}
            speech={speech}
          />
        </section>
      </main>
    </div>
  );
}

function Canvas(props: {
  state: EditorState;
  selectedId: string | null;
  dispatch: React.Dispatch<EditorAction>;
}) {
  const { state, dispatch, selectedId } = props;
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const ref = useRef<HTMLDivElement | null>(null);
  const [drag, setDrag] = useState<{
    id: string;
    startClientX: number;
    startClientY: number;
    originX: number;
    originY: number;
  } | null>(null);

  const onCanvasMouseDown = (e: React.MouseEvent) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const x = clamp(e.clientX - r.left, 0, state.canvas.width);
    const y = clamp(e.clientY - r.top, 0, state.canvas.height);
    dispatch({ type: "setLastPointer", pointer: { x, y } });
    dispatch({ type: "select", id: null });
  };

  useEffect(() => {
    if (!drag) return;

    const onMove = (e: MouseEvent) => {
      const s = stateRef.current;
      const element = s.elements.find((x) => x.id === drag.id);
      if (!element) return;

      const dx = e.clientX - drag.startClientX;
      const dy = e.clientY - drag.startClientY;
      const x = clamp(drag.originX + dx, 0, s.canvas.width - element.w);
      const y = clamp(drag.originY + dy, 0, s.canvas.height - element.h);
      dispatch({ type: "update", id: drag.id, patch: { x, y } });
    };

    const onUp = () => setDrag(null);

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp, { once: true });

    return () => {
      window.removeEventListener("mousemove", onMove);
    };
  }, [drag, dispatch]);

  return (
    <div className="nlui-canvas-wrap">
      <div
        ref={ref}
        className="nlui-canvas"
        style={{ width: state.canvas.width, height: state.canvas.height }}
        onMouseDown={onCanvasMouseDown}
      >
        <div className="nlui-grid" />

        {state.lastPointer ? (
          <div
            className="nlui-pointer"
            style={{
              left: state.lastPointer.x,
              top: state.lastPointer.y,
            }}
            title="last click"
          />
        ) : null}

        {state.elements.map((e) => {
          const isSelected = e.id === selectedId;
          const cls = isSelected ? "nlui-el nlui-el-selected" : "nlui-el";
          const onDown = (evt: React.MouseEvent) => {
            evt.stopPropagation();
            dispatch({ type: "select", id: e.id });
            setDrag({
              id: e.id,
              startClientX: evt.clientX,
              startClientY: evt.clientY,
              originX: e.x,
              originY: e.y,
            });
          };

          // Render as a <button> for a more realistic preview, but neutralize native styles.
          return (
            <button
              key={e.id}
              className={cls}
              style={elementCss(e)}
              onMouseDown={onDown}
              type="button"
            >
              {e.text ?? ""}
            </button>
          );
        })}
      </div>
      <div className="nlui-canvas-hint">
        Click to set a target point. Drag elements to reposition.
      </div>
    </div>
  );
}

function Inspector(props: {
  state: EditorState;
  selected: UIElement | null;
  dispatch: React.Dispatch<EditorAction>;
}) {
  const { state, selected, dispatch } = props;
  return (
    <div className="nlui-inspector">
      <div className="nlui-panel-title">Inspector</div>
      {selected ? (
        <div className="nlui-inspector-grid">
          <div className="nlui-k">id</div>
          <div className="nlui-v">{selected.id}</div>
          <div className="nlui-k">x / y</div>
          <div className="nlui-v">
            {Math.round(selected.x)} / {Math.round(selected.y)}
          </div>
          <div className="nlui-k">w / h</div>
          <div className="nlui-v">
            {Math.round(selected.w)} / {Math.round(selected.h)}
          </div>
          <div className="nlui-k">bg</div>
          <div className="nlui-v">{selected.style?.backgroundColor ?? "-"}</div>
          <div className="nlui-k">radius</div>
          <div className="nlui-v">{selected.style?.borderRadius ?? "-"}</div>
        </div>
      ) : (
        <div className="nlui-muted">No element selected.</div>
      )}

      <div className="nlui-panel-title" style={{ marginTop: 12 }}>
        Elements ({state.elements.length})
      </div>
      {state.elements.length ? (
        <div className="nlui-element-list">
          {state.elements.map((e) => (
            <button
              key={e.id}
              className={
                e.id === state.selectedId
                  ? "nlui-list-item nlui-list-item-selected"
                  : "nlui-list-item"
              }
              type="button"
              onClick={() => dispatch({ type: "select", id: e.id })}
            >
              {e.kind} · {e.text ?? "(no text)"}
            </button>
          ))}
        </div>
      ) : (
        <div className="nlui-muted">Nothing yet. Add a button with a command.</div>
      )}
    </div>
  );
}

function Chat(props: { messages: ChatMessage[] }) {
  const { messages } = props;
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [messages.length]);

  return (
    <div className="nlui-chat" ref={ref}>
      {messages.map((m) => (
        <div key={m.id} className={`nlui-msg nlui-msg-${m.role}`}>
          <div className="nlui-msg-role">{m.role}</div>
          <div className="nlui-msg-content">{m.content}</div>
        </div>
      ))}
    </div>
  );
}

function CommandBar(props: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  isSending: boolean;
  speech: {
    isSupported: boolean;
    isListening: boolean;
    interim: string;
    error: string | null;
    start: () => void;
    stop: () => void;
  };
}) {
  const { value, onChange, onSend, isSending, speech } = props;
  return (
    <div className="nlui-commandbar">
      <div className="nlui-commandbar-row">
        <input
          className="nlui-input"
          value={value}
          placeholder='e.g. "make it bigger and green"'
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          disabled={isSending}
        />

        <button
          className="nlui-btn"
          type="button"
          onClick={onSend}
          disabled={isSending || !value.trim()}
          title="Send"
        >
          Send
        </button>

        <button
          className="nlui-btn"
          type="button"
          disabled={!speech.isSupported}
          onClick={() => (speech.isListening ? speech.stop() : speech.start())}
          title={speech.isSupported ? "Voice input" : "SpeechRecognition not supported"}
        >
          {speech.isListening ? "Stop mic" : "Mic"}
        </button>
      </div>

      {speech.interim ? (
        <div className="nlui-muted">Listening: {speech.interim}</div>
      ) : null}
      {speech.error ? <div className="nlui-error">Mic error: {speech.error}</div> : null}
    </div>
  );
}

