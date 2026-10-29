"use client";

import { Html, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";

import { energyBlocks, type CameraView, type ScoredDesign } from "@/lib/lab-model";
import { SWARM_CAMERAS, StageRig } from "@/components/lab/stage";

export function EnergyScene({
  design,
  cameraView,
  cameraNonce,
}: {
  design: ScoredDesign | null;
  cameraView: CameraView;
  cameraNonce: number;
}) {
  const blocks = energyBlocks(design?.parameters);
  if (!blocks.length) {
    return (
      <div className="flex h-full items-center justify-center px-8 text-center text-sm leading-6 text-lab-muted">
        This run has no solar, storage, and discharge ratings. The energy view does not invent a plant or an hourly trace.
      </div>
    );
  }
  return (
    <div className="relative h-full">
      <Canvas dpr={[1, 1.5]} camera={{ position: [2.4, 1.6, 2.6], fov: 40 }}>
        <color attach="background" args={["#0c1424"]} />
        <ambientLight intensity={0.45} />
        <directionalLight position={[2, 3, 2]} intensity={1.3} />
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]} receiveShadow>
          <planeGeometry args={[4, 3]} />
          <meshStandardMaterial color="#10192b" metalness={0.2} roughness={0.85} />
        </mesh>
        {blocks.map((block, index) => (
          <group key={block.id} position={[(index - 1) * 0.85, 0, 0]}>
            <mesh position={[0, 0.15 + block.fraction * 0.45, 0]} castShadow>
              <boxGeometry args={[0.42, 0.3 + block.fraction * 0.9, 0.42]} />
              <meshStandardMaterial color={index === 1 ? "#8aa0b8" : "#1f6f78"} metalness={0.72} roughness={0.32} />
            </mesh>
            <Html position={[0, 1.15, 0]} center style={{ pointerEvents: "none" }}>
              <span className="whitespace-nowrap rounded bg-lab-panel/90 px-2 py-1 text-center font-mono text-[10px] text-lab-text">
                {block.label}
                <br />
                {block.value.toFixed(2)} {block.unit}
              </span>
            </Html>
          </group>
        ))}
        <Html position={[0, -0.2, 0.9]} center style={{ pointerEvents: "none" }}>
          <span className="max-w-xs text-center font-mono text-[10px] text-lab-amber">Ratings only. Hourly flow and state of charge are not stored on the run.</span>
        </Html>
        <OrbitControls makeDefault enablePan minDistance={1.5} maxDistance={8} />
        <StageRig preset={cameraView} nonce={cameraNonce} cameras={ENERGY_CAMERAS} target={[0, 0.3, 0]} />
      </Canvas>
    </div>
  );
}

const ENERGY_CAMERAS: Record<CameraView, [number, number, number]> = {
  front: [0, 0.4, 3.2],
  side: [3.2, 0.4, 0.01],
  top: [0.01, 3.4, 0.01],
  isometric: SWARM_CAMERAS.isometric.map((value) => value * 0.45) as [number, number, number],
};
