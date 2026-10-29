import assert from "node:assert/strict";
import test from "node:test";

import {
  axisSpans,
  bestOf,
  comparisonPair,
  energyBlocks,
  fitNote,
  gripperLayout,
  illustrativeGapMm,
  lineageChain,
  parseGripperExplanation,
  PART_NOTES,
  readBundle,
  reasonTone,
  referenceObjectWidth,
  runPresentation,
  stepGeneration,
  swarmPoint,
  visibleDesigns,
} from "./lab-model.ts";

const HERO_EXPLAIN =
  "Friction capacity 0.00 N versus required 25.97 N for a 1.28 kg object 37.2 mm wide, friction 0.28, disturbance 6.40 N, safety factor 1.84. Jaw 44.6 mm, finger 78.6 mm, pad 11.9 mm, stiffness 27.66 N/mm, actuator 62.6 N. Deflection 17.18 mm scales contact by 0.00 and engagement is 1.00. Causes: deflection exceeds hard limit and contact is lost.";

function design(partial: {
  id: string;
  method: string;
  generation?: number;
  fitness: number;
  success?: number;
  margin?: number;
  material?: number;
  force?: number;
  stiffness?: number;
  preregistered?: boolean;
  parents?: string[];
}) {
  return {
    id: partial.id,
    method: partial.method,
    generation: partial.generation ?? 0,
    parent_ids: partial.parents ?? [],
    parameters: { actuator_force_n: partial.force ?? 30, stiffness_n_per_mm: partial.stiffness ?? 10, jaw_opening_mm: 60, finger_length_mm: 50, pad_width_mm: 15 },
    score: {
      success_rate: partial.success ?? 1,
      worst_margin_n: partial.margin ?? 0,
      material_proxy: partial.material ?? 10,
      fitness: partial.fitness,
    },
    preregistered: partial.preregistered ?? false,
  };
}

test("gripper jaw is the distance between pad inner faces", () => {
  const layout = gripperLayout({ jaw_opening_mm: 60, finger_length_mm: 50, pad_width_mm: 15, actuator_force_n: 30, stiffness_n_per_mm: 40 });
  assert.ok(layout);
  assert.equal(layout.rightPadInnerXmm - layout.leftPadInnerXmm, 60);
  assert.equal(layout.fingerTipYmm - layout.fingerRootYmm, -50);
  assert.equal(layout.padSpanMm, 15);
  assert.equal(layout.displayStockMm, 8);
  assert.equal(layout.actuatorForceN, 30);
});

test("illustrative motion does not change the stored jaw", () => {
  const params = { jaw_opening_mm: 60, finger_length_mm: 40, pad_width_mm: 12 };
  const layout = gripperLayout(params);
  assert.equal(illustrativeGapMm(layout!.jawOpeningMm, 1, false), 60);
  assert.notEqual(illustrativeGapMm(60, 1, true), 60);
  assert.equal(params.jaw_opening_mm, 60);
});

test("pad wider than the finger is flagged and not drawn longer than the finger", () => {
  const layout = gripperLayout({ jaw_opening_mm: 40, finger_length_mm: 20, pad_width_mm: 28 });
  assert.equal(layout?.padExceedsFinger, true);
  assert.equal(layout?.padDrawnMm, 20);
  assert.equal(layout?.padWidthMm, 28);
});

test("joints are labeled as display-only", () => {
  assert.match(PART_NOTES["left-joint"], /no joint angle/i);
  assert.match(PART_NOTES.object, /display/i);
});

test("archived explanation parser reads simulator text and rejects other prose", () => {
  const parsed = parseGripperExplanation(HERO_EXPLAIN);
  assert.equal(parsed?.frictionCapacityN, 0);
  assert.equal(parsed?.requiredForceN, 25.97);
  assert.equal(parsed?.deflectionMm, 17.18);
  assert.equal(parsed?.source, "archived-explanation");
  assert.equal(parseGripperExplanation("the grasp looks fine"), null);
});

test("warning reasons stay distinct from hard failures", () => {
  assert.equal(reasonTone("narrow pad reduces contact engagement"), "warn");
  assert.equal(reasonTone("deflection in the penalty band reduces normal contact"), "warn");
  assert.equal(reasonTone("object wider than jaw opening"), "fail");
});

