const LEGEND_ITEMS = [
  { label: 'Flare Gas', color: 'var(--energy-flare)' },
  { label: 'Wind', color: 'var(--energy-wind)' },
  { label: 'Solar', color: 'var(--energy-solar)' },
  { label: 'Landfill Methane', color: 'var(--energy-methane)' },
  { label: 'Fiber Backbone', color: 'var(--fiber-color)' },
  { label: 'Data Center', color: 'var(--dc-color)' },
];

export function Legend() {
  return (
    <div className="absolute bottom-6 left-4 z-10 bg-[var(--panel-bg)]/90 border border-[var(--panel-border)] rounded-lg p-3 backdrop-blur-sm">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {LEGEND_ITEMS.map((item) => (
          <div key={item.label} className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: item.color }}
            />
            {item.label}
          </div>
        ))}
      </div>
    </div>
  );
}
