import { useState, useCallback } from 'react';
import { useMapData } from './hooks/useMapData';
import { MapView } from './components/MapView';
import { SidePanel } from './components/SidePanel';
import { Legend } from './components/Legend';
import type { FeasibilityReport } from './types';

export default function App() {
  const { flares, renewables, lmop, fiber, datacenters, energyRates, loading, error } = useMapData();
  const [report, setReport] = useState<FeasibilityReport | null>(null);

  const handleSiteSelected = useCallback((r: FeasibilityReport) => {
    setReport(r);
  }, []);

  const handleClose = useCallback(() => {
    setReport(null);
  }, []);

  return (
    <div className="w-screen h-screen relative overflow-hidden">
      {loading && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-[#020617]">
          <div className="text-center">
            <div className="w-12 h-12 border-4 border-[var(--accent)]/30 border-t-[var(--accent)] rounded-full animate-spin mx-auto mb-4" />
            <h1 className="text-xl font-bold mb-1">SIAM</h1>
            <p className="text-sm text-[var(--text-secondary)]">
              Loading geospatial data...
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 bg-red-900/80 text-red-200 px-4 py-2 rounded-lg text-sm">
          {error}
        </div>
      )}

      <MapView
        flares={flares}
        renewables={renewables}
        lmop={lmop}
        fiber={fiber}
        datacenters={datacenters}
        energyRates={energyRates}
        onSiteSelected={handleSiteSelected}
      />

      <Legend />

      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10">
        <h1 className="text-sm font-bold tracking-widest uppercase text-[var(--text-secondary)] bg-[var(--panel-bg)]/80 backdrop-blur-sm px-4 py-1.5 rounded-full border border-[var(--panel-border)]">
          Strategic Infrastructure Arbitrage Map
        </h1>
      </div>

      <SidePanel report={report} onClose={handleClose} />
    </div>
  );
}
