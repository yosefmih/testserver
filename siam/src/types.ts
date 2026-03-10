export interface StrandedEnergySite {
  type: 'flare' | 'wind' | 'solar' | 'methane';
  name: string;
  lat: number;
  lon: number;
  state: string;
  properties: Record<string, unknown>;
}

export interface FiberResult {
  distanceMiles: number;
  nearestPointOnFiber: [number, number];
  fiberRouteName: string;
}

export interface DataCenterResult {
  name: string;
  provider: string;
  distanceMiles: number;
  distanceKm: number;
  coordinates: [number, number];
}

export interface FeasibilityReport {
  site: StrandedEnergySite;
  fiber: FiberResult;
  dataCenter: DataCenterResult;
  fiberCapex: number;
  rttMs: number;
  terrainType: TerrainType;
  energySavingsPerMonth: number;
  breakEvenMonths: number;
  itLoadMW: number;
  strandedRate: number;
  gridRate: number;
}

export type TerrainType = 'rural' | 'standard' | 'boring';

export const TERRAIN_COSTS: Record<TerrainType, { label: string; costPerMile: number }> = {
  rural: { label: 'Rural Plowing', costPerMile: 25000 },
  standard: { label: 'Standard Trenching', costPerMile: 100000 },
  boring: { label: 'Horizontal Boring', costPerMile: 250000 },
};

export const VCPU_PER_MW = 300000;
export const FIBER_SPEED_KM_PER_MS = 200;
export const ROUTING_OVERHEAD_MS = 2;
export const DEFAULT_STRANDED_RATE = 0.03;
