/** Pure mappings for the lab. This file does not score designs. */

export const DISPLAY_STOCK_MM = 8;
export const DISPLAY_PAD_THICKNESS_MM = 4;
export const SCALE_REFERENCE_MM = 10;
export const METHODS = ["random", "evolutionary", "adversarial"] as const;

export type MethodName = (typeof METHODS)[number];
export type Workspace = "gripper" | "swarm" | "failure" | "energy";
export type CameraView = "front" | "side" | "top" | "isometric";

export const WORKSPACES: { id: Workspace; label: string; key: string }[] = [
  { id: "gripper", label: "Gripper Digital Twin", key: "1" },
  { id: "swarm", label: "Swarm Evolution", key: "2" },
  { id: "failure", label: "Failure Analysis", key: "3" },
  { id: "energy", label: "Energy System", key: "4" },
];

export const METHOD_STYLE: Record<string, { color: string; shape: string; letter: string }> = {
  random: { color: "#d2c4a8", shape: "sphere", letter: "R" },
  evolutionary: { color: "#3ec6c0", shape: "box", letter: "E" },
  adversarial: { color: "#c49bff", shape: "diamond", letter: "A" },
};

export type ScoredDesign = {
  id: string;
  method: string;
  generation: number;
  parent_ids?: string[];
  origin?: string;
  parameters: Record<string, number>;
  score: {
    success_rate: number;
    mean_margin_n?: number;
    worst_margin_n: number;
    material_proxy: number;
    mean_deflection_mm?: number;
    fitness: number;
    scenario_count?: number;
    score_basis?: string;
  };
  is_finalist?: boolean;
  preregistered?: boolean;
};

export type StoredFailure = {
  id: string;
  design_id: string;
  method?: string;
  margin_n: number;
  feasible: boolean;
  explanation: string;
  reasons: string[];
  scenario: Record<string, number | string>;
  parameters?: Record<string, number>;
};

export type GripperLayout = {
  jawOpeningMm: number;
  fingerLengthMm: number;
  padWidthMm: number;
  padDrawnMm: number;
  padExceedsFinger: boolean;
  displayStockMm: number;
  displayPadThicknessMm: number;
  leftPadInnerXmm: number;
  rightPadInnerXmm: number;
  fingerRootYmm: number;
  fingerTipYmm: number;
  padCenterYmm: number;
  padSpanMm: number;
  actuatorForceN: number | null;
  stiffnessNPerMm: number | null;
};

export const PART_NOTES: Record<string, string> = {
  frame: "Display frame spanning the jaw. It is not an independent simulated part.",
  "left-finger": "Length is finger_length_mm. The 8 mm thickness is display stock, not a surrogate input.",
  "right-finger": "Length is finger_length_mm. The 8 mm thickness is display stock, not a surrogate input.",
  "left-pad": "Contact length along the finger is pad_width_mm. Pad thickness is display-only.",
  "right-pad": "Contact length along the finger is pad_width_mm. Pad thickness is display-only.",
  "left-joint": "Display hinge only. gripper-2d-1.0.0 has no joint angle or actuator dynamics.",
  "right-joint": "Display hinge only. gripper-2d-1.0.0 has no joint angle or actuator dynamics.",
  object: "Only object width is a scenario input. Height and depth are display extrusions.",
};

const GRIPPER_EXPLAIN =
  /^Friction capacity (-?\d+(?:\.\d+)?) N versus required (-?\d+(?:\.\d+)?) N for a (-?\d+(?:\.\d+)?) kg object (-?\d+(?:\.\d+)?) mm wide, friction (-?\d+(?:\.\d+)?), disturbance (-?\d+(?:\.\d+)?) N, safety factor (-?\d+(?:\.\d+)?)\.[\s\S]*Deflection (-?\d+(?:\.\d+)?) mm scales contact by (-?\d+(?:\.\d+)?) and engagement is (-?\d+(?:\.\d+)?)\./;

export type ParsedExplanation = {
  frictionCapacityN: number;
  requiredForceN: number;
  massKg: number;
  objectWidthMm: number;
  friction: number;
  disturbanceN: number;
  safetyFactor: number;
  deflectionMm: number;
  deflectionScale: number;
  engagement: number;
  source: "archived-explanation";
};

