import type { TerrainType } from '../types';
import {
  TERRAIN_COSTS,
  VCPU_PER_MW,
  FIBER_SPEED_KM_PER_MS,
  ROUTING_OVERHEAD_MS,
} from '../types';

export function calculateFiberCapex(distanceMiles: number, terrainType: TerrainType): number {
  return distanceMiles * TERRAIN_COSTS[terrainType].costPerMile;
}

export function calculateRTT(distanceKm: number): number {
  return (distanceKm * 2) / FIBER_SPEED_KM_PER_MS + ROUTING_OVERHEAD_MS;
}

export function calculateEnergySavingsPerMonth(
  itLoadMW: number,
  gridRate: number,
  strandedRate: number
): number {
  const hoursPerMonth = 730;
  const kwhPerMonth = itLoadMW * 1000 * hoursPerMonth;
  return kwhPerMonth * (gridRate - strandedRate);
}

export function calculateBreakEven(
  fiberCapex: number,
  itLoadMW: number,
  gridRate: number,
  strandedRate: number
): number {
  const monthlySavings = calculateEnergySavingsPerMonth(itLoadMW, gridRate, strandedRate);
  if (monthlySavings <= 0) return Infinity;
  return fiberCapex / monthlySavings;
}

export function calculateVCPUs(itLoadMW: number): number {
  return Math.round(itLoadMW * VCPU_PER_MW);
}

export function formatCurrency(amount: number): string {
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(2)}M`;
  if (amount >= 1_000) return `$${(amount / 1_000).toFixed(0)}K`;
  return `$${amount.toFixed(0)}`;
}

export function formatDistance(miles: number): string {
  if (miles >= 100) return `${miles.toFixed(0)} mi`;
  return `${miles.toFixed(1)} mi`;
}
