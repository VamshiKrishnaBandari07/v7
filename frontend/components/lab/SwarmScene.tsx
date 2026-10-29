"use client";

import { Html, Line, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { METHOD_STYLE, METHODS, axisSpans, lineageChain, swarmAxes, swarmPoint, visibleDesigns, type CameraView, type ScoredDesign } from "@/lib/lab-model";
import { SWARM_CAMERAS, StageRig } from "@/components/lab/stage";

type Point = ScoredDesign & { x: number; y: number; z: number; shown: boolean };

export function SwarmScene({
  designs,
  domain,
  generation,
  methods,
  finalistsOnly,
  selectedId,
  compareId,
  showLineage,
  cameraView,
  cameraNonce,
  onSelect,
  onHover,
}: {
  designs: ScoredDesign[];
  domain: string;
  generation: number;
  methods: Record<string, boolean>;
  finalistsOnly: boolean;
  selectedId: string | null;
  compareId: string | null;
  showLineage: boolean;
  cameraView: CameraView;
  cameraNonce: number;
  onSelect: (id: string) => void;
  onHover: (id: string | null, x: number, y: number) => void;
}) {
  const axes = swarmAxes(domain, designs[0]?.parameters);
  const spans = useMemo(() => axisSpans(designs, axes.xKey, axes.zKey), [axes.xKey, axes.zKey, designs]);
  const placed = useMemo(() => {
    const rows: Point[] = [];
    designs.forEach((design) => {
      const point = swarmPoint(design, axes.xKey, axes.zKey, spans);
      if (point) rows.push({ ...design, ...point, shown: true });
    });
    const allowed = new Set(visibleDesigns(rows, generation, methods, finalistsOnly).map((design) => design.id));
    return rows.map((row) => ({ ...row, shown: allowed.has(row.id) }));
  }, [axes.xKey, axes.zKey, designs, finalistsOnly, generation, methods, spans]);
  const chain = showLineage ? lineageChain(placed, selectedId) : [];
  const chainPoints = chain
    .map((id) => placed.find((design) => design.id === id))
    .filter((design): design is Point => Boolean(design))
    .map((design) => [design.x, design.y, design.z] as [number, number, number]);

  return (
    <Canvas dpr={[1, 1.5]} camera={{ position: SWARM_CAMERAS.isometric, fov: 42, near: 0.1, far: 40 }}>
      <color attach="background" args={["#0c1424"]} />
      <ambientLight intensity={0.7} />
      <directionalLight position={[4, 6, 3]} intensity={1.1} />
      {METHODS.map((method) => (
        <MethodCloud
          key={method}
          method={method}
          points={placed.filter((design) => design.method === method)}
          selectedId={selectedId}
          onSelect={onSelect}
          onHover={onHover}
        />
      ))}
      {chainPoints.length > 1 ? <Line points={chainPoints} color="#e6eef8" lineWidth={1} /> : null}
      <Marker id={selectedId} points={placed} color="#e6eef8" />
      <Marker id={compareId} points={placed} color="#e2b15a" />
      <Line points={[[-2.2, -2, -2], [2.2, -2, -2]]} color="#93a4bd" />
      <Line points={[[-2, -2.2, -2], [-2, 2.2, -2]]} color="#7fd3e8" />
      <Line points={[[-2, -2, -2.2], [-2, -2, 2.2]]} color="#b7a6ff" />
      <Html position={[2.35, -2, -2]} style={{ pointerEvents: "none" }}>
        <span className="font-mono text-[10px] text-lab-muted">X {axes.xLabel}</span>
      </Html>
      <Html position={[-2, 2.35, -2]} style={{ pointerEvents: "none" }}>
        <span className="font-mono text-[10px] text-lab-cyan">Y fitness (stored)</span>
      </Html>
      <Html position={[-2, -2, 2.35]} style={{ pointerEvents: "none" }}>
        <span className="font-mono text-[10px] text-lab-violet">Z {axes.zLabel}</span>
      </Html>
      <OrbitControls makeDefault enablePan minDistance={3} maxDistance={14} />
      <StageRig preset={cameraView} nonce={cameraNonce} cameras={SWARM_CAMERAS} target={[0, 0, 0]} />
    </Canvas>
  );
}

function MethodCloud({
  method,
  points,
  selectedId,
  onSelect,
  onHover,
}: {
  method: string;
  points: Point[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onHover: (id: string | null, x: number, y: number) => void;
}) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const color = new THREE.Color(METHOD_STYLE[method]?.color ?? "#e6eef8");
    points.forEach((point, index) => {
      const on = point.shown;
      dummy.position.set(point.x, point.y, point.z);
      const scale = !on ? 0 : point.id === selectedId ? 0.16 : point.preregistered ? 0.11 : 0.07;
      dummy.scale.setScalar(scale);
      dummy.updateMatrix();
      mesh.setMatrixAt(index, dummy.matrix);
      mesh.setColorAt(index, color);
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [dummy, method, points, selectedId]);

  if (!points.length) return null;
  const geometry = method === "evolutionary" ? <boxGeometry args={[1, 1, 1]} /> : method === "adversarial" ? <octahedronGeometry args={[0.85, 0]} /> : <sphereGeometry args={[0.7, 12, 12]} />;
  return (
    <instancedMesh
      ref={ref}
      args={[undefined, undefined, points.length]}
      frustumCulled={false}
      onClick={(event) => {
        event.stopPropagation();
        const index = event.instanceId;
        if (index === undefined || !points[index].shown) return;
        onSelect(points[index].id);
      }}
      onPointerMove={(event) => {
        const index = event.instanceId;
        if (index === undefined) return;
        onHover(points[index].id, event.nativeEvent.clientX, event.nativeEvent.clientY);
      }}
      onPointerOut={() => onHover(null, 0, 0)}
    >
      {geometry}
      <meshStandardMaterial roughness={0.45} metalness={0.15} />
    </instancedMesh>
  );
}

function Marker({ id, points, color }: { id: string | null; points: Point[]; color: string }) {
  const point = points.find((item) => item.id === id);
  if (!point) return null;
  return (
    <mesh position={[point.x, point.y, point.z]}>
      <sphereGeometry args={[0.12, 16, 16]} />
      <meshBasicMaterial color={color} wireframe />
    </mesh>
  );
}
