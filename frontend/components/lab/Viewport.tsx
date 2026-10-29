"use client";

import { Component, type ReactNode } from "react";

import { EnergyScene } from "@/components/lab/EnergyScene";
import { FailureScene } from "@/components/lab/FailureScene";
import { GripperStage } from "@/components/lab/GripperStage";
import { SwarmScene } from "@/components/lab/SwarmScene";
import { Figure } from "@/components/Figure";
import type { CameraView, ScoredDesign, StoredFailure, Workspace } from "@/lib/lab-model";

type Props = {
  webgl: boolean;
  workspace: Workspace;
  domain: string;
  parameters: Record<string, number> | null;
  objectWidthMm: number;
  objectSource: string;
  designs: ScoredDesign[];
  generation: number;
  methods: Record<string, boolean>;
  finalistsOnly: boolean;
  selectedId: string | null;
  compareId: string | null;
  baseline: ScoredDesign | null;
  focus: ScoredDesign | null;
  failure: StoredFailure | null;
  showLineage: boolean;
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
  onSelect: (id: string) => void;
  onHover: (id: string | null, x: number, y: number) => void;
};

export function Viewport(props: Props) {
  return (
    <ViewBoundary>
      {props.webgl ? <Scene {...props} /> : <Fallback parameters={props.parameters} domain={props.domain} objectWidth={props.objectWidthMm} />}
    </ViewBoundary>
  );
}

function Scene(props: Props) {
  if (props.workspace === "swarm") {
    return (
      <SwarmScene
        designs={props.designs}
        domain={props.domain}
        generation={props.generation}
        methods={props.methods}
        finalistsOnly={props.finalistsOnly}
        selectedId={props.selectedId}
        compareId={props.compareId}
        showLineage={props.showLineage}
        cameraView={props.cameraView}
        cameraNonce={props.cameraNonce}
        onSelect={props.onSelect}
        onHover={props.onHover}
      />
    );
  }
  if (props.workspace === "failure") {
    return (
      <FailureScene
        baseline={props.baseline}
        focus={props.focus}
        failure={props.failure}
        objectWidthMm={props.objectWidthMm}
        cameraView={props.cameraView}
        cameraNonce={props.cameraNonce}
        showGrid={props.showGrid}
        showDimensions={props.showDimensions}
        showScale={props.showScale}
        showGeometry={props.showGeometry}
        showForces={props.showForces}
        selectedPart={props.selectedPart}
        onSelectPart={props.onSelectPart}
      />
    );
  }
  if (props.workspace === "energy") {
    return <EnergyScene design={props.focus} cameraView={props.cameraView} cameraNonce={props.cameraNonce} />;
  }
  return (
    <GripperStage
      parameters={props.parameters}
      objectWidthMm={props.objectWidthMm}
      cameraView={props.cameraView}
      cameraNonce={props.cameraNonce}
      showGrid={props.showGrid}
      showDimensions={props.showDimensions}
      showScale={props.showScale}
      showGeometry={props.showGeometry}
      showForces={props.showForces}
      marginN={props.marginN}
      illustrative={props.illustrative}
      selectedPart={props.selectedPart}
      onSelectPart={props.onSelectPart}
    />
  );
}

function Fallback({ domain, parameters, objectWidth }: { domain: string; parameters: Record<string, number> | null; objectWidth: number }) {
  return (
    <div className="flex h-full flex-col bg-paper text-ink">
      <p className="px-4 pt-3 font-mono text-[11px] text-ink/70">WebGL is unavailable. This is the parametric schematic, not a digital twin.</p>
      <Figure domain={domain} parameters={parameters} objectWidth={objectWidth} />
    </div>
  );
}

class ViewBoundary extends Component<{ children: ReactNode }, { message: string }> {
  state = { message: "" };

  static getDerivedStateFromError(error: Error) {
    return { message: error.message };
  }

  render() {
    if (this.state.message) {
      return <div className="flex h-full items-center justify-center px-6 text-sm text-lab-amber">The 3D view stopped: {this.state.message}. Stored numbers in the inspector are unchanged.</div>;
    }
    return this.props.children;
  }
}
