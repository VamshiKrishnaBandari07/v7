"use client";

type Props = {
  domain: string;
  parameters: Record<string, number> | null;
  objectWidth: number;
};

export function Figure({ domain, parameters, objectWidth }: Props) {
  if (!parameters) {
    return <p className="p-6 text-sm text-ink/70">No frozen design yet.</p>;
  }
  if (domain === "energy") {
    const rows = [
      ["Solar", parameters.solar_kw, 8, "kW"],
      ["Storage", parameters.storage_kwh, 20, "kWh"],
      ["Discharge", parameters.discharge_kw, 5, "kW"],
    ] as const;
    return (
      <div className="space-y-4 p-4">
        {rows.map(([label, value, max, unit]) => (
          <div key={label}>
            <div className="mb-1 flex justify-between font-mono text-xs">
              <span>{label}</span>
              <span>
                {value.toFixed(2)} {unit}
              </span>
            </div>
            <div className="h-3 rounded-full bg-line">
              <div className="h-3 rounded-full bg-moss" style={{ width: `${Math.min(100, (value / max) * 100)}%` }} />
            </div>
          </div>
        ))}
        <p className="text-sm text-ink/70">Simplified 24-hour balance. Not a grid model.</p>
      </div>
    );
  }

  const jaw = parameters.jaw_opening_mm ?? 60;
  const finger = parameters.finger_length_mm ?? 40;
  const pad = parameters.pad_width_mm ?? 12;
  const scale = 240 / 90;
  const gap = jaw * scale;
  const obj = Math.min(objectWidth, jaw) * scale;
  const fingerH = 40 + (finger / 80) * 110;
  const padH = 16 + (pad / 30) * 54;
  const cx = 210;
  const left = cx - gap / 2 - 16;
  const right = cx + gap / 2;
  const top = 150 - fingerH / 2;

  return (
    <svg viewBox="0 0 420 250" className="h-auto w-full" role="img" aria-label="Parametric gripper">
      <rect x="0" y="0" width="420" height="250" fill="#f7f1e7" />
      {[0, 1, 2, 3, 4].map((row) => (
        <line key={row} x1="24" x2="396" y1={40 + row * 40} y2={40 + row * 40} stroke="#eadfce" />
      ))}
      <rect x={cx - obj / 2} y={108} width={obj} height={46} rx="4" fill="#c9844a" />
      <rect x={left} y={top} width="16" height={fingerH} rx="3" fill="#241c16" />
      <rect x={right} y={top} width="16" height={fingerH} rx="3" fill="#241c16" />
      <rect x={left + 12} y={131 - padH / 2} width="6" height={padH} fill="#0e6b52" />
      <rect x={right - 2} y={131 - padH / 2} width="6" height={padH} fill="#0e6b52" />
      <text x="24" y="28" className="fill-ink" fontFamily="IBM Plex Mono, monospace" fontSize="12">
        jaw {jaw.toFixed(0)} mm · finger {finger.toFixed(0)} mm · pad {pad.toFixed(0)} mm
      </text>
      <text x="24" y="228" fontFamily="IBM Plex Mono, monospace" fontSize="12" fill="#241c16">
        force {parameters.actuator_force_n?.toFixed(0)} N · stiffness {parameters.stiffness_n_per_mm?.toFixed(1)} N/mm
      </text>
    </svg>
  );
}
