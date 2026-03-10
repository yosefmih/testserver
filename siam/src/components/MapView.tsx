import { useRef, useEffect, useState, useCallback } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { FeatureCollection } from 'geojson';
import { findNearestFiber, findNearestDataCenter } from '../utils/spatial';
import type { FeasibilityReport, StrandedEnergySite } from '../types';
import { LayerToggle } from './LayerToggle';

interface MapViewProps {
  flares: FeatureCollection | null;
  renewables: FeatureCollection | null;
  lmop: FeatureCollection | null;
  fiber: FeatureCollection | null;
  datacenters: FeatureCollection | null;
  energyRates: Record<string, number> | null;
  onSiteSelected: (report: FeasibilityReport) => void;
}

const STYLE_URL = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

const LAYER_CONFIGS = [
  { id: 'flares', label: 'Flare Gas', color: '#f97316' },
  { id: 'wind', label: 'Wind', color: '#22d3ee' },
  { id: 'solar', label: 'Solar', color: '#facc15' },
  { id: 'lmop', label: 'Landfill Methane', color: '#a3e635' },
  { id: 'fiber', label: 'Fiber Backbone', color: '#c084fc' },
  { id: 'datacenters', label: 'Data Centers', color: '#f472b6' },
];

export function MapView({
  flares,
  renewables,
  lmop,
  fiber,
  datacenters,
  energyRates,
  onSiteSelected,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const sourcesReadyRef = useRef(false);

  const dataRef = useRef({ flares, renewables, lmop, fiber, datacenters });
  dataRef.current = { flares, renewables, lmop, fiber, datacenters };

  const [layerVisibility, setLayerVisibility] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(LAYER_CONFIGS.map((l) => [l.id, true]))
  );

  const handleToggle = useCallback((layerId: string) => {
    setLayerVisibility((prev) => {
      const next = { ...prev, [layerId]: !prev[layerId] };
      const map = mapRef.current;
      if (!map) return next;

      const visibility = next[layerId] ? 'visible' : 'none';
      const layerIds = getMapLayerIds(layerId);
      for (const lid of layerIds) {
        if (map.getLayer(lid)) {
          map.setLayoutProperty(lid, 'visibility', visibility);
        }
      }
      return next;
    });
  }, []);

  // Initialize map once
  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center: [-98.5, 39.8],
      zoom: 4,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl(), 'bottom-right');
    mapRef.current = map;

    map.on('load', () => {
      // Read from ref to get current data (not stale closure values)
      const d = dataRef.current;
      addFiberLayer(map, d.fiber);
      addFlareLayer(map, d.flares);
      addRenewablesLayer(map, d.renewables);
      addLMOPLayer(map, d.lmop);
      addDataCenterLayer(map, d.datacenters);
      addConnectionLineSources(map);
      sourcesReadyRef.current = true;
    });

    return () => {
      sourcesReadyRef.current = false;
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update sources when data changes after map is ready
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !sourcesReadyRef.current) return;
    updateSource(map, 'fiber-data', fiber);
  }, [fiber]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !sourcesReadyRef.current) return;
    updateSource(map, 'flares-data', flares);
  }, [flares]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !sourcesReadyRef.current) return;
    updateSource(map, 'renewables-data', renewables);
  }, [renewables]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !sourcesReadyRef.current) return;
    updateSource(map, 'lmop-data', lmop);
  }, [lmop]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !sourcesReadyRef.current) return;
    updateSource(map, 'dc-data', datacenters);
  }, [datacenters]);

  // Click handler for energy site selection
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const clickableLayers = ['flares-circles', 'wind-circles', 'solar-circles', 'lmop-circles'];

    function handleClick(e: maplibregl.MapMouseEvent) {
      if (!map) return;
      const features = map.queryRenderedFeatures(e.point, { layers: clickableLayers.filter((l) => map.getLayer(l)) });
      if (!features.length) {
        clearConnectionLines(map);
        return;
      }

      const feature = features[0];
      const coords = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
      const props = feature.properties ?? {};

      const siteType = props.type || 'flare';
      const site: StrandedEnergySite = {
        type: siteType,
        name: props.plant_name || props.name || props.basin || 'Unknown Site',
        lat: coords[1],
        lon: coords[0],
        state: props.state || '',
        properties: props,
      };

      if (!fiber || !datacenters) return;

      const fiberResult = findNearestFiber(coords, fiber);
      const dcResult = findNearestDataCenter(coords, datacenters);

      const gridRate = energyRates?.[site.state] ?? 0.08;

      drawConnectionLines(map, coords, fiberResult.nearestPointOnFiber, dcResult.coordinates);

      onSiteSelected({
        site,
        fiber: fiberResult,
        dataCenter: dcResult,
        fiberCapex: 0,
        rttMs: 0,
        terrainType: 'rural',
        energySavingsPerMonth: 0,
        breakEvenMonths: 0,
        itLoadMW: 1,
        strandedRate: 0.03,
        gridRate,
      });
    }

    map.on('click', handleClick);

    for (const layerId of clickableLayers) {
      map.on('mouseenter', layerId, () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', layerId, () => {
        map.getCanvas().style.cursor = '';
      });
    }

    return () => {
      map.off('click', handleClick);
    };
  }, [fiber, datacenters, energyRates, onSiteSelected]);

  const layerConfigsWithVisibility = LAYER_CONFIGS.map((l) => ({
    ...l,
    visible: layerVisibility[l.id] ?? true,
  }));

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" />
      <LayerToggle layers={layerConfigsWithVisibility} onToggle={handleToggle} />
    </div>
  );
}

