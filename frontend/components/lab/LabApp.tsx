"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import { API_BASE, cancelRun, createRun, downloadBundle, getCandidates, getFailures, getHealth, getRun, loadHero } from "@/lib/api";
import {
  METHOD_STYLE,
  METHODS,
  PART_NOTES,
  WORKSPACES,
  bestOf,
  betterDesign,
  comparisonPair,
  energyBlocks,
  fitNote,
  gripperLayout,
  marginTone,
  parseGripperExplanation,
  plannerBadge,
  preregisteredDesign,
  readBundle,
  reasonTone,
  referenceObjectWidth,
  runPresentation,
  stepGeneration,
  visibleDesigns,
  webglAvailable,
  type CameraView,
  type ScoredDesign,
  type Workspace,
} from "@/lib/lab-model";
import type { Bundle, FailureCase, Progress } from "@/lib/types";

const Viewport = dynamic(() => import("@/components/lab/Viewport").then((mod) => mod.Viewport), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center text-sm text-lab-muted">Opening viewport…</div>,
});

const GRIPPER_BOUNDS: Record<string, [number, number]> = {
  jaw_opening_mm: [25, 90],
  finger_length_mm: [20, 80],
  pad_width_mm: [5, 30],
  stiffness_n_per_mm: [1, 40],
  actuator_force_n: [5, 80],
};
const ENERGY_BOUNDS: Record<string, [number, number]> = {
  solar_kw: [0.5, 8],
  storage_kwh: [0.5, 20],
  discharge_kw: [0.2, 5],
};
const PRESETS = {
  quick: { calls: 180, train: 4, holdout: 6 },
  standard: { calls: 1200, train: 8, holdout: 24 },
  deeper: { calls: 2400, train: 16, holdout: 40 },
};
const RUNNING = ["PENDING", "PLANNING", "SIMULATING", "EVOLVING", "VALIDATING"];
const VIEW_MODE: { id: Workspace; label: string }[] = [
  { id: "gripper", label: "Digital Twin" },
  { id: "swarm", label: "Swarm" },
  { id: "failure", label: "Failures" },
  { id: "energy", label: "Energy" },
];

