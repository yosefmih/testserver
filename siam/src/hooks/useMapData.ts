import { useState, useEffect } from 'react';
import type { FeatureCollection } from 'geojson';

interface MapData {
  flares: FeatureCollection | null;
  renewables: FeatureCollection | null;
  lmop: FeatureCollection | null;
  fiber: FeatureCollection | null;
  datacenters: FeatureCollection | null;
  energyRates: Record<string, number> | null;
  loading: boolean;
  error: string | null;
}

async function fetchJSON<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch ${url}: ${response.status}`);
  return response.json();
}

export function useMapData(): MapData {
  const [data, setData] = useState<MapData>({
    flares: null,
    renewables: null,
    lmop: null,
    fiber: null,
    datacenters: null,
    energyRates: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    async function loadAll() {
      try {
        const [flares, renewables, lmop, fiber, datacenters, energyRates] = await Promise.all([
          fetchJSON<FeatureCollection>('/data/viirs_flares.geojson'),
          fetchJSON<FeatureCollection>('/data/eia860_renewables.geojson'),
          fetchJSON<FeatureCollection>('/data/lmop.geojson'),
          fetchJSON<FeatureCollection>('/data/fiber_backbone.geojson'),
          fetchJSON<FeatureCollection>('/data/datacenters.geojson'),
          fetchJSON<Record<string, number>>('/data/energy_rates.json'),
        ]);

        setData({
          flares,
          renewables,
          lmop,
          fiber,
          datacenters,
          energyRates,
          loading: false,
          error: null,
        });
      } catch (err) {
        setData((prev) => ({
          ...prev,
          loading: false,
          error: err instanceof Error ? err.message : 'Failed to load data',
        }));
      }
    }

    loadAll();
  }, []);

  return data;
}