function getMapLayerIds(toggleId: string): string[] {
  switch (toggleId) {
    case 'flares': return ['flares-circles', 'flares-cluster-circles', 'flares-cluster-count'];
    case 'wind': return ['wind-circles'];
    case 'solar': return ['solar-circles'];
    case 'lmop': return ['lmop-circles'];
    case 'fiber': return ['fiber-glow', 'fiber-lines'];
    case 'datacenters': return ['dc-circles', 'dc-pulse'];
    default: return [];
  }
}

function updateSource(map: maplibregl.Map, sourceId: string, data: FeatureCollection | null) {
  const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (source && data) {
    source.setData(data);
  }
}

function addFiberLayer(map: maplibregl.Map, data: FeatureCollection | null) {
  map.addSource('fiber-data', {
    type: 'geojson',
    data: data ?? { type: 'FeatureCollection', features: [] },
  });

  map.addLayer({
    id: 'fiber-glow',
    type: 'line',
    source: 'fiber-data',
    paint: {
      'line-color': '#c084fc',
      'line-width': 6,
      'line-opacity': 0.2,
    },
  });

  map.addLayer({
    id: 'fiber-lines',
    type: 'line',
    source: 'fiber-data',
    paint: {
      'line-color': '#c084fc',
      'line-width': 2,
      'line-opacity': 0.8,
    },
  });
}

function addFlareLayer(map: maplibregl.Map, data: FeatureCollection | null) {
  map.addSource('flares-data', {
    type: 'geojson',
    data: data ?? { type: 'FeatureCollection', features: [] },
    cluster: true,
    clusterMaxZoom: 10,
    clusterRadius: 50,
  });

  map.addLayer({
    id: 'flares-cluster-circles',
    type: 'circle',
    source: 'flares-data',
    filter: ['has', 'point_count'],
    paint: {
      'circle-color': '#f97316',
      'circle-radius': ['step', ['get', 'point_count'], 15, 10, 20, 30, 25],
      'circle-opacity': 0.7,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#f97316',
      'circle-stroke-opacity': 0.3,
    },
  });

  map.addLayer({
    id: 'flares-cluster-count',
    type: 'symbol',
    source: 'flares-data',
    filter: ['has', 'point_count'],
    layout: {
      'text-field': '{point_count_abbreviated}',
      'text-size': 12,
    },
    paint: {
      'text-color': '#ffffff',
    },
  });

  map.addLayer({
    id: 'flares-circles',
    type: 'circle',
    source: 'flares-data',
    filter: ['!', ['has', 'point_count']],
    paint: {
      'circle-color': '#f97316',
      'circle-radius': 6,
      'circle-opacity': 0.8,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-opacity': 0.4,
    },
  });
}

