import { useState, useMemo } from 'react';
import type { FeasibilityReport, TerrainType } from '../types';
import { TERRAIN_COSTS, DEFAULT_STRANDED_RATE } from '../types';
import {
  calculateFiberCapex,
  calculateRTT,
  calculateBreakEven,
  calculateEnergySavingsPerMonth,
  calculateVCPUs,
  formatCurrency,
  formatDistance,
} from '../utils/calculations';

interface SidePanelProps {
  report: FeasibilityReport | null;
  onClose: () => void;
}

const TYPE_COLORS: Record<string, string> = {
  flare: 'var(--energy-flare)',
  wind: 'var(--energy-wind)',
  solar: 'var(--energy-solar)',
  methane: 'var(--energy-methane)',
};

const TYPE_LABELS: Record<string, string> = {
  flare: 'Flare Gas',
  wind: 'Wind',
  solar: 'Solar',
  methane: 'Landfill Methane',
};

export function SidePanel({ report, onClose }: SidePanelProps) {
  const [terrainType, setTerrainType] = useState<TerrainType>('rural');
  const [itLoadMW, setItLoadMW] = useState(1);
  const [strandedRate, setStrandedRate] = useState(DEFAULT_STRANDED_RATE);

  const calculations = useMemo(() => {
    if (!report) return null;

    const fiberCapex = calculateFiberCapex(report.fiber.distanceMiles, terrainType);
    const rttMs = calculateRTT(report.dataCenter.distanceKm);
    const gridRate = report.gridRate;
    const monthlySavings = calculateEnergySavingsPerMonth(itLoadMW, gridRate, strandedRate);
    const breakEvenMonths = calculateBreakEven(fiberCapex, itLoadMW, gridRate, strandedRate);
    const vcpus = calculateVCPUs(itLoadMW);

    return { fiberCapex, rttMs, monthlySavings, breakEvenMonths, vcpus };
  }, [report, terrainType, itLoadMW, strandedRate]);

  if (!report || !calculations) return null;

  const { site, fiber, dataCenter } = report;

  return (
    <div className="absolute top-0 right-0 z-20 h-full w-[420px] bg-[var(--panel-bg)] border-l border-[var(--panel-border)] overflow-y-auto shadow-2xl">
      <div className="p-5">
        {/* Header */}
        <div className="flex items-start justify-between mb-5">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span
                className="px-2 py-0.5 rounded text-xs font-semibold uppercase"
                style={{
                  backgroundColor: TYPE_COLORS[site.type] + '22',
                  color: TYPE_COLORS[site.type],
                }}
              >
                {TYPE_LABELS[site.type]}
              </span>
              <span className="text-xs text-[var(--text-secondary)]">{site.state}</span>
            </div>
            <h2 className="text-lg font-bold">{site.name}</h2>
            <p className="text-xs text-[var(--text-secondary)] mt-0.5">
              {site.lat.toFixed(4)}°N, {Math.abs(site.lon).toFixed(4)}°W
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-secondary)] hover:text-white p-1 rounded hover:bg-white/10 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        {/* Fiber Connection */}
        <Section title="Fiber Connection">
          <MetricRow label="Distance to Fiber" value={formatDistance(fiber.distanceMiles)} accent />
          <MetricRow label="Nearest Route" value={fiber.fiberRouteName} />
        </Section>

        {/* Fiber CapEx Estimator */}
        <Section title="Fiber CapEx Estimator">
          <div className="space-y-2 mb-3">
            {(Object.entries(TERRAIN_COSTS) as [TerrainType, typeof TERRAIN_COSTS.rural][]).map(
              ([key, config]) => (
                <label
                  key={key}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer border transition-colors ${
                    terrainType === key
                      ? 'border-[var(--accent)] bg-[var(--accent)]/10'
                      : 'border-[var(--panel-border)] hover:border-[var(--panel-border)]/80'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="terrain"
                      checked={terrainType === key}
                      onChange={() => setTerrainType(key)}
                      className="sr-only"
                    />
                    <span
                      className="w-3 h-3 rounded-full border-2"
                      style={{
                        backgroundColor: terrainType === key ? 'var(--accent)' : 'transparent',
                        borderColor: 'var(--accent)',
                      }}
                    />
                    <span className="text-sm">{config.label}</span>
                  </div>
                  <span className="text-xs text-[var(--text-secondary)]">
                    ${(config.costPerMile / 1000).toFixed(0)}K/mi
                  </span>
                </label>
              )
            )}
          </div>
          <div className="bg-[var(--accent)]/10 border border-[var(--accent)]/30 rounded-lg p-3 text-center">
            <p className="text-xs text-[var(--accent)] mb-1">Estimated CapEx</p>
            <p className="text-2xl font-bold text-[var(--accent)]">
              {formatCurrency(calculations.fiberCapex)}
            </p>
          </div>
        </Section>

        {/* Network Latency */}
        <Section title="Network Latency">
          <MetricRow
            label="RTT to Hub"
            value={`${calculations.rttMs.toFixed(2)} ms`}
            accent
          />
          <MetricRow label="Nearest Hub" value={dataCenter.name} />
          <MetricRow label="Provider" value={dataCenter.provider} />
          <MetricRow
            label="Distance"
            value={`${dataCenter.distanceMiles.toFixed(0)} mi (${dataCenter.distanceKm.toFixed(0)} km)`}
          />
        </Section>

        {/* vCPU Floor Calculator */}
        <Section title="vCPU Floor Calculator">
          <div className="mb-3">
            <div className="flex justify-between text-sm mb-1">
              <span className="text-[var(--text-secondary)]">IT Load</span>
              <span className="font-semibold">{itLoadMW.toFixed(1)} MW</span>
            </div>
            <input
              type="range"
              min="0.5"
              max="10"
              step="0.5"
              value={itLoadMW}
              onChange={(e) => setItLoadMW(parseFloat(e.target.value))}
              className="w-full accent-[var(--accent)]"
            />
            <div className="flex justify-between text-xs text-[var(--text-secondary)]">
              <span>0.5 MW</span>
              <span>10 MW</span>
            </div>
          </div>

          <MetricRow
            label="Estimated vCPUs"
            value={calculations.vcpus.toLocaleString()}
            accent
          />
          <MetricRow
            label="Grid Rate"
            value={`$${report.gridRate.toFixed(3)}/kWh`}
          />

          <div className="mt-2 mb-2">
            <div className="flex justify-between text-sm mb-1">
              <span className="text-[var(--text-secondary)]">Stranded Rate</span>
              <span className="font-semibold">${strandedRate.toFixed(3)}/kWh</span>
            </div>
            <input
              type="range"
              min="0.01"
              max="0.06"
              step="0.005"
              value={strandedRate}
              onChange={(e) => setStrandedRate(parseFloat(e.target.value))}
              className="w-full accent-[var(--energy-methane)]"
            />
          </div>

          <div className="grid grid-cols-2 gap-2 mt-3">
            <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-2 text-center">
              <p className="text-xs text-emerald-400 mb-0.5">Monthly Savings</p>
              <p className="text-lg font-bold text-emerald-400">
                {formatCurrency(calculations.monthlySavings)}
              </p>
            </div>
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-2 text-center">
              <p className="text-xs text-amber-400 mb-0.5">Break Even</p>
              <p className="text-lg font-bold text-amber-400">
                {calculations.breakEvenMonths === Infinity
                  ? '∞'
                  : `${calculations.breakEvenMonths.toFixed(1)} mo`}
              </p>
            </div>
          </div>
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)] mb-2 pb-1 border-b border-[var(--panel-border)]">
        {title}
      </h3>
      {children}
    </div>
  );
}

function MetricRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex justify-between items-center py-1">
      <span className="text-sm text-[var(--text-secondary)]">{label}</span>
      <span className={`text-sm font-medium ${accent ? 'text-[var(--accent)]' : ''}`}>
        {value}
      </span>
    </div>
  );
}