export function gripperLayout(parameters: Record<string, number> | null | undefined): GripperLayout | null {
  if (!parameters) return null;
  const jaw = parameters.jaw_opening_mm;
  const finger = parameters.finger_length_mm;
  const pad = parameters.pad_width_mm;
  if (![jaw, finger, pad].every((value) => typeof value === "number" && Number.isFinite(value) && value > 0)) return null;
  const padDrawn = Math.min(pad, finger);
  return {
    jawOpeningMm: jaw,
    fingerLengthMm: finger,
    padWidthMm: pad,
    padDrawnMm: padDrawn,
    padExceedsFinger: pad > finger + 1e-9,
    displayStockMm: DISPLAY_STOCK_MM,
    displayPadThicknessMm: DISPLAY_PAD_THICKNESS_MM,
    leftPadInnerXmm: -jaw / 2,
    rightPadInnerXmm: jaw / 2,
    fingerRootYmm: 0,
    fingerTipYmm: -finger,
    padCenterYmm: padCenterY(finger, padDrawn),
    padSpanMm: padDrawn,
    actuatorForceN: finite(parameters.actuator_force_n),
    stiffnessNPerMm: finite(parameters.stiffness_n_per_mm),
  };
}

export function illustrativeGapMm(jawMm: number, motion: number, enabled: boolean) {
  if (!enabled) return jawMm;
  const clamped = Math.min(1, Math.max(0, motion));
  return jawMm * (0.72 + clamped * 0.56);
}

export function objectBox(widthMm: number) {
  const width = Number.isFinite(widthMm) && widthMm > 0 ? widthMm : 40;
  return {
    widthMm: width,
    heightMm: Math.min(width * 0.65, 50),
    depthMm: Math.min(width * 0.7, 40),
    heightIsDisplayOnly: true,
    depthIsDisplayOnly: true,
  };
}

export function fitNote(jawMm: number, widthMm: number) {
  if (widthMm > jawMm + 1e-9) return "Object width exceeds the jaw opening. The surrogate treats that as a geometry failure.";
  return "Object width fits the jaw opening. That alone does not make the grasp feasible.";
}

function padCenterY(finger: number, pad: number) {
  if (pad >= finger) return -finger / 2;
  const preferred = -finger * 0.62;
  const minCenter = -finger + pad / 2;
  const maxCenter = -pad / 2;
  return Math.min(maxCenter, Math.max(minCenter, preferred));
}

