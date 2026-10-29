import type { Bundle, Candidate, FailureCase, Report, RunView } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export async function getHealth(): Promise<{ status: string; enable_meta: boolean; simulator_version: string }> {
  const response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!response.ok) throw new Error("The experiment API is not running.");
  return response.json();
}

export async function createRun(body: Record<string, unknown>): Promise<{ id: string; status: string }> {
  const response = await fetch(`${API_BASE}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "The run was rejected.");
  }
  return response.json();
}

export async function getRun(id: string): Promise<RunView> {
  const response = await fetch(`${API_BASE}/runs/${id}`, { cache: "no-store" });
  if (!response.ok) throw new Error("The run could not be read.");
  return response.json();
}

export async function getCandidates(id: string): Promise<Candidate[]> {
  const response = await fetch(`${API_BASE}/runs/${id}/candidates`, { cache: "no-store" });
  if (!response.ok) throw new Error("Candidates are not available.");
  return response.json();
}

export async function cancelRun(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/runs/${id}/cancel`, { method: "POST" });
  if (!response.ok) throw new Error("The run could not be cancelled.");
}

export async function getFailures(id: string): Promise<FailureCase[]> {
  const response = await fetch(`${API_BASE}/runs/${id}/failures`, { cache: "no-store" });
  if (!response.ok) throw new Error("Failures are not available.");
  return response.json();
}

export async function loadHero(): Promise<Bundle> {
  const response = await fetch("/demo/hero.json", { cache: "no-store" });
  if (!response.ok) throw new Error("The recorded hero run is missing.");
  const bundle = (await response.json()) as Bundle;
  if (!bundle.report) throw new Error("The hero file has no report.");
  return bundle;
}

export function downloadBundle(bundle: Bundle) {
  const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `swarm-${bundle.report.domain}-seed-${bundle.report.seed}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

export function preregistered(report: Report) {
  return report.holdout.filter((row) => row.preregistered);
}
