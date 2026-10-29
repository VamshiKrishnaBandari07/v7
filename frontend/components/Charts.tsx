"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";

import type { Report } from "@/lib/types";

const COLORS: Record<string, string> = {
  random: "#8a8175",
  evolutionary: "#0e6b52",
  adversarial: "#b6401a",
};

export function FitnessChart({ report }: { report: Report }) {
  const names = report.methods.map((method) => method.method);
  const calls = new Set<number>();
  report.methods.forEach((method) => method.history.forEach((point) => calls.add(point.simulator_calls)));
  const rows = [...calls]
    .sort((a, b) => a - b)
    .map((call) => {
      const row: Record<string, number> = { calls: call };
      report.methods.forEach((method) => {
        const prior = [...method.history].reverse().find((point) => point.simulator_calls <= call);
        if (prior) row[method.method] = prior.best_fitness;
      });
      return row;
    });
  return (
    <div className="h-64 w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#eadfce" />
          <XAxis dataKey="calls" tick={{ fontSize: 11 }} label={{ value: "Simulator calls", position: "insideBottom", offset: -2, fontSize: 11 }} height={40} />
          <YAxis tick={{ fontSize: 11 }} width={42} />
          <Tooltip />
          <Legend />
          {names.map((name) => (
            <Line key={name} type="monotone" dataKey={name} stroke={COLORS[name] ?? "#241c16"} dot={false} strokeWidth={2} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ParetoChart({ report }: { report: Report }) {
  return (
    <div className="h-64 w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
          <CartesianGrid stroke="#eadfce" />
          <XAxis dataKey="material_proxy" name="Material" tick={{ fontSize: 11 }} />
          <YAxis dataKey="success_rate" name="Success" tick={{ fontSize: 11 }} width={42} domain={[0, 1]} />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} />
          <Legend />
          {report.methods.map((method) => (
            <Scatter key={method.method} name={method.method} data={method.pareto} fill={COLORS[method.method] ?? "#241c16"} />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
