"use client";

import { Grid, Html, OrbitControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import * as THREE from "three";

import { DISPLAY_PAD_THICKNESS_MM, DISPLAY_STOCK_MM, SCALE_REFERENCE_MM, type CameraView, type GripperLayout } from "@/lib/lab-model";

export const GRIPPER_CAMERAS: Record<CameraView, [number, number, number]> = {
  front: [0, -0.025, 0.24],
  side: [0.28, -0.02, 0.001],
  top: [0.001, 0.26, 0.001],
  isometric: [0.16, 0.11, 0.18],
};

export const SWARM_CAMERAS: Record<CameraView, [number, number, number]> = {
  front: [0, 0, 7.2],
  side: [7.2, 0.2, 0.01],
  top: [0.01, 7.4, 0.01],
  isometric: [5.2, 3.5, 5.6],
};

const MM = 0.001;

export function StageRig({
  preset,
  nonce,
  cameras,
  target = [0, -0.03, 0],
}: {
  preset: CameraView;
  nonce: number;
  cameras: Record<CameraView, [number, number, number]>;
  target?: [number, number, number];
}) {
  const controls = useThree((state) => state.controls) as OrbitControlsImpl | null;
  const { camera } = useThree();
  const [tx, ty, tz] = target;
  useEffect(() => {
    const [x, y, z] = cameras[preset];
    camera.position.set(x, y, z);
    camera.lookAt(tx, ty, tz);
    if (controls) {
      controls.target.set(tx, ty, tz);
      controls.update();
    }
  }, [camera, cameras, controls, nonce, preset, tx, ty, tz]);
  return null;
}

export function LabLights() {
  return (
    <>
      <color attach="background" args={["#0c1424"]} />
      <ambientLight intensity={0.38} />
      <directionalLight
        castShadow
        position={[0.35, 0.55, 0.3]}
        intensity={1.55}
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-camera-near={0.01}
        shadow-camera-far={2}
        shadow-camera-left={-0.3}
        shadow-camera-right={0.3}
        shadow-camera-top={0.3}
        shadow-camera-bottom={-0.3}
      />
      <directionalLight position={[-0.3, 0.15, -0.2]} intensity={0.35} color="#9eb4d6" />
    </>
  );
}

export function LabGrid({ floorY, cell = 0.01 }: { floorY: number; cell?: number }) {
  return (
    <Grid
      args={[0.8, 0.8]}
      position={[0, floorY, 0]}
      cellSize={cell}
      cellThickness={0.6}
      cellColor="#1c3148"
      sectionSize={cell * 5}
      sectionThickness={1.1}
      sectionColor="#245066"
      fadeDistance={cell > 0.05 ? 14 : 0.7}
      infiniteGrid={false}
    />
  );
}

export function GripperAssembly({
  layout,
  objectWidthMm,
  objectWarn,
  illustrative,
  selected,
  onSelect,
  offset = [0, 0, 0],
  showDimensions,
  showScale,
  showGeometry,
  showForces,
  marginN,
  caption,
}: {
  layout: GripperLayout;
  objectWidthMm: number;
  objectWarn: boolean;
  illustrative: boolean;
  selected: string | null;
  onSelect: (part: string) => void;
  offset?: [number, number, number];
  showDimensions: boolean;
  showScale: boolean;
  showGeometry: boolean;
  showForces: boolean;
  marginN: number | null;
  caption?: string;
}) {
  const left = useRef<THREE.Group>(null);
  const right = useRef<THREE.Group>(null);
  const jawM = layout.jawOpeningMm * MM;
  const fingerM = layout.fingerLengthMm * MM;
  const padM = layout.padDrawnMm * MM;
  const stock = DISPLAY_STOCK_MM * MM;
  const padT = DISPLAY_PAD_THICKNESS_MM * MM;
  const fingerX = jawM / 2 + padT + stock / 2;
  const padX = jawM / 2 + padT / 2;
  const padY = layout.padCenterYmm * MM;
  const objectW = objectWidthMm * MM;
  const objectH = Math.min(objectWidthMm * 0.65, 50) * MM;
  const objectD = Math.min(objectWidthMm * 0.7, 40) * MM;

  useFrame(({ clock }) => {
    const factor = illustrative ? 0.72 + (0.5 + 0.5 * Math.sin(clock.elapsedTime * 0.7)) * 0.56 : 1;
    const shift = (jawM * (factor - 1)) / 2;
    if (left.current) left.current.position.x = -shift;
    if (right.current) right.current.position.x = shift;
  });

  const metal = "#9aa6b8";
  const padColor = "#1f6f78";
  const select = (part: string) => (event: { stopPropagation: () => void }) => {
    event.stopPropagation();
    onSelect(part);
  };

  return (
    <group position={offset}>
      {caption ? (
        <Html position={[0, 0.02, 0]} center style={{ pointerEvents: "none" }}>
          <span className="whitespace-nowrap rounded bg-lab-panel/90 px-2 py-0.5 font-mono text-[10px] text-lab-text">{caption}</span>
        </Html>
      ) : null}
      {showGeometry ? (
        <mesh position={[0, stock / 2, 0]} castShadow receiveShadow onClick={select("frame")}>
          <boxGeometry args={[jawM + stock * 2 + padT * 2, stock, stock * 1.4]} />
          <meshStandardMaterial color={metal} metalness={0.84} roughness={0.28} emissive={selected === "frame" ? "#7fd3e8" : "#000"} emissiveIntensity={0.18} />
        </mesh>
      ) : null}
      <group ref={left}>
        {showGeometry ? <Finger x={-fingerX} length={fingerM} stock={stock} selected={selected === "left-finger"} onClick={select("left-finger")} /> : null}
        {showGeometry ? <Pad x={-padX} y={padY} length={padM} thickness={padT} stock={stock} color={padColor} selected={selected === "left-pad"} onClick={select("left-pad")} /> : null}
        {showGeometry ? <Joint x={-(jawM / 2 + padT + stock / 2)} selected={selected === "left-joint"} onClick={select("left-joint")} /> : null}
        {showForces ? <ForceArrow x={-(jawM / 2 + padT + stock + 0.012)} y={padY} direction={1} newtons={layout.actuatorForceN} /> : null}
      </group>
      <group ref={right}>
        {showGeometry ? <Finger x={fingerX} length={fingerM} stock={stock} selected={selected === "right-finger"} onClick={select("right-finger")} /> : null}
        {showGeometry ? <Pad x={padX} y={padY} length={padM} thickness={padT} stock={stock} color={padColor} selected={selected === "right-pad"} onClick={select("right-pad")} /> : null}
        {showGeometry ? <Joint x={jawM / 2 + padT + stock / 2} selected={selected === "right-joint"} onClick={select("right-joint")} /> : null}
        {showForces ? <ForceArrow x={jawM / 2 + padT + stock + 0.012} y={padY} direction={-1} newtons={layout.actuatorForceN} /> : null}
      </group>
      {showGeometry ? (
        <mesh position={[0, padY, 0]} castShadow receiveShadow onClick={select("object")}>
          <boxGeometry args={[objectW, objectH, objectD]} />
          <meshStandardMaterial color={objectWarn || (marginN !== null && marginN < 0) ? "#c45b4a" : "#c4a574"} metalness={0.08} roughness={0.72} emissive={selected === "object" ? "#7fd3e8" : "#000"} emissiveIntensity={0.12} />
        </mesh>
      ) : null}
      {showDimensions ? (
        <Html position={[0, -fingerM - 0.018, 0]} center style={{ pointerEvents: "none", whiteSpace: "nowrap" }}>
          <span className="whitespace-nowrap font-mono text-[10px] text-lab-cyan">jaw {layout.jawOpeningMm.toFixed(1)} mm</span>
        </Html>
      ) : null}
      {showDimensions ? (
        <Html position={[fingerX + 0.03, -fingerM / 2, 0]} center style={{ pointerEvents: "none", whiteSpace: "nowrap" }}>
          <span className="whitespace-nowrap font-mono text-[10px] text-lab-muted">finger {layout.fingerLengthMm.toFixed(1)} mm</span>
        </Html>
      ) : null}
      {showDimensions ? (
        <Html position={[0, padY + padM / 2 + 0.014, 0]} center style={{ pointerEvents: "none", whiteSpace: "nowrap" }}>
          <span className="whitespace-nowrap font-mono text-[10px] text-lab-muted">pad {layout.padWidthMm.toFixed(1)} mm</span>
        </Html>
      ) : null}
      {showScale ? <ScaleBar y={-fingerM - 0.028} /> : null}
    </group>
  );
}

function Finger({ x, length, stock, selected, onClick }: { x: number; length: number; stock: number; selected: boolean; onClick: (event: { stopPropagation: () => void }) => void }) {
  return (
    <mesh position={[x, -length / 2, 0]} castShadow receiveShadow onClick={onClick}>
      <boxGeometry args={[stock, length, stock]} />
      <meshStandardMaterial color="#9aa6b8" metalness={0.82} roughness={0.32} emissive={selected ? "#7fd3e8" : "#000"} emissiveIntensity={0.2} />
    </mesh>
  );
}

function Pad({ x, y, length, thickness, stock, color, selected, onClick }: { x: number; y: number; length: number; thickness: number; stock: number; color: string; selected: boolean; onClick: (event: { stopPropagation: () => void }) => void }) {
  return (
    <mesh position={[x, y, 0]} castShadow onClick={onClick}>
      <boxGeometry args={[thickness, length, stock * 0.92]} />
      <meshStandardMaterial color={color} metalness={0.18} roughness={0.58} emissive={selected ? "#7fd3e8" : "#000"} emissiveIntensity={0.22} />
    </mesh>
  );
}

function Joint({ x, selected, onClick }: { x: number; selected: boolean; onClick: (event: { stopPropagation: () => void }) => void }) {
  return (
    <mesh position={[x, 0, 0]} rotation={[Math.PI / 2, 0, 0]} castShadow onClick={onClick}>
      <cylinderGeometry args={[0.0045, 0.0045, 0.012, 16]} />
      <meshStandardMaterial color="#6e7c90" metalness={0.7} roughness={0.35} emissive={selected ? "#7fd3e8" : "#000"} emissiveIntensity={0.25} />
    </mesh>
  );
}

function ForceArrow({ x, y, direction, newtons }: { x: number; y: number; direction: 1 | -1; newtons: number | null }) {
  if (newtons === null) return null;
  const length = 0.012 + Math.min(1, Math.abs(newtons) / 80) * 0.028;
  const tip = x + direction * length;
  return (
    <group>
      <mesh position={[(x + tip) / 2, y, 0]} rotation={[0, 0, direction === 1 ? -Math.PI / 2 : Math.PI / 2]}>
        <cylinderGeometry args={[0.0014, 0.0014, Math.max(0.004, length - 0.006), 8]} />
        <meshStandardMaterial color="#7fd3e8" metalness={0.2} roughness={0.4} />
      </mesh>
      <mesh position={[tip, y, 0]} rotation={[0, 0, direction === 1 ? -Math.PI / 2 : Math.PI / 2]}>
        <coneGeometry args={[0.0032, 0.008, 10]} />
        <meshStandardMaterial color="#7fd3e8" metalness={0.2} roughness={0.35} />
      </mesh>
      <Html position={[tip, y + 0.01, 0]} center style={{ pointerEvents: "none" }}>
        <span className="whitespace-nowrap font-mono text-[10px] text-lab-cyan">{newtons.toFixed(1)} N actuator</span>
      </Html>
    </group>
  );
}

function ScaleBar({ y }: { y: number }) {
  const length = SCALE_REFERENCE_MM * MM;
  return (
    <group position={[-0.08, y, 0]}>
      <mesh>
        <boxGeometry args={[length, 0.0012, 0.0012]} />
        <meshStandardMaterial color="#e6eef8" />
      </mesh>
      <Html position={[length / 2, -0.01, 0]} center style={{ pointerEvents: "none", whiteSpace: "nowrap" }}>
        <span className="whitespace-nowrap font-mono text-[10px] text-lab-text">10 mm</span>
      </Html>
    </group>
  );
}

export function Ground({ y }: { y: number }) {
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, y, 0]} receiveShadow>
      <planeGeometry args={[0.7, 0.7]} />
      <meshStandardMaterial color="#0e1626" metalness={0.12} roughness={0.92} />
    </mesh>
  );
}