export function LabApp() {
  const [domain, setDomain] = useState<"gripper_2d" | "energy">("gripper_2d");
  const [preset, setPreset] = useState<keyof typeof PRESETS>("standard");
  const [seed, setSeed] = useState(42);
  const [provider, setProvider] = useState("mock");
  const [bounds, setBounds] = useState(GRIPPER_BOUNDS);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [status, setStatus] = useState("Idle");
  const [error, setError] = useState("");
  const [api, setApi] = useState("checking");
  const [source, setSource] = useState<"recorded" | "saved" | "idle">("idle");
  const [runId, setRunId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<Workspace>("gripper");
  const [cameraView, setCameraView] = useState<CameraView>("isometric");
  const [cameraNonce, setCameraNonce] = useState(0);
  const [showGrid, setShowGrid] = useState(true);
  const [showDimensions, setShowDimensions] = useState(true);
  const [showScale, setShowScale] = useState(true);
  const [showGeometry, setShowGeometry] = useState(true);
  const [showForces, setShowForces] = useState(true);
  const [illustrative, setIllustrative] = useState(false);
  const [selectedPart, setSelectedPart] = useState<string | null>("frame");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string | null>(null);
  const [failureId, setFailureId] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [methodsOn, setMethodsOn] = useState<Record<string, boolean>>({ random: true, evolutionary: true, adversarial: true });
  const [finalistsOnly, setFinalistsOnly] = useState(false);
  const [showLineage, setShowLineage] = useState(true);
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null);
  const [leftW, setLeftW] = useState(300);
  const [rightW, setRightW] = useState(340);
  const [webgl, setWebgl] = useState(true);
  const [help, setHelp] = useState(false);

  useEffect(() => {
    getHealth().then(() => setApi("connected")).catch(() => setApi("offline"));
    setWebgl(webglAvailable());
  }, []);

  useEffect(() => {
    setBounds(domain === "gripper_2d" ? { ...GRIPPER_BOUNDS } : { ...ENERGY_BOUNDS });
  }, [domain]);

  const designs = useMemo(() => (bundle?.candidates ?? []) as ScoredDesign[], [bundle]);
  const failures = bundle?.failures ?? [];
  const maxGen = designs.reduce((max, design) => Math.max(max, design.generation), 0);
  const selected = designs.find((design) => design.id === selectedId) ?? null;
  const compare = designs.find((design) => design.id === compareId) ?? null;
  const failure = failures.find((item) => item.id === failureId) ?? failures.find((item) => item.design_id === selected?.id) ?? null;
  const widthFailure = failure && selected && failure.design_id === selected.id ? failure : null;
  const pair = useMemo(() => comparisonPair(designs), [designs]);
  const width = referenceObjectWidth(bundle?.report.train_scenarios, widthFailure);
  const presentation = runPresentation(status, source);
  const badge = plannerBadge(bundle?.report.planner?.provider);
  const layout = gripperLayout(selected?.parameters ?? null);
  const parsed = widthFailure ? parseGripperExplanation(widthFailure.explanation) : null;
  const shownCount = visibleDesigns(designs, generation, methodsOn, finalistsOnly).length;
  const methodCounts = METHODS.map((method) => ({ method, count: designs.filter((design) => design.method === method).length }));
  const marginN = selected?.score.worst_margin_n ?? null;

  useEffect(() => {
    if (!playing) return undefined;
    const timer = window.setInterval(() => {
      setGeneration((current) => stepGeneration(current, maxGen, 1));
    }, Math.round(800 / speed));
    return () => window.clearInterval(timer);
  }, [maxGen, playing, speed]);

  useEffect(() => {
    if (playing && generation >= maxGen) setPlaying(false);
  }, [generation, maxGen, playing]);

  useEffect(() => {
    if (!playing) return;
    const visible = designs.filter((design) => design.generation <= generation && design.method === "adversarial");
    if (!visible.length) return;
    const lead = visible.reduce((best, design) => betterDesign(best, design));
    setSelectedId(lead.id);
  }, [designs, generation, playing]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, select, textarea")) return;
      const workspaceHit = WORKSPACES.find((item) => item.key === event.key);
      if (workspaceHit) setWorkspace(workspaceHit.id);
      if (event.key === "f") setCameraView("front");
      if (event.key === "s") setCameraView("side");
      if (event.key === "t") setCameraView("top");
      if (event.key === "i") setCameraView("isometric");
      if (event.key === "r") setCameraNonce((value) => value + 1);
      if (event.key === "?" ) setHelp((value) => !value);
      if (event.key === "ArrowRight") setGeneration((current) => stepGeneration(current, maxGen, 1));
      if (event.key === "ArrowLeft") setGeneration((current) => stepGeneration(current, maxGen, -1));
      if (event.key === " " && !target?.closest("button")) {
        event.preventDefault();
        setPlaying((value) => !value);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [maxGen]);

  function adopt(next: Bundle, nextSource: "recorded" | "saved", nextStatus: string) {
    readBundle(next);
    const rows = next.candidates as ScoredDesign[];
    const chosen = comparisonPair(rows);
    setBundle(next);
    setSource(nextSource);
    setStatus(nextStatus);
    setSelectedId(chosen.adversarial?.id ?? rows[0]?.id ?? null);
    setCompareId(chosen.baseline?.id ?? null);
    setFailureId(next.failures[0]?.id ?? null);
    setGeneration(0);
    setPlaying(rows.some((row) => row.generation > 0));
    setSelectedPart("frame");
  }

  async function replayHero() {
    setError("");
    setStatus("Loading recorded run");
    try {
      adopt(await loadHero(), "recorded", "COMPLETE");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The recorded run could not be read.");
    }
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    for (const [key, pairBounds] of Object.entries(bounds)) {
      if (!(pairBounds[0] < pairBounds[1])) {
        setError(`${key} needs a low value below the high value.`);
        return;
      }
    }
    const chosen = PRESETS[preset];
    setStatus("PENDING");
    setBundle(null);
    setSource("saved");
    setPlaying(false);
    try {
      const created = await createRun({
        domain,
        seed,
        model_provider: provider,
        blocking: false,
        budget: { total_simulator_calls: chosen.calls, adversarial_fraction: 0.2, playback_ms: 250 },
        scenarios: { train_count: chosen.train, holdout_count: chosen.holdout },
        design_bounds: bounds,
        objectives: domain === "gripper_2d" ? ["grip_success", "material_proxy"] : ["service", "cost_proxy"],
      });
      setRunId(created.id);
      let view = await getRun(created.id);
      setProgress(view.progress);
      setStatus(view.status);
      while (!["COMPLETE", "FAILED", "CANCELLED"].includes(view.status)) {
        await new Promise((resolve) => setTimeout(resolve, 700));
        view = await getRun(created.id);
        setProgress(view.progress);
        setStatus(view.status);
      }
      if (view.status !== "COMPLETE" || !view.report) throw new Error(view.error || "The run did not finish.");
      const [candidates, archived] = await Promise.all([getCandidates(created.id), getFailures(created.id)]);
      adopt({ report: view.report, candidates, failures: archived }, "saved", "COMPLETE");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Run failed");
      setStatus("FAILED");
    }
  }

  const parameters = workspace === "failure" ? (failure?.parameters ?? selected?.parameters ?? null) : (selected?.parameters ?? null);

  return (
    <div className="flex h-screen flex-col bg-lab-bg text-lab-text">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-lab-line px-3">
        <div className="min-w-0">
          <p className="font-serif text-lg leading-none">SWARM EVOLVE-X</p>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-lab-cyan">Engineering lab</p>
        </div>
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2 font-mono text-[10px] text-lab-muted">
          <span className={`rounded-full px-2 py-0.5 ${badge.tone === "mock" ? "bg-lab-amber/20 text-lab-amber" : badge.tone === "meta" ? "bg-lab-violet/20 text-lab-violet" : "bg-lab-panel2 text-lab-cyan"}`}>{badge.label}</span>
          <span>{presentation.title}</span>
          <span>API {api}</span>
          <span>{status}</span>
          <span>seed {bundle?.report.seed ?? seed}</span>
          <span>{bundle?.report.simulator_version ?? "—"}</span>
          <span>{bundle?.report.assumptions_hash ?? ""}</span>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="max-h-[42vh] w-full overflow-y-auto border-b border-lab-line p-3 lg:max-h-none lg:w-[var(--dock)] lg:shrink-0 lg:border-b-0 lg:border-r" style={{ ["--dock" as string]: `${leftW}px` }}>
          <section className="mb-4">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-lab-muted">Designs</p>
            <p className="font-serif text-5xl leading-none">{designs.length}</p>
            <p className="mt-1 font-mono text-[11px] text-lab-muted">{methodCounts.filter((row) => row.count > 0).length} methods</p>
            <ul className="mt-2 space-y-1">
              {methodCounts.map((row) => (
                <li key={row.method} className="flex items-center justify-between font-mono text-[11px]">
                  <span className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full" style={{ background: METHOD_STYLE[row.method].color }} />
                    {row.method}
                  </span>
                  <span>{row.count}</span>
                </li>
              ))}
            </ul>
          </section>
          <section className="mb-4">
            <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-lab-muted">View mode</p>
            <div className="grid gap-1">
              {VIEW_MODE.map((item) => (
                <button key={item.id} type="button" onClick={() => setWorkspace(item.id)} className={`rounded-md px-2 py-1.5 text-left text-sm ${workspace === item.id ? "bg-lab-cyan text-lab-bg" : "bg-lab-panel2 text-lab-text"}`}>
                  {item.label}
                </button>
              ))}
            </div>
          </section>
          <section className="mb-4">
            <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-lab-muted">Visual layers</p>
            <div className="flex flex-wrap gap-1">
              <button type="button" className={chip(showGeometry)} onClick={() => setShowGeometry((value) => !value)}>Geometry</button>
              <button type="button" className={chip(showForces)} onClick={() => setShowForces((value) => !value)}>Force vectors</button>
              <button type="button" className={chip(showDimensions)} onClick={() => setShowDimensions((value) => !value)}>Dimensions</button>
              <button type="button" className={chip(showGrid)} onClick={() => setShowGrid((value) => !value)}>Grid</button>
              <button type="button" className={chip(showScale)} onClick={() => setShowScale((value) => !value)}>10 mm</button>
              <button type="button" className={chip(illustrative)} onClick={() => setIllustrative((value) => !value)}>Illustrative jaw</button>
            </div>
            <p className="mt-2 text-[11px] leading-4 text-lab-muted">A red object means the stored worst margin is negative. That tint is not a stress map.</p>
          </section>
          <button className="mb-3 w-full rounded-md border border-lab-cyan/50 px-3 py-1.5 text-sm text-lab-cyan" type="button" onClick={replayHero}>Replay recorded gripper run</button>
          <details className="mb-3">
            <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.16em] text-lab-muted">Experiment</summary>
          <form onSubmit={onSubmit} className="mt-2 space-y-2 text-sm">
            <Field label="Domain">
              <select className={inputClass} value={domain} onChange={(event) => setDomain(event.target.value as "gripper_2d" | "energy")}>
                <option value="gripper_2d">2D opposing-jaw gripper</option>
                <option value="energy">Toy daily energy balance</option>
              </select>
            </Field>
            <Field label="Budget preset">
              <select className={inputClass} value={preset} onChange={(event) => setPreset(event.target.value as keyof typeof PRESETS)}>
                <option value="quick">Quick look · 180 calls</option>
                <option value="standard">Standard · 1,200 calls</option>
                <option value="deeper">Deeper · 2,400 calls</option>
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Seed">
                <input className={inputClass} type="number" min={0} value={seed} onChange={(event) => setSeed(Number(event.target.value))} />
              </Field>
              <Field label="Planner">
                <select className={inputClass} value={provider} onChange={(event) => setProvider(event.target.value)}>
                  <option value="mock">Mock</option>
                  <option value="rule">Rule</option>
                  <option value="meta">Meta, if enabled</option>
                </select>
              </Field>
            </div>
            <fieldset>
              <legend className="mb-1 text-xs text-lab-muted">Parameter bounds</legend>
              <div className="space-y-1">
                {Object.entries(bounds).map(([key, pairBounds]) => (
                  <div key={key} className="grid grid-cols-[1fr_64px_64px] items-center gap-1">
                    <span className="truncate font-mono text-[10px] text-lab-muted">{key}</span>
                    <input className={inputClass} type="number" step="any" value={pairBounds[0]} aria-label={`${key} low`} onChange={(event) => setBounds({ ...bounds, [key]: [Number(event.target.value), pairBounds[1]] })} />
                    <input className={inputClass} type="number" step="any" value={pairBounds[1]} aria-label={`${key} high`} onChange={(event) => setBounds({ ...bounds, [key]: [pairBounds[0], Number(event.target.value)] })} />
                  </div>
                ))}
              </div>
            </fieldset>
            <button className="w-full rounded-md bg-lab-cyan px-3 py-1.5 text-sm text-lab-bg" type="submit">Run experiment</button>
            {runId && RUNNING.includes(status) ? (
              <button className="w-full rounded-md border border-lab-amber px-3 py-1.5 text-sm text-lab-amber" type="button" onClick={() => cancelRun(runId).catch((exc) => setError(exc.message))}>Cancel run</button>
            ) : null}
            {error ? <p className="text-sm text-lab-fail">{error}</p> : null}
            <p className="font-mono text-[10px] leading-4 text-lab-muted">{API_BASE}. Meta keys stay on the server.</p>
          </form>
          </details>
        </aside>
        <div className="hidden w-1.5 cursor-col-resize bg-lab-line/40 lg:block" role="separator" aria-orientation="vertical" aria-label="Resize navigation" onPointerDown={(event) => dragWidth(event, leftW, setLeftW, 1)} />

        <main className="relative min-h-[420px] min-w-0 flex-1">
          <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-1">
            {(["isometric", "front", "side", "top"] as CameraView[]).map((view) => (
              <button key={view} type="button" className={chip(cameraView === view)} onClick={() => { setCameraView(view); setCameraNonce((value) => value + 1); }}>{view}</button>
            ))}
            <button type="button" className={chip(false)} onClick={() => setCameraNonce((value) => value + 1)}>Reset</button>
            <button type="button" className={chip(false)} onClick={() => setHelp(true)}>Keys</button>
          </div>
          {illustrative && workspace === "gripper" ? (
            <p className="absolute bottom-3 left-3 z-10 max-w-sm rounded-md bg-lab-amber/15 px-2 py-1 text-xs text-lab-amber">Illustrative opening only. The surrogate scores a fixed jaw. This motion is not validated kinematics.</p>
          ) : null}
          {!bundle && RUNNING.includes(status) ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
              <p className="font-mono text-xs uppercase tracking-wider text-lab-amber">Batch progress, not a live swarm</p>
              <p className="text-sm text-lab-muted">{progress?.phase}: {progress?.message}</p>
              <p className="font-mono text-sm">{progress?.simulator_calls ?? 0} / {progress?.budget ?? "—"} simulator calls</p>
              <p className="max-w-md text-xs text-lab-muted">Candidates are written when the run is stored. Nothing is being streamed into the viewport.</p>
            </div>
          ) : (
            <Viewport
              webgl={webgl}
              workspace={workspace}
              domain={bundle?.report.domain ?? domain}
              parameters={parameters}
              objectWidthMm={width.mm}
              objectSource={width.source}
              designs={designs}
              generation={generation}
              methods={methodsOn}
              finalistsOnly={finalistsOnly}
              selectedId={selectedId}
              compareId={compareId}
              baseline={pair.baseline}
              focus={selected}
              failure={failure}
              showLineage={showLineage}
              cameraView={cameraView}
              cameraNonce={cameraNonce}
              showGrid={showGrid}
              showDimensions={showDimensions}
              showScale={showScale}
              showGeometry={showGeometry}
              showForces={showForces}
              marginN={marginN}
              illustrative={illustrative}
              selectedPart={selectedPart}
              onSelectPart={setSelectedPart}
              onSelect={(id) => { setPlaying(false); setSelectedId(id); }}
              onHover={(id, x, y) => setHover(id ? { id, x, y } : null)}
            />
          )}
          {hover ? (
            <div className="pointer-events-none fixed z-20 rounded-md bg-lab-panel px-2 py-1 font-mono text-[10px] shadow" style={{ left: hover.x + 12, top: hover.y + 12 }}>
              {hover.id}
            </div>
          ) : null}
        </main>

        <div className="hidden w-1.5 cursor-col-resize bg-lab-line/40 lg:block" role="separator" aria-orientation="vertical" aria-label="Resize inspector" onPointerDown={(event) => dragWidth(event, rightW, setRightW, -1)} />
        <aside className="max-h-[46vh] w-full overflow-y-auto border-t border-lab-line p-3 lg:max-h-none lg:w-[var(--inspect)] lg:shrink-0 lg:border-l lg:border-t-0" style={{ ["--inspect" as string]: `${rightW}px` }}>
          <Inspector
            bundle={bundle}
            selected={selected}
            compare={compare}
            failure={widthFailure}
            failures={failures}
            layoutNote={layout ? fitNote(layout.jawOpeningMm, width.mm) : ""}
            objectSource={width.source}
            part={selectedPart}
            parsed={parsed}
            onPickDesign={(id) => setSelectedId(id)}
            onPickFailure={(id) => { setPlaying(false); setFailureId(id); setWorkspace("failure"); const found = failures.find((item) => item.id === id); if (found) setSelectedId(found.design_id); }}
            onUseBaseline={() => setCompareId(pair.baseline?.id ?? null)}
            methodsOn={methodsOn}
            setMethodsOn={setMethodsOn}
            finalistsOnly={finalistsOnly}
            setFinalistsOnly={setFinalistsOnly}
            showLineage={showLineage}
            setShowLineage={setShowLineage}
            workspace={workspace}
          />
        </aside>
      </div>

      <footer className="shrink-0 border-t border-lab-line px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="rounded-md bg-lab-panel2 px-3 py-1 text-sm" onClick={() => { if (generation >= maxGen) { setGeneration(0); setPlaying(maxGen > 0); } else setPlaying((value) => !value); }}>
            {playing ? "Pause" : generation >= maxGen && maxGen > 0 ? "Replay generations" : "Play"}
          </button>
          <input className="min-w-[120px] flex-1" type="range" min={0} max={Math.max(0, maxGen)} value={Math.min(generation, maxGen)} aria-label="Generation" onChange={(event) => { setPlaying(false); setGeneration(Number(event.target.value)); }} />
          <span className="font-mono text-xs text-lab-muted">Generation {generation}/{maxGen} · {shownCount} shown</span>
          {[0.5, 1, 2, 4].map((value) => (
            <button key={value} type="button" className={chip(speed === value)} onClick={() => setSpeed(value)}>{value}×</button>
          ))}
          <button type="button" className={chip(illustrative)} onClick={() => setIllustrative((value) => !value)}>Illustrative jaw</button>
          {bundle ? <button type="button" className={chip(false)} onClick={() => downloadBundle(bundle)}>Download JSON</button> : null}
        </div>
        <p className="mt-1 font-mono text-[10px] text-lab-muted" aria-live="polite">
          {presentation.mode === "batch"
            ? "Batch progress only. Designs appear after the run is saved."
            : presentation.mode === "replay"
              ? `${presentation.title}. Scrubbing replays stored generations. It is not a live search.`
              : "Load a recorded run or start an experiment."}
          {workspace === "energy" ? " Hourly energy flow is not stored." : ""}
        </p>
      </footer>
      {help ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/50 p-4" onClick={() => setHelp(false)}>
          <div className="max-w-md rounded-lg bg-lab-panel p-4 text-sm" onClick={(event) => event.stopPropagation()}>
            <h2 className="font-serif text-xl">Keyboard</h2>
            <p className="mt-2 font-mono text-xs leading-5 text-lab-muted">1–4 workspaces · F front · S side · T top · I isometric · R reset camera · arrows step generation · space play · ? close</p>
            <button type="button" className="mt-3 rounded-md bg-lab-panel2 px-3 py-1" onClick={() => setHelp(false)}>Close</button>
          </div>
        </div>
      ) : null}
      <span className="sr-only">Navigation width {leftW}. Inspector width {rightW}.</span>
    </div>
  );
}

