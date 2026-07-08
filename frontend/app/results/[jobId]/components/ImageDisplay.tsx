import LayerStack from "./LayerStack";
import InspectLoupe, { type PaletteEntry } from "./InspectLoupe";
import { type CompareMode } from "../lib/manifest";

// ── Image display with comparison modes ───────────────────────────────────────
export default function ImageDisplay({
  compareMode,
  analysisUrl,
  activeAssets,
  referenceUrl,
  opacity,
  imageWidth,
  imageHeight,
  title,
  palette,
}: {
  compareMode:   CompareMode;
  analysisUrl?:  string;
  activeAssets:  string[];
  referenceUrl:  string;
  opacity:       number;
  imageWidth?:   number;
  imageHeight?:  number;
  title:         string;
  palette?:      PaletteEntry[];
}) {
  // Determine what to show in the "analysis" slot
  // If a classic page is selected, show it as a single image; otherwise show the layer stack
  const hasClassic = Boolean(analysisUrl);

  if (compareMode === "reference") {
    return (
      <div>
        <p className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>Reference photo</p>
        <InspectLoupe imageUrl={referenceUrl} palette={palette} alt="Reference" />
      </div>
    );
  }

  if (compareMode === "side_by_side") {
    return (
      <div>
        <p className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>{title} · Reference</p>
        <div className="flex gap-2">
          <div className="flex-1">
            {hasClassic
              ? <img src={analysisUrl} alt="Analysis" className="w-full rounded-xl object-contain max-h-[480px]" />
              : <LayerStack assets={activeAssets} imageWidth={imageWidth} imageHeight={imageHeight} maxHeight={480} />
            }
          </div>
          <img src={referenceUrl} alt="Reference" className="flex-1 rounded-xl object-contain max-h-[480px]" />
        </div>
      </div>
    );
  }

  if (compareMode === "overlay") {
    return (
      <div>
        <p className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>{title} · overlay at {Math.round(opacity * 100)}%</p>
        <div className="relative rounded-xl overflow-hidden" style={{ maxHeight: 520 }}>
          <img src={referenceUrl} alt="Reference" className="w-full object-contain" />
          <div className="absolute inset-0 w-full h-full" style={{ opacity }}>
            {hasClassic
              ? <img src={analysisUrl} alt="Analysis" className="w-full h-full object-contain" />
              : <LayerStack assets={activeAssets} imageWidth={imageWidth} imageHeight={imageHeight} maxHeight={520} />
            }
          </div>
        </div>
      </div>
    );
  }

  // default: "analysis"
  if (!hasClassic && activeAssets.length === 0) {
    return (
      <div className="rounded-xl flex items-center justify-center" style={{ minHeight: 300, background: "var(--surface)" }}>
        <p style={{ color: "var(--text-dim)" }}>No layers selected — enable at least one above</p>
      </div>
    );
  }

  return (
    <div>
      {title && <p className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>{title}</p>}
      {hasClassic
        ? <img src={analysisUrl} alt={title || "Analysis"} className="w-full rounded-xl object-contain max-h-[520px]" />
        : <LayerStack assets={activeAssets} imageWidth={imageWidth} imageHeight={imageHeight} maxHeight={520} />
      }
    </div>
  );
}
