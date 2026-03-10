interface LayerConfig {
  id: string;
  label: string;
  color: string;
  visible: boolean;
}

interface LayerToggleProps {
  layers: LayerConfig[];
  onToggle: (layerId: string) => void;
}

export function LayerToggle({ layers, onToggle }: LayerToggleProps) {
  return (
    <div className="absolute top-4 left-4 z-10 bg-[var(--panel-bg)] border border-[var(--panel-border)] rounded-lg p-3 min-w-[180px]">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)] mb-2">
        Layers
      </h3>
      {layers.map((layer) => (
        <label
          key={layer.id}
          className="flex items-center gap-2 py-1 cursor-pointer hover:bg-white/5 px-1 rounded text-sm"
        >
          <input
            type="checkbox"
            checked={layer.visible}
            onChange={() => onToggle(layer.id)}
            className="sr-only"
          />
          <span
            className="w-3 h-3 rounded-full border-2 flex-shrink-0"
            style={{
              backgroundColor: layer.visible ? layer.color : 'transparent',
              borderColor: layer.color,
            }}
          />
          <span className={layer.visible ? 'text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}>
            {layer.label}
          </span>
        </label>
      ))}
    </div>
  );
}
