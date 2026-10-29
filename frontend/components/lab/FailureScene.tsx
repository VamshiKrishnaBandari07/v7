"use client";

import { Html, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";

import { fitNote, gripperLayout, parseGripperExplanation, type CameraView, type ScoredDesign, type StoredFailure } from "@/lib/lab-model";
import { GRIPPER_CAMERAS, GripperAssembly, Ground, LabGrid, LabLights, StageRig } from "@/components/lab/stage";

export function FailureScene({
  baseline,
  focus,
  failure,
  objectWidthMm,
  cameraView,
  cameraNonce,
  showGrid,
  showDimensions,
  showScale,
  showGeometry,
  showForces,
  selectedPart,
  onSelectPart,
}: {
  baseline: ScoredDesign | null;
  focus: ScoredDesign | null;
  failure: StoredFailure | null;
  objectWidthMm: number;
  cameraView: CameraView;
  cameraNonce: number;
  showGrid: boolean;
  showDimensions: boolean;
  showScale: boolean;
  showGeometry: boolean;
  showForces: boolean;
  selectedPart: string | null;
  onSelectPart: (part: string) => void;
}) {
  const left = gripperLayout(baseline?.parameters);
  const right = gripperLayout(focus?.parameters);
  if (!left && !right) return <div className="flex h-full items-center justify-center text-sm text-lab-muted">No gripper designs are stored for a side-by-side view.</div>;
  const parsed = failure && focus && failure.design_id === focus.id ? parseGripperExplanation(failure.explanation) : null;
  const floor = Math.min(left?.fingerTipYmm ?? 0, right?.fingerTipYmm ?? 0) * 0.001 - 0.02;
  return (
    <div className="relative h-full">
      <Canvas shadows dpr={[1, 1.5]} camera={{ position: [0.34, 0.16, 0.42], fov: 38, near: 0.001, far: 10 }}>
        <LabLights />
        {showGrid ? <LabGrid floorY={floor} /> : null}
        <Ground y={floor} />
        {left && baseline ? (
          <GripperAssembly
            layout={left}
            objectWidthMm={objectWidthMm}
            objectWarn={objectWidthMm > left.jawOpeningMm}
            illustrative={false}
            selected={selectedPart}
            onSelect={onSelectPart}
            offset={[-0.16, 0, 0]}
            showDimensions={showDimensions}
            showScale={false}
            showGeometry={showGeometry}
            showForces={showForces}
            marginN={baseline.score.worst_margin_n}
            caption={`${baseline.id} · random baseline`}
          />
        ) : null}
        {right && focus ? (
          <GripperAssembly
            layout={right}
            objectWidthMm={parsed?.objectWidthMm ?? objectWidthMm}
            objectWarn={(parsed?.objectWidthMm ?? objectWidthMm) > right.jawOpeningMm}
            illustrative={false}
            selected={selectedPart}
            onSelect={onSelectPart}
            offset={[0.16, 0, 0]}
            showDimensions={showDimensions}
            showScale={showScale}
            showGeometry={showGeometry}
            showForces={showForces}
            marginN={focus.score.worst_margin_n}
            caption={`${focus.id} · comparison`}
          />
        ) : null}
        {parsed ? <StoredForceNote parsed={parsed} /> : null}
        <OrbitControls makeDefault enablePan minDistance={0.12} maxDistance={1.4} />
        <StageRig preset={cameraView} nonce={cameraNonce} cameras={WIDE} target={[0, -0.03, 0]} />
      </Canvas>
      {parsed ? (
        <p className="pointer-events-none absolute bottom-3 left-3 max-w-md rounded-md bg-lab-panel/90 px-2 py-1 font-mono text-[10px] leading-4 text-lab-amber">
          Required {parsed.requiredForceN.toFixed(2)} N · friction capacity {parsed.frictionCapacityN.toFixed(2)} N · copied from the archived explanation, not a new solve.
        </p>
      ) : null}
    </div>
  );
}

const WIDE: typeof GRIPPER_CAMERAS = {
  front: [0, -0.02, 0.55],
  side: [0.62, -0.02, 0.01],
  top: [0.01, 0.58, 0.01],
  isometric: [0.36, 0.2, 0.42],
};

function StoredForceNote({ parsed }: { parsed: { requiredForceN: number; frictionCapacityN: number } }) {
  const scale = 0.04 / Math.max(parsed.requiredForceN, parsed.frictionCapacityN, 1);
  return (
    <group position={[0.16, 0.03, 0.04]}>
      <mesh position={[0, parsed.requiredForceN * scale * 0.5, 0]}>
        <boxGeometry args={[0.004, Math.max(0.004, parsed.requiredForceN * scale), 0.004]} />
        <meshStandardMaterial color="#e2b15a" />
      </mesh>
      <mesh position={[0.012, parsed.frictionCapacityN * scale * 0.5, 0]}>
        <boxGeometry args={[0.004, Math.max(0.004, parsed.frictionCapacityN * scale), 0.004]} />
        <meshStandardMaterial color="#e15b4c" />
      </mesh>
      <Html position={[0.02, 0.03, 0]} style={{ pointerEvents: "none" }}>
        <span className="font-mono text-[10px] text-lab-muted">amber required · red capacity</span>
      </Html>
    </group>
  );
}

export function failureFit(focus: ScoredDesign | null, width: number) {
  const layout = gripperLayout(focus?.parameters);
  if (!layout) return "";
  return fitNote(layout.jawOpeningMm, width);
}