function finite(value: number | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function parseGripperExplanation(text: string | undefined | null): ParsedExplanation | null {
  if (!text) return null;
  const match = GRIPPER_EXPLAIN.exec(text);
  if (!match) return null;
  const nums = match.slice(1).map(Number);
  if (nums.some((value) => !Number.isFinite(value))) return null;
  return {
    frictionCapacityN: nums[0],
    requiredForceN: nums[1],
    massKg: nums[2],
    objectWidthMm: nums[3],
    friction: nums[4],
    disturbanceN: nums[5],
    safetyFactor: nums[6],
    deflectionMm: nums[7],
    deflectionScale: nums[8],
    engagement: nums[9],
    source: "archived-explanation",
  };
}

export function reasonTone(reason: string): "warn" | "fail" {
  const text = reason.toLowerCase();
  if (text.includes("narrow pad") || text.includes("penalty band")) return "warn";
  return "fail";
}

export function marginTone(margin: number, feasible: boolean): "pass" | "fail" {
  if (feasible && margin >= -1e-9) return "pass";
  return "fail";
}

export type Span = { min: number; max: number };

export function swarmAxes(domain: string, parameters: Record<string, number> | undefined) {
  if (domain === "energy" || (parameters && "solar_kw" in parameters)) {
    return { xKey: "solar_kw", zKey: "storage_kwh", xLabel: "Solar rating (kW)", zLabel: "Storage rating (kWh)" };
  }
  return { xKey: "actuator_force_n", zKey: "stiffness_n_per_mm", xLabel: "Actuator force (N)", zLabel: "Stiffness (N/mm)" };
}

export function axisSpans(designs: ScoredDesign[], xKey: string, zKey: string) {
  const usable = designs.filter((design) => coordinateFinite(design, xKey, zKey));
  return {
    x: span(usable.map((design) => design.parameters[xKey])),
    y: span(usable.map((design) => design.score.fitness)),
    z: span(usable.map((design) => design.parameters[zKey])),
    omitted: designs.length - usable.length,
  };
}

export function swarmPoint(
  design: ScoredDesign,
  xKey: string,
  zKey: string,
  spans: { x: Span; y: Span; z: Span },
): { id: string; x: number; y: number; z: number } | null {
  if (!coordinateFinite(design, xKey, zKey)) return null;
  return {
    id: design.id,
    x: unit(design.parameters[xKey], spans.x),
    y: unit(design.score.fitness, spans.y),
    z: unit(design.parameters[zKey], spans.z),
  };
}

function coordinateFinite(design: ScoredDesign, xKey: string, zKey: string) {
  return [design.parameters?.[xKey], design.score?.fitness, design.parameters?.[zKey]].every((value) => typeof value === "number" && Number.isFinite(value));
}

function span(values: number[]): Span {
  if (!values.length) return { min: 0, max: 1 };
  const min = Math.min(...values);
  const max = Math.max(...values);
  return { min, max: max === min ? min + 1 : max };
}

function unit(value: number, range: Span) {
  return ((value - range.min) / (range.max - range.min)) * 4 - 2;
}

export function stepGeneration(current: number, max: number, direction: number) {
  if (!Number.isFinite(max) || max < 0) return 0;
  const next = current + direction;
  return Math.min(max, Math.max(0, next));
}

export function visibleDesigns<T extends { generation: number; method: string; preregistered?: boolean; is_finalist?: boolean; id: string }>(
  designs: T[],
  generation: number,
  methods: Record<string, boolean>,
  finalistsOnly: boolean,
) {
  return designs.filter((design) => {
    if (design.generation > generation) return false;
    if (methods[design.method] === false) return false;
    if (finalistsOnly && !design.preregistered && !design.is_finalist) return false;
    return true;
  });
}

export function rankTuple(design: ScoredDesign): [number, number, number, number] {
  return [design.score.success_rate, design.score.worst_margin_n, -design.score.material_proxy, design.score.fitness];
}

export function betterDesign(a: ScoredDesign, b: ScoredDesign) {
  const left = rankTuple(a);
  const right = rankTuple(b);
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) return left[index] > right[index] ? a : b;
  }
  return a;
}

export function bestOf(designs: ScoredDesign[], method: string) {
  const rows = designs.filter((design) => design.method === method && Number.isFinite(design.score?.fitness));
  if (!rows.length) return null;
  return rows.reduce((lead, design) => betterDesign(lead, design));
}

export function preregisteredDesign(designs: ScoredDesign[], method = "adversarial") {
  return designs.find((design) => design.method === method && design.preregistered) ?? bestOf(designs, method);
}

export function comparisonPair(designs: ScoredDesign[]) {
  return {
    baseline: bestOf(designs, "random"),
    adversarial: preregisteredDesign(designs, "adversarial"),
  };
}

export function lineageChain(designs: ScoredDesign[], id: string | null) {
  const byId = new Map(designs.map((design) => [design.id, design]));
  const chain: string[] = [];
  const seen = new Set<string>();
  let cursor = id;
  while (cursor && byId.has(cursor) && !seen.has(cursor)) {
    seen.add(cursor);
    chain.push(cursor);
    cursor = byId.get(cursor)?.parent_ids?.[0] ?? null;
  }
  return chain.reverse();
}

export function referenceObjectWidth(
  scenarios: Array<Record<string, number | string>> | undefined,
  failure: StoredFailure | null,
): { mm: number; source: string } {
  const fromFailure = failure?.scenario?.object_width_mm;
  if (typeof fromFailure === "number" && Number.isFinite(fromFailure)) {
    return { mm: fromFailure, source: `archived failure ${failure?.id}` };
  }
  const train = scenarios?.find((scenario) => typeof scenario.object_width_mm === "number");
  if (train && typeof train.object_width_mm === "number") {
    return { mm: train.object_width_mm, source: `train scenario ${String(train.id ?? "")}`.trim() };
  }
  return { mm: 40, source: "display fallback 40 mm because no scenario width is stored" };
}

