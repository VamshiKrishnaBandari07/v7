export interface HistoryPoint {
  generation: number;
  simulator_calls: number;
  best_fitness: number;
  best_success_rate: number;
  best_material: number;
  best_worst_margin: number;
}

export interface ParetoPoint {
  id: string;
  method: string;
  success_rate: number;
  material_proxy: number;
  worst_margin_n: number;
  fitness: number;
  parameters: Record<string, number>;
  preregistered: boolean;
}

export interface MethodReport {
  method: string;
  simulator_calls: number;
  design_evaluations: number;
  adversarial_calls: number;
  history: HistoryPoint[];
  pareto: ParetoPoint[];
  finalist_ids: string[];
  best: ParetoPoint | null;
}

export interface HoldoutScore {
  method: string;
  design_id: string;
  parameters: Record<string, number>;
  success_rate: number;
  mean_margin_n: number;
  worst_margin_n: number;
  material_proxy: number;
  scenario_count: number;
  preregistered: boolean;
  exploratory: boolean;
}

export interface ExperimentPlan {
  objective: string;
  hypothesis: string;
  rationale: string;
  simulation_calls: number;
  prioritized_actions: string[];
  provider: string;
  rejected_code: boolean;
  warnings: string[];
}

export interface ProvenanceEvent {
  id: string;
  kind: string;
  summary: string;
  payload: Record<string, unknown>;
}

export interface Report {
  run_id: string;
  domain: string;
  seed: number;
  status: string;
  simulator_version: string;
  assumptions_hash: string;
  holdout_fingerprint: string;
  train_fingerprint: string;
  search_budget_per_method: Record<string, number>;
  validation_calls: number;
  total_search_calls: number;
  methods: MethodReport[];
  holdout: HoldoutScore[];
  planner: ExperimentPlan | null;
  provenance: ProvenanceEvent[];
  limitations: string[];
  git_sha: string;
  failure_count: number;
  objective_labels: Record<string, string>;
  config?: Record<string, unknown>;
  train_scenarios?: Array<Record<string, number | string>>;
  holdout_scenarios?: Array<Record<string, number | string>>;
}

export interface Candidate {
  id: string;
  method: string;
  generation: number;
  parent_ids: string[];
  origin: string;
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
  is_finalist: boolean;
  preregistered: boolean;
}

export interface FailureCase {
  id: string;
  method: string;
  design_id: string;
  generation: number;
  parameters: Record<string, number>;
  scenario: Record<string, number | string>;
  margin_n: number;
  feasible: boolean;
  explanation: string;
  reasons: string[];
  linked_design_ids: string[];
}

export interface Bundle {
  report: Report;
  candidates: Candidate[];
  failures: FailureCase[];
}

export interface Progress {
  phase?: string;
  message?: string;
  simulator_calls?: number;
  budget?: number;
  best_score?: number | null;
  best_success_rate?: number | null;
}

export interface RunView {
  id: string;
  status: string;
  progress: Progress;
  error?: string | null;
  report?: Report | null;
}
