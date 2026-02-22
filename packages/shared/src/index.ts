import { z } from "zod";

export const AnchorSchema = z.enum([
  "top_left",
  "top_right",
  "bottom_left",
  "bottom_right",
  "center",
]);
export type Anchor = z.infer<typeof AnchorSchema>;

export const ElementKindSchema = z.enum(["button"]);
export type ElementKind = z.infer<typeof ElementKindSchema>;

export const PointerSchema = z
  .object({
    x: z.number(),
    y: z.number(),
  })
  .strict();
export type Pointer = z.infer<typeof PointerSchema>;

export const CanvasSchema = z
  .object({
    width: z.number().positive(),
    height: z.number().positive(),
  })
  .strict();
export type Canvas = z.infer<typeof CanvasSchema>;

export const ElementStyleSchema = z
  .object({
    backgroundColor: z.string().optional(),
    borderRadius: z.number().optional(),
    color: z.string().optional(),
    borderColor: z.string().optional(),
    borderWidth: z.number().optional(),
    fontSize: z.number().optional(),
    fontWeight: z.number().optional(),
  })
  .strict();
export type ElementStyle = z.infer<typeof ElementStyleSchema>;

export const ElementStylePatchSchema = ElementStyleSchema.partial().strict();
export type ElementStylePatch = z.infer<typeof ElementStylePatchSchema>;

export const UIElementSchema = z
  .object({
    id: z.string().min(1),
    kind: ElementKindSchema,
    x: z.number(),
    y: z.number(),
    w: z.number().positive(),
    h: z.number().positive(),
    text: z.string().optional(),
    style: ElementStyleSchema.optional(),
  })
  .strict();
export type UIElement = z.infer<typeof UIElementSchema>;

export const EditorStateSchema = z
  .object({
    canvas: CanvasSchema,
    elements: z.array(UIElementSchema),
    selectedId: z.string().nullable(),
    lastPointer: PointerSchema.nullable().optional(),
  })
  .strict();
export type EditorState = z.infer<typeof EditorStateSchema>;

export const ElementPatchSchema = z
  .object({
    x: z.number().optional(),
    y: z.number().optional(),
    w: z.number().positive().optional(),
    h: z.number().positive().optional(),
    text: z.string().optional(),
    style: ElementStylePatchSchema.optional(),
  })
  .strict();
export type ElementPatch = z.infer<typeof ElementPatchSchema>;

export const EditorActionSchema = z.discriminatedUnion("type", [
  z
    .object({
      type: z.literal("add"),
      element: UIElementSchema,
      select: z.boolean().optional(),
    })
    .strict(),
  z
    .object({
      type: z.literal("update"),
      id: z.string().min(1),
      patch: ElementPatchSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("select"),
      id: z.string().nullable(),
    })
    .strict(),
  z
    .object({
      type: z.literal("delete"),
      id: z.string().min(1),
    })
    .strict(),
  z
    .object({
      type: z.literal("setLastPointer"),
      pointer: PointerSchema.nullable(),
    })
    .strict(),
]);
export type EditorAction = z.infer<typeof EditorActionSchema>;

// --- Unresolved actions (LLM -> server), allowing placeholders and deltas ---

export const TargetIdSchema = z.string().min(1);
export const TargetIdOrSelectedSchema = z.union([
  TargetIdSchema,
  z.literal("__selected__"),
]);
export type TargetIdOrSelected = z.infer<typeof TargetIdOrSelectedSchema>;

export const AddElementSpecSchema = z
  .object({
    kind: ElementKindSchema,
    x: z.number().optional(),
    y: z.number().optional(),
    w: z.number().positive().optional(),
    h: z.number().positive().optional(),
    anchor: AnchorSchema.optional(),
    margin: z.number().optional(),
    text: z.string().optional(),
    style: ElementStylePatchSchema.optional(),
  })
  .strict();
export type AddElementSpec = z.infer<typeof AddElementSpecSchema>;

export const DeltaSchema = z
  .object({
    dx: z.number().optional(),
    dy: z.number().optional(),
  })
  .strict();
export type Delta = z.infer<typeof DeltaSchema>;

export const ResizeDeltaSchema = z
  .object({
    dw: z.number().optional(),
    dh: z.number().optional(),
  })
  .strict();
export type ResizeDelta = z.infer<typeof ResizeDeltaSchema>;

export const UnresolvedElementPatchSchema = z
  .object({
    x: z.number().optional(),
    y: z.number().optional(),
    w: z.number().positive().optional(),
    h: z.number().positive().optional(),
    nudge: DeltaSchema.optional(),
    resizeDelta: ResizeDeltaSchema.optional(),
    text: z.string().optional(),
    style: ElementStylePatchSchema.optional(),
  })
  .strict();
export type UnresolvedElementPatch = z.infer<typeof UnresolvedElementPatchSchema>;

export const UnresolvedEditorActionSchema = z.discriminatedUnion("type", [
  z
    .object({
      type: z.literal("add"),
      element: AddElementSpecSchema,
      select: z.boolean().optional(),
    })
    .strict(),
  z
    .object({
      type: z.literal("update"),
      id: TargetIdOrSelectedSchema,
      patch: UnresolvedElementPatchSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("select"),
      id: z.union([
        TargetIdSchema,
        z.null(),
        z.literal("__last_added__"),
        z.literal("__selected__"),
      ]),
    })
    .strict(),
  z
    .object({
      type: z.literal("delete"),
      id: TargetIdOrSelectedSchema,
    })
    .strict(),
]);
export type UnresolvedEditorAction = z.infer<typeof UnresolvedEditorActionSchema>;

export const LLMPlanSchema = z
  .object({
    assistantMessage: z.string(),
    actions: z.array(UnresolvedEditorActionSchema),
  })
  .strict();
export type LLMPlan = z.infer<typeof LLMPlanSchema>;

export const InterpretRequestSchema = z
  .object({
    instruction: z.string().min(1),
    state: EditorStateSchema,
  })
  .strict();
export type InterpretRequest = z.infer<typeof InterpretRequestSchema>;

export const InterpretResponseSchema = z
  .object({
    assistantMessage: z.string(),
    actions: z.array(EditorActionSchema),
  })
  .strict();
export type InterpretResponse = z.infer<typeof InterpretResponseSchema>;
