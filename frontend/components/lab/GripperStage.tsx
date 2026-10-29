"use client";

import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useMemo } from "react";

import { fitNote, gripperLayout, type CameraView } from "@/lib/lab-model";
import { GRIPPER_CAMERAS, GripperAssembly, Ground, LabGrid, LabLights, StageRig } from "@/components/lab/stage";

export function GripperStage({
  parameters,
  objectWidthMm,
  cameraView,
  cameraNonce,
  showGrid,
  showDimensions,
  showScale,
  showGeometry,
  showForces,
  marginN,
  illustrative,
  selectedPart,
  onSelectPart,
}: {
  parameters: Record<string, number> | null;
  objectWidthMm: number;
  cameraView: CameraView;
  cameraNonce: number;
  showGrid: boolean;
  showDimensions: boolean;
  showScale: boolean;
  showGeometry: boolean;
  showForces: boolean;
  marginN: number | null;
  illustrative: boolean;
  selectedPart: string | null;
  onSelectPart: (part: string) => void;
}) {
  const layout = useMemo(() => gripperLayout(parameters), [parameters]);
  if (!layout) {
    return <EmptyCanvas text="This design has no gripper parameters to draw." />;
  }
  const floor = layout.fingerTipYmm * 0.001 - 0.02;
  return (
    <Canvas shadows dpr={[1, 1.5]} camera={{ position: GRIPPER_CAMERAS.isometric, fov: 38, near: 0.001, far: 10 }} gl={{ antialias: true, powerPreference: "high-performance" }}>
      <LabLights />
      {showGrid ? <LabGrid floorY={floor} /> : null}
      <Ground y={floor} />
      <GripperAssembly
        layout={layout}
        objectWidthMm={objectWidthMm}
        objectWarn={objectWidthMm > layout.jawOpeningMm}
        illustrative={illustrative}
        selected={selectedPart}
        onSelect={onSelectPart}
        showDimensions={showDimensions}
        showScale={showScale}
        showGeometry={showGeometry}
        showForces={showForces}
        marginN={marginN}
      />
      <OrbitControls makeDefault enablePan enableZoom minDistance={0.08} maxDistance={0.8} />
      <StageRig preset={cameraView} nonce={cameraNonce} cameras={GRIPPER_CAMERAS} target={[0, layout.fingerTipYmm * 0.0005, 0]} />
    </Canvas>
  );
}

export function gripperReadout(parameters: Record<string, number> | null, objectWidthMm: number, objectSource: string) {
  const layout = gripperLayout(parameters);
  if (!layout) return null;
  return {
    layout,
    note: fitNote(layout.jawOpeningMm, objectWidthMm),
    objectSource,
  };
}

function EmptyCanvas({ text }: { text: string }) {
  return <div className="flex h-full items-center justify-center px-6 text-center text-sm text-lab-muted">{text}</div>;
}