function dragWidth(event: React.PointerEvent, startWidth: number, setWidth: (value: number) => void, sign: number) {
  event.preventDefault();
  const startX = event.clientX;
  function move(ev: PointerEvent) {
    setWidth(Math.min(480, Math.max(240, startWidth + sign * (ev.clientX - startX))));
  }
  function up() {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
  }
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

const inputClass = "mt-1 w-full rounded-md border border-lab-line bg-lab-panel2 px-2 py-1 text-sm";

function chip(active: boolean) {
  return `rounded-md px-2 py-1 text-[11px] ${active ? "bg-lab-cyan text-lab-bg" : "bg-lab-panel/80 text-lab-muted"}`;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-xs text-lab-muted">
      {label}
      {children}
    </label>
  );
}

function Inspector(props: {
  bundle: Bundle | null;
  selected: ScoredDesign | null;
  compare: ScoredDesign | null;
  failure: FailureCase | null;
  failures: FailureCase[];
  layoutNote: string;
  objectSource: string;
  part: string | null;
  parsed: ReturnType<typeof parseGripperExplanation>;
  onPickDesign: (id: string) => void;
  onPickFailure: (id: string) => void;
  onUseBaseline: () => void;
  methodsOn: Record<string, boolean>;
  setMethodsOn: (value: Record<string, boolean>) => void;
  finalistsOnly: boolean;
  setFinalistsOnly: (value: boolean) => void;
  showLineage: boolean;
  setShowLineage: (value: boolean) => void;
  workspace: Workspace;
}) {
  const { selected, compare, bundle } = props;
  return (
    <div className="space-y-3 text-sm lg:w-[320px]">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-wider text-lab-muted">Inspector</p>
        <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-lab-muted">Safety margin</p>
        <p className={`font-mono text-4xl leading-none ${selected && selected.score.worst_margin_n < 0 ? "text-lab-fail" : "text-lab-ok"}`}>
          {selected ? `${selected.score.worst_margin_n.toFixed(3)} N` : "—"}
        </p>
        <p className="mt-1 text-[11px] leading-4 text-lab-muted">Stored worst-case margin on the train-core score. Not a contact-force solve and not a stress result.</p>
        <h2 className="mt-3 font-serif text-2xl">{selected?.id ?? "No design"}</h2>
        <p className="font-mono text-[11px] text-lab-muted">{selected ? `${selected.method} · generation ${selected.generation} · ${selected.origin}` : "Replay a run to inspect a stored design."}</p>
      </div>
      {props.workspace === "swarm" ? (
        <div className="space-y-1">
          {METHODS.map((method) => (
            <label key={method} className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={props.methodsOn[method] !== false} onChange={(event) => props.setMethodsOn({ ...props.methodsOn, [method]: event.target.checked })} />
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: METHOD_STYLE[method].color }} />
              {method} · {METHOD_STYLE[method].shape} · {METHOD_STYLE[method].letter}
            </label>
          ))}
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={props.finalistsOnly} onChange={(event) => props.setFinalistsOnly(event.target.checked)} /> Finalists only</label>
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={props.showLineage} onChange={(event) => props.setShowLineage(event.target.checked)} /> Lineage of the selection</label>
          <p className="text-[11px] leading-4 text-lab-muted">Y is stored fitness. X and Z are recorded design variables. Points use instancing.</p>
        </div>
      ) : null}
      {props.part && PART_NOTES[props.part] ? <p className="rounded-md bg-lab-panel2 p-2 text-xs leading-5">{PART_NOTES[props.part]}</p> : null}
      {selected ? <ScoreBlock title="Stored score" design={selected} /> : null}
      <p className="text-[11px] leading-4 text-lab-muted">{props.layoutNote} Object width source: {props.objectSource}.</p>
      <p className="text-[11px] leading-4 text-lab-muted">No per-part stress is stored, so the mesh has no stress colors. Mean deflection, when present, is a scalar and does not bend the geometry.</p>
      {selected?.score.mean_deflection_mm !== undefined ? <p className="font-mono text-[11px]">Mean deflection {selected.score.mean_deflection_mm.toFixed(2)} mm · basis {selected.score.score_basis ?? "stored aggregate"}</p> : null}
      {props.parsed ? (
        <div className="rounded-md border border-lab-amber/40 p-2 font-mono text-[11px] leading-5">
          <p className="text-lab-amber">From the archived explanation, not a new solve.</p>
          <p>Friction capacity {props.parsed.frictionCapacityN.toFixed(2)} N</p>
          <p>Required holding force {props.parsed.requiredForceN.toFixed(2)} N</p>
          <p>Deflection {props.parsed.deflectionMm.toFixed(2)} mm · scale {props.parsed.deflectionScale.toFixed(2)} · engagement {props.parsed.engagement.toFixed(2)}</p>
        </div>
      ) : null}
      <div className="flex items-center justify-between">
        <h3 className="font-serif text-lg">Side by side</h3>
        <button type="button" className="text-xs text-lab-cyan" onClick={props.onUseBaseline}>Use random baseline</button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <ScoreBlock title={compare?.id ?? "Baseline"} design={compare} />
        <ScoreBlock title={selected?.id ?? "Focus"} design={selected} />
      </div>
      <h3 className="font-serif text-lg">Archived failures</h3>
      <ul className="max-h-40 space-y-1 overflow-auto">
        {props.failures.length === 0 ? <li className="text-xs text-lab-muted">None stored for this run.</li> : null}
        {props.failures.map((item) => (
          <li key={item.id}>
            <button type="button" className="w-full rounded-md bg-lab-panel2 px-2 py-1 text-left text-xs" onClick={() => props.onPickFailure(item.id)}>
              <span className={marginTone(item.margin_n, item.feasible) === "pass" ? "text-lab-ok" : "text-lab-fail"}>{item.margin_n.toFixed(2)} N</span>
              {" · "}{item.design_id}
              <span className="mt-1 block text-lab-muted">{item.reasons.map((reason) => `${reasonTone(reason) === "warn" ? "warning" : "fail"}: ${reason}`).join(" · ")}</span>
            </button>
          </li>
        ))}
      </ul>
      {props.failure ? <p className="text-xs leading-5 text-lab-muted">{props.failure.explanation}</p> : null}
      {bundle?.report.planner ? (
        <div>
          <h3 className="font-serif text-lg">Hypothesis</h3>
          <p className="text-xs leading-5">{bundle.report.planner.hypothesis}</p>
          {bundle.report.planner.warnings.map((warning) => <p key={warning} className="mt-1 text-xs text-lab-amber">{warning}</p>)}
        </div>
      ) : null}
      {bundle ? (
        <div>
          <h3 className="font-serif text-lg">Holdout</h3>
          <ul className="font-mono text-[11px] leading-5">
            {bundle.report.holdout.filter((row) => row.preregistered).map((row) => (
              <li key={row.method}>
                <button type="button" className="text-left text-lab-cyan" onClick={() => props.onPickDesign(row.design_id)}>{row.method}</button>
                {" "}{(row.success_rate * 100).toFixed(0)}% · margin {row.worst_margin_n.toFixed(2)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {props.workspace === "energy" ? (
        <ul className="font-mono text-[11px]">
          {energyBlocks(selected?.parameters).map((block) => <li key={block.id}>{block.label} {block.value.toFixed(2)} {block.unit}</li>)}
          <li className="text-lab-amber">Hourly state of charge is not in the saved run.</li>
        </ul>
      ) : null}
      {bundle?.report.limitations?.length ? (
        <details>
          <summary className="cursor-pointer text-xs text-lab-muted">Limits and provenance</summary>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-lab-muted">
            {bundle.report.limitations.map((item) => <li key={item}>{item}</li>)}
          </ul>
          <ul className="mt-2 space-y-1 text-[11px] text-lab-muted">
            {bundle.report.provenance.slice(0, 8).map((event) => <li key={event.id}>{event.kind}: {event.summary}</li>)}
          </ul>
        </details>
      ) : null}
      <p className="font-mono text-[10px] text-lab-muted">Focus rank uses success, then worst margin, then lower material, then fitness. {bestOf(bundle?.candidates ?? [], "adversarial") ? `Adversarial train leader ${preregisteredDesign(bundle?.candidates ?? [])?.id ?? ""}.` : ""}</p>
    </div>
  );
}

function ScoreBlock({ title, design }: { title: string; design: ScoredDesign | null }) {
  if (!design) return <div className="rounded-md bg-lab-panel2 p-2 text-[11px] text-lab-muted">{title}<br />—</div>;
  return (
    <div className="rounded-md bg-lab-panel2 p-2 font-mono text-[10px] leading-4">
      <p className="truncate text-lab-text">{title}</p>
      <p>success {(design.score.success_rate * 100).toFixed(0)}%</p>
      <p className={design.score.worst_margin_n < 0 ? "text-lab-fail" : "text-lab-ok"}>worst margin {design.score.worst_margin_n.toFixed(2)}</p>
      <p>material {design.score.material_proxy.toFixed(1)}</p>
      <p>fitness {design.score.fitness.toFixed(1)}</p>
    </div>
  );
}