test("fitness is the only vertical swarm coordinate and missing fitness is omitted", () => {
  const rows = [design({ id: "a", method: "random", fitness: 10, force: 20 }), design({ id: "b", method: "random", fitness: 40, force: 80 })];
  const spans = axisSpans(rows, "actuator_force_n", "stiffness_n_per_mm");
  const low = swarmPoint(rows[0], "actuator_force_n", "stiffness_n_per_mm", spans);
  const high = swarmPoint(rows[1], "actuator_force_n", "stiffness_n_per_mm", spans);
  assert.ok(low && high);
  assert.ok(high.y > low.y);
  assert.equal(high.x > low.x, true);
  const broken = design({ id: "c", method: "random", fitness: Number.NaN });
  const withGap = axisSpans([rows[0], broken], "actuator_force_n", "stiffness_n_per_mm");
  assert.equal(withGap.omitted, 1);
  assert.equal(swarmPoint(broken, "actuator_force_n", "stiffness_n_per_mm", withGap), null);
});

test("a thousand points keep stable ids", () => {
  const rows = Array.from({ length: 1000 }, (_, index) => design({ id: `d-${index}`, method: index % 3 === 0 ? "random" : "evolutionary", fitness: index, force: index, generation: index % 5 }));
  const spans = axisSpans(rows, "actuator_force_n", "stiffness_n_per_mm");
  const points = rows.map((row) => swarmPoint(row, "actuator_force_n", "stiffness_n_per_mm", spans));
  assert.equal(points.length, 1000);
  assert.equal(points[999]?.id, "d-999");
  assert.equal(visibleDesigns(rows, 1, { random: true, evolutionary: true, adversarial: true }, false).every((row) => row.generation <= 1), true);
});

test("ranking prefers feasibility over a higher fitness", () => {
  const weak = design({ id: "weak", method: "random", fitness: 90, success: 0.2, margin: -5 });
  const strong = design({ id: "strong", method: "random", fitness: 40, success: 1, margin: 1 });
  assert.equal(bestOf([weak, strong], "random")?.id, "strong");
});

test("comparison pair uses the random baseline and the preregistered adversarial design", () => {
  const pair = comparisonPair([
    design({ id: "r", method: "random", fitness: 10, success: 1 }),
    design({ id: "a-best", method: "adversarial", fitness: 80, success: 1 }),
    design({ id: "a-reg", method: "adversarial", fitness: 30, success: 1, preregistered: true }),
  ]);
  assert.equal(pair.baseline?.id, "r");
  assert.equal(pair.adversarial?.id, "a-reg");
});

test("lineage walks parent ids without looping", () => {
  const rows = [
    design({ id: "root", method: "adversarial", fitness: 1 }),
    design({ id: "child", method: "adversarial", fitness: 2, parents: ["root"] }),
    design({ id: "loop", method: "adversarial", fitness: 3, parents: ["loop"] }),
  ];
  assert.deepEqual(lineageChain(rows, "child"), ["root", "child"]);
  assert.deepEqual(lineageChain(rows, "loop"), ["loop"]);
});

test("object width prefers an archived failure, then a train scenario, then a labeled fallback", () => {
  const failure = { id: "f1", design_id: "a", margin_n: -1, feasible: false, explanation: "", reasons: [], scenario: { object_width_mm: 37.2 } };
  assert.equal(referenceObjectWidth([{ id: "t", object_width_mm: 40 }], failure).source.includes("f1"), true);
  assert.equal(referenceObjectWidth([{ id: "t", object_width_mm: 40 }], null).mm, 40);
  assert.match(referenceObjectWidth([], null).source, /fallback/);
});

test("fit note uses only the two stored lengths", () => {
  assert.match(fitNote(40, 50), /exceeds/);
  assert.match(fitNote(60, 40), /fits/);
});

test("energy blocks are ratings and do not invent an hourly trace", () => {
  const blocks = energyBlocks({ solar_kw: 4, storage_kwh: 10, discharge_kw: 1 });
  assert.equal(blocks.length, 3);
  assert.equal(blocks.every((block) => block.hourly === null), true);
  assert.equal(energyBlocks({ jaw_opening_mm: 60 }).length, 0);
});

test("playback and progress never claim a live swarm", () => {
  assert.equal(stepGeneration(0, 3, -1), 0);
  assert.equal(stepGeneration(3, 3, 1), 3);
  assert.equal(runPresentation("EVOLVING", "saved").live, false);
  assert.equal(runPresentation("EVOLVING", "saved").mode, "batch");
  assert.equal(runPresentation("COMPLETE", "recorded").title.includes("Recorded"), true);
  assert.equal(runPresentation("COMPLETE", "saved").live, false);
});

test("bundle reader rejects a payload without seed or fitness", () => {
  assert.throws(() => readBundle({ report: { domain: "gripper_2d", simulator_version: "gripper-2d-1.0.0" }, candidates: [] }), /seed/);
  const ok = readBundle({
    report: { seed: 42, domain: "gripper_2d", simulator_version: "gripper-2d-1.0.0" },
    candidates: [design({ id: "a", method: "random", fitness: 1 })],
    failures: [],
  });
  assert.equal(ok.candidates[0].id, "a");
});
