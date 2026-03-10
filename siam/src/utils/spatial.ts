import * as turf from '@turf/turf';
import type { FeatureCollection } from 'geojson';
import type { FiberResult, DataCenterResult } from '../types';

export function findNearestFiber(
  point: [number, number],
  fiberGeoJSON: FeatureCollection
): FiberResult {
  const turfPoint = turf.point(point);
  let nearestDistance = Infinity;
  let nearestCoord: [number, number] = [0, 0];
  let nearestRouteName = 'Unknown';

  for (const feature of fiberGeoJSON.features) {
    if (feature.geometry.type !== 'LineString' && feature.geometry.type !== 'MultiLineString') {
      continue;
    }

    const snapped = turf.nearestPointOnLine(
      feature as GeoJSON.Feature<GeoJSON.LineString>,
      turfPoint,
      { units: 'miles' }
    );

    const dist = snapped.properties.dist ?? Infinity;
    if (dist < nearestDistance) {
      nearestDistance = dist;
      nearestCoord = snapped.geometry.coordinates as [number, number];
      nearestRouteName = (feature.properties?.route_name as string) ?? 'Unknown';
    }
  }

  return {
    distanceMiles: nearestDistance,
    nearestPointOnFiber: nearestCoord,
    fiberRouteName: nearestRouteName,
  };
}

export function findNearestDataCenter(
  point: [number, number],
  dcGeoJSON: FeatureCollection
): DataCenterResult {
  const turfPoint = turf.point(point);
  let nearest: DataCenterResult = {
    name: 'Unknown',
    provider: 'Unknown',
    distanceMiles: Infinity,
    distanceKm: Infinity,
    coordinates: [0, 0],
  };

  for (const feature of dcGeoJSON.features) {
    if (feature.geometry.type !== 'Point') continue;

    const coords = feature.geometry.coordinates as [number, number];
    const dcPoint = turf.point(coords);
    const distMiles = turf.distance(turfPoint, dcPoint, { units: 'miles' });
    const distKm = turf.distance(turfPoint, dcPoint, { units: 'kilometers' });

    if (distMiles < nearest.distanceMiles) {
      nearest = {
        name: (feature.properties?.name as string) ?? 'Unknown',
        provider: (feature.properties?.provider as string) ?? 'Unknown',
        distanceMiles: distMiles,
        distanceKm: distKm,
        coordinates: coords,
      };
    }
  }

  return nearest;
}