export function energyBlocks(parameters: Record<string, number> | null | undefined) {
  if (!parameters) return [];
  const rows = [
    ["solar", "Solar rating", parameters.solar_kw, "kW", 8],
    ["storage", "Storage rating", parameters.storage_kwh, "kWh", 20],
    ["discharge", "Discharge rating", parameters.discharge_kw, "kW", 5],
  ] as const;
  return rows
    .filter((row) => typeof row[2] === "number" && Number.isFinite(row[2]))
    .map(([id, label, value, unit, absolute]) => ({
      id,
      label,
      value,
      unit,
      fraction: Math.min(1, Math.max(0, value / absolute)),
      hourly: null,
    }));
}

export function runPresentation(status: string, source: "recorded" | "saved" | "idle") {
  if (source === "recorded") {
    return { mode: "replay" as const, title: "Recorded offline replay", live: false as const };
  }
  if (["PENDING", "PLANNING", "SIMULATING", "EVOLVING", "VALIDATING"].includes(status)) {
    return { mode: "batch" as const, title: "Batch run in progress", live: false as const };
  }
  if (status === "COMPLETE" && source === "saved") {
    return { mode: "replay" as const, title: "Saved run replay", live: false as const };
  }
  return { mode: "idle" as const, title: "No run loaded", live: false as const };
}

export function plannerBadge(provider: string | undefined) {
  if (provider === "meta") return { label: "Meta planner", tone: "meta" as const };
  if (provider === "rule") return { label: "Rule planner", tone: "rule" as const };
  if (provider === "mock") return { label: "Mock planner", tone: "mock" as const };
  return { label: "Planner not recorded", tone: "unknown" as const };
}

export function readBundle(value: unknown): { report: BundleReport; candidates: ScoredDesign[]; failures: StoredFailure[] } {
  if (!value || typeof value !== "object") throw new Error("Run payload is not an object.");
  const bundle = value as { report?: unknown; candidates?: unknown; failures?: unknown };
  const report = bundle.report as BundleReport | undefined;
  if (!report || typeof report !== "object") throw new Error("Run payload has no report.");
  if (typeof report.seed !== "number" || !Number.isFinite(report.seed)) throw new Error("Report seed is missing.");
  if (typeof report.domain !== "string" || !report.domain) throw new Error("Report domain is missing.");
  if (typeof report.simulator_version !== "string") throw new Error("Simulator version is missing.");
  if (!Array.isArray(bundle.candidates)) throw new Error("Candidates are missing.");
  bundle.candidates.forEach((candidate, index) => {
    const row = candidate as ScoredDesign;
    if (!row || typeof row.id !== "string" || typeof row.method !== "string") throw new Error(`Candidate ${index} has no stable id.`);
    if (typeof row.generation !== "number") throw new Error(`Candidate ${row.id} has no generation.`);
    if (!row.parameters || typeof row.parameters !== "object") throw new Error(`Candidate ${row.id} has no parameters.`);
    if (!row.score || typeof row.score.fitness !== "number") throw new Error(`Candidate ${row.id} has no stored fitness.`);
  });
  const failures = Array.isArray(bundle.failures) ? (bundle.failures as StoredFailure[]) : [];
  return { report, candidates: bundle.candidates as ScoredDesign[], failures };
}

export type BundleReport = {
  seed: number;
  domain: string;
  simulator_version: string;
  assumptions_hash?: string;
  run_id?: string;
  status?: string;
  planner?: { provider?: string; hypothesis?: string; rationale?: string; warnings?: string[] } | null;
  train_scenarios?: Array<Record<string, number | string>>;
  limitations?: string[];
  failure_count?: number;
  total_search_calls?: number;
  holdout?: Array<Record<string, unknown>>;
  provenance?: Array<{ id: string; kind: string; summary: string }>;
};

export function webglAvailable() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}