function addRenewablesLayer(map: maplibregl.Map, data: FeatureCollection | null) {
  map.addSource('renewables-data', {
    type: 'geojson',
    data: data ?? { type: 'FeatureCollection', features: [] },
  });

  map.addLayer({
    id: 'wind-circles',
    type: 'circle',
    source: 'renewables-data',
    filter: ['==', ['get', 'type'], 'wind'],
    paint: {
      'circle-color': '#22d3ee',
      'circle-radius': 6,
      'circle-opacity': 0.8,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-opacity': 0.4,
    },
  });

  map.addLayer({
    id: 'solar-circles',
    type: 'circle',
    source: 'renewables-data',
    filter: ['==', ['get', 'type'], 'solar'],
    paint: {
      'circle-color': '#facc15',
      'circle-radius': 6,
      'circle-opacity': 0.8,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-opacity': 0.4,
    },
  });
}

function addLMOPLayer(map: maplibregl.Map, data: FeatureCollection | null) {
  map.addSource('lmop-data', {
    type: 'geojson',
    data: data ?? { type: 'FeatureCollection', features: [] },
  });

  map.addLayer({
    id: 'lmop-circles',
    type: 'circle',
    source: 'lmop-data',
    paint: {
      'circle-color': '#a3e635',
      'circle-radius': 6,
      'circle-opacity': 0.8,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-opacity': 0.4,
    },
  });
}

function addDataCenterLayer(map: maplibregl.Map, data: FeatureCollection | null) {
  map.addSource('dc-data', {
    type: 'geojson',
    data: data ?? { type: 'FeatureCollection', features: [] },
  });

  map.addLayer({
    id: 'dc-pulse',
    type: 'circle',
    source: 'dc-data',
    paint: {
      'circle-color': '#f472b6',
      'circle-radius': 12,
      'circle-opacity': 0.2,
    },
  });

  map.addLayer({
    id: 'dc-circles',
    type: 'circle',
    source: 'dc-data',
    paint: {
      'circle-color': '#f472b6',
      'circle-radius': 6,
      'circle-opacity': 0.9,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-opacity': 0.5,
    },
  });
}

function addConnectionLineSources(map: maplibregl.Map) {
  map.addSource('fiber-connection', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  });

  map.addLayer({
    id: 'fiber-connection-line',
    type: 'line',
    source: 'fiber-connection',
    paint: {
      'line-color': '#38bdf8',
      'line-width': 2,
      'line-dasharray': [4, 4],
      'line-opacity': 0.9,
    },
  });

  map.addSource('dc-connection', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  });

  map.addLayer({
    id: 'dc-connection-line',
    type: 'line',
    source: 'dc-connection',
    paint: {
      'line-color': '#f472b6',
      'line-width': 2,
      'line-dasharray': [4, 4],
      'line-opacity': 0.9,
    },
  });
}

function drawConnectionLines(
  map: maplibregl.Map,
  from: [number, number],
  fiberPoint: [number, number],
  dcPoint: [number, number]
) {
  const fiberSource = map.getSource('fiber-connection') as maplibregl.GeoJSONSource | undefined;
  const dcSource = map.getSource('dc-connection') as maplibregl.GeoJSONSource | undefined;

  if (fiberSource) {
    fiberSource.setData({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry: { type: 'LineString', coordinates: [from, fiberPoint] },
        },
      ],
    });
  }

  if (dcSource) {
    dcSource.setData({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry: { type: 'LineString', coordinates: [from, dcPoint] },
        },
      ],
    });
  }
}

function clearConnectionLines(map: maplibregl.Map) {
  const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
  const fiberSource = map.getSource('fiber-connection') as maplibregl.GeoJSONSource | undefined;
  const dcSource = map.getSource('dc-connection') as maplibregl.GeoJSONSource | undefined;
  if (fiberSource) fiberSource.setData(empty);
  if (dcSource) dcSource.setData(empty);
}
