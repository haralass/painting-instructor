"use client";
// The real image workspace (Phase 2): OpenSeadragon zoom/pan, keyboard
// shortcuts, fullscreen, minimap, mirror; analysis overlays aligned in image
// coordinates; region hover/click/multi-selection resolved against the
// existing merge-tree hierarchy (RGB label map → regions.json); Reference /
// Overlay / Before-After split / synced Side-by-Side view modes; viewport
// state persisted per project. All geometry maps through app/lib/imageCoords
// conventions: original-image pixels are authoritative.
import { useCallback, useEffect, useRef, useState } from "react";
import OpenSeadragon from "openseadragon";
import { rescalePoint } from "../../../lib/imageCoords";
import type { Manifest } from "../lib/manifest";

export type RegionInfo = {
  id: number; scale: string; area: number; centroid: [number, number];
  bbox: [number, number, number, number];
  mean_rgb: [number, number, number]; value_zone: number;
  colour_family_id: number; importance: number; parent_id: number | null;
};

export type ViewerMode = "overlay" | "reference" | "split" | "side_by_side";

type Props = {
  jobId: string;
  referenceUrl: string;
  overlays: string[];
  opacity: number;
  mode: ViewerMode;
  imageWidth?: number;
  imageHeight?: number;
  labelMapUrl?: string;
  regionsUrl?: string;
  manifest?: Manifest | null;
  syncKey?: string;          // viewers sharing a key mirror zoom/pan
  hideControls?: boolean;    // secondary pane of side-by-side
};

// ── Cross-viewer pan/zoom sync (side-by-side) ────────────────────────────────
const syncGroups = new Map<string, Set<OpenSeadragon.Viewer>>();
function joinSync(key: string, viewer: OpenSeadragon.Viewer) {
  if (!syncGroups.has(key)) syncGroups.set(key, new Set());
  const group = syncGroups.get(key)!;
  group.add(viewer);
  let applying = false;
  const propagate = () => {
    if (applying) return;
    for (const other of group) {
      if (other === viewer) continue;
      applying = true;
      try {
        other.viewport.zoomTo(viewer.viewport.getZoom(), undefined, true);
        other.viewport.panTo(viewer.viewport.getCenter(), true);
      } finally { applying = false; }
    }
  };
  viewer.addHandler("zoom", propagate);
  viewer.addHandler("pan", propagate);
  return () => { group.delete(viewer); if (!group.size) syncGroups.delete(key); };
}

const viewKey = (jobId: string) => `pi:viewport:${jobId}`;

export default function Viewer({
  jobId, referenceUrl, overlays, opacity, mode, imageWidth, imageHeight,
  labelMapUrl, regionsUrl, manifest, syncKey, hideControls,
}: Props) {
  const hostRef    = useRef<HTMLDivElement>(null);
  const wrapRef    = useRef<HTMLDivElement>(null);
  const viewerRef  = useRef<OpenSeadragon.Viewer | null>(null);
  const labelData  = useRef<{ url: string; data: ImageData } | null>(null);
  const regions    = useRef<Map<number, RegionInfo> | null>(null);
  const children   = useRef<Map<number, number[]>>(new Map());
  const selOverlay = useRef<HTMLImageElement | null>(null);
  const hovOverlay = useRef<HTMLImageElement | null>(null);
  const hoverId    = useRef<number>(-1);
  const modeRef    = useRef(mode);
  modeRef.current  = mode;

  const [ready, setReady]       = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [picked, setPicked]     = useState<RegionInfo | null>(null);
  const [flip, setFlip]         = useState(false);
  const [showNav, setShowNav]   = useState(true);
  const [split, setSplit]       = useState(0.5);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;

  const overlaysActive = mode === "overlay" || mode === "split";
  const effOpacity = mode === "split" ? 1 : opacity;

  // ── Viewer lifecycle ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!hostRef.current || !referenceUrl) return;
    const viewer = OpenSeadragon({
      element: hostRef.current,
      tileSources: { type: "image", url: referenceUrl },
      crossOriginPolicy: "Anonymous",
      showNavigator: true,
      navigatorPosition: "BOTTOM_RIGHT",
      showNavigationControl: false,
      gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
      gestureSettingsTouch: { pinchToZoom: true, flickEnabled: true },
      maxZoomPixelRatio: 8,
      visibilityRatio: 0.6,
      animationTime: 0.4,
      prefixUrl: "",
    });
    viewerRef.current = viewer;

    viewer.addHandler("canvas-click", (e) => {
      if (!e.quick) return;
      const img = viewer.viewport.viewerElementToImageCoordinates(e.position);
      void handleClick(Math.round(img.x), Math.round(img.y),
                       (e.originalEvent as MouseEvent)?.shiftKey === true);
    });

    // Hover highlight — throttled decode along mouse moves.
    let lastMove = 0;
    const onMove = (ev: MouseEvent) => {
      const now = performance.now();
      if (now - lastMove < 70) return;
      lastMove = now;
      const r = viewer.element.getBoundingClientRect();
      const img = viewer.viewport.viewerElementToImageCoordinates(
        new OpenSeadragon.Point(ev.clientX - r.left, ev.clientY - r.top));
      void handleHover(Math.round(img.x), Math.round(img.y));
    };
    viewer.element.addEventListener("mousemove", onMove);
    viewer.element.addEventListener("mouseleave", () => void handleHover(-1, -1));

    // Persist / restore viewport per project.
    viewer.addHandler("animation-finish", () => {
      try {
        localStorage.setItem(viewKey(jobId), JSON.stringify({
          zoom: viewer.viewport.getZoom(),
          cx: viewer.viewport.getCenter().x, cy: viewer.viewport.getCenter().y,
        }));
      } catch { /* private mode */ }
    });

    setReady(false);
    let cancelled = false;
    const poll = () => {
      if (cancelled) return;
      if (viewer.drawer && viewer.world.getItemCount() > 0) {
        try {
          const saved = JSON.parse(localStorage.getItem(viewKey(jobId)) ?? "null");
          if (saved?.zoom) {
            viewer.viewport.zoomTo(saved.zoom, undefined, true);
            viewer.viewport.panTo(new OpenSeadragon.Point(saved.cx, saved.cy), true);
          }
        } catch { /* corrupt state — fit view is fine */ }
        setReady(true);
      } else setTimeout(poll, 60);
    };
    viewer.addOnceHandler("open", poll);

    const leaveSync = syncKey ? joinSync(syncKey, viewer) : undefined;
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as { __osdViewer?: OpenSeadragon.Viewer }).__osdViewer = viewer;
    }
    const host = hostRef.current;
    return () => {
      cancelled = true; leaveSync?.();
      viewer.element.removeEventListener("mousemove", onMove);
      viewerRef.current = null; viewer.destroy();
      // OSD's destroy() leaves its container div behind — clear it, or every
      // remount (mode switch, StrictMode) stacks another dead container.
      if (host) host.innerHTML = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [referenceUrl, syncKey]);

  // ── Keyboard shortcuts (primary pane only) ────────────────────────────────
  useEffect(() => {
    if (hideControls) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || t?.isContentEditable) return;
      const v = viewerRef.current; if (!v) return;
      switch (e.key) {
        case "+": case "=": v.viewport.zoomBy(1.3); break;
        case "-": v.viewport.zoomBy(1 / 1.3); break;
        case "0": v.viewport.goHome(); break;
        case "1": v.viewport.zoomTo(v.viewport.imageToViewportZoom(1)); break;
        case "f": case "F": v.setFullScreen(!v.isFullPage()); break;
        case "h": case "H": doFlip(); break;
        case "Escape": clearSelection(); break;
        default: return;
      }
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hideControls, flip]);

  // ── Analysis overlays (mode-aware, with split clipping) ───────────────────
  const overlayKey = overlays.join("|") + `|${overlaysActive}`;
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer?.world || !viewer.drawer || !ready) return;
    while (viewer.world.getItemCount() > 1) viewer.world.removeItem(viewer.world.getItemAt(1));
    if (!overlaysActive) return;
    overlays.forEach(url => {
      viewer.addTiledImage({
        tileSource: { type: "image", url }, opacity: effOpacity, error: () => {},
        success: (ev: unknown) => {
          const item = (ev as { item?: OpenSeadragon.TiledImage }).item;
          if (item && modeRef.current === "split") applyClip(item);
        },
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlayKey, ready]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer?.world) return;
    for (let i = 1; i < viewer.world.getItemCount(); i++) {
      const item = viewer.world.getItemAt(i);
      item.setOpacity(effOpacity);
      if (mode === "split") applyClip(item); else item.setClip(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effOpacity, split, mode]);

  function applyClip(item: OpenSeadragon.TiledImage) {
    // Before/After: analysis visible left of the divider, reference right.
    const s = item.getContentSize();
    item.setClip(new OpenSeadragon.Rect(0, 0, s.x * split, s.y));
  }

  // ── Region lookups ────────────────────────────────────────────────────────
  const ensureLookups = useCallback(async (): Promise<boolean> => {
    if (!labelMapUrl || !regionsUrl) return false;
    try {
      if (!regions.current) {
        const res = await fetch(regionsUrl);
        if (!res.ok) return false;
        const list: RegionInfo[] = await res.json();
        regions.current = new Map(list.map(r => [r.id, r]));
        children.current = new Map();
        for (const r of list) {
          if (r.parent_id == null) continue;
          if (!children.current.has(r.parent_id)) children.current.set(r.parent_id, []);
          children.current.get(r.parent_id)!.push(r.id);
        }
      }
      if (!labelData.current || labelData.current.url !== labelMapUrl) {
        const res = await fetch(labelMapUrl);
        if (!res.ok) return false;
        const bmp = await createImageBitmap(await res.blob());
        const cv = document.createElement("canvas");
        cv.width = bmp.width; cv.height = bmp.height;
        const ctx = cv.getContext("2d")!;
        ctx.drawImage(bmp, 0, 0);
        labelData.current = { url: labelMapUrl, data: ctx.getImageData(0, 0, cv.width, cv.height) };
        renderMask(selectedRef.current, selOverlay, [180, 81, 31, 95]);
      }
      return true;
    } catch { return false; }
  }, [labelMapUrl, regionsUrl]);

  function idAt(x: number, y: number): number {
    const ld = labelData.current; if (!ld) return -1;
    const p = rescalePoint({ x, y }, imageWidth ?? ld.data.width,
                           imageHeight ?? ld.data.height, ld.data.width, ld.data.height);
    const px = Math.min(ld.data.width - 1, Math.max(0, Math.round(p.x)));
    const py = Math.min(ld.data.height - 1, Math.max(0, Math.round(p.y)));
    const o = (py * ld.data.width + px) * 4;
    return ld.data.data[o] + (ld.data.data[o + 1] << 8) - 1;
  }

  // Region ids → tinted RGBA mask, mounted as an OSD overlay so it scales
  // and stays aligned through zoom/pan/resize/fullscreen automatically.
  function renderMask(ids: number[], slot: typeof selOverlay, rgba: [number, number, number, number]) {
    const viewer = viewerRef.current, ld = labelData.current;
    if (!viewer || !ld) return;
    if (slot.current) { viewer.removeOverlay(slot.current); slot.current = null; }
    if (!ids.length) return;
    const want = new Set(ids);
    const cv = document.createElement("canvas");
    cv.width = ld.data.width; cv.height = ld.data.height;
    const ctx = cv.getContext("2d")!;
    const out = ctx.createImageData(cv.width, cv.height);
    const src = ld.data.data, dst = out.data;
    for (let i = 0; i < src.length; i += 4) {
      if (want.has(src[i] + (src[i + 1] << 8) - 1)) {
        dst[i] = rgba[0]; dst[i + 1] = rgba[1]; dst[i + 2] = rgba[2]; dst[i + 3] = rgba[3];
      }
    }
    ctx.putImageData(out, 0, 0);
    const img = document.createElement("img");
    img.src = cv.toDataURL();
    img.style.width = "100%"; img.style.height = "100%";
    img.style.imageRendering = "pixelated";
    const aspect = (imageHeight ?? cv.height) / (imageWidth ?? cv.width);
    viewer.addOverlay({ element: img, location: new OpenSeadragon.Rect(0, 0, 1, aspect) });
    slot.current = img;
  }

  async function handleHover(x: number, y: number) {
    if (!(await ensureLookups())) return;
    const id = x < 0 ? -1 : idAt(x, y);
    if (id === hoverId.current) return;
    hoverId.current = id;
    renderMask(id >= 0 && !selectedRef.current.includes(id) ? [id] : [], hovOverlay, [62, 92, 118, 60]);
  }

  async function handleClick(x: number, y: number, additive: boolean) {
    if (!(await ensureLookups()) || !regions.current) return;
    const id = idAt(x, y);
    if (id < 0) { if (!additive) clearSelection(); return; }
    let next: number[];
    if (additive) {
      next = selectedRef.current.includes(id)
        ? selectedRef.current.filter(s => s !== id)   // shift-click again = subtract
        : [...selectedRef.current, id];
    } else {
      next = selectedRef.current.length === 1 && selectedRef.current[0] === id ? [] : [id];
    }
    applySelection(next);
  }

  function applySelection(ids: number[]) {
    setSelected(ids);
    selectedRef.current = ids;
    setPicked(ids.length ? regions.current?.get(ids[ids.length - 1]) ?? null : null);
    renderMask(ids, selOverlay, [180, 81, 31, 95]);
  }

  function clearSelection() { applySelection([]); }
  function selectRegion(id: number) {
    if (regions.current?.has(id)) applySelection([id]);
  }

  // ── Controls ──────────────────────────────────────────────────────────────
  const vp = () => viewerRef.current?.viewport;
  const doFlip = () => {
    const v = vp(); if (!v) return;
    const f = !v.getFlip(); v.setFlip(f); setFlip(f);
  };
  const resetView = () => {
    const v = viewerRef.current; if (!v) return;
    if (v.viewport.getFlip()) { v.viewport.setFlip(false); setFlip(false); }
    clearSelection(); v.viewport.goHome();
    try { localStorage.removeItem(viewKey(jobId)); } catch { /* ok */ }
  };
  const toggleNav = () => {
    const v = viewerRef.current; if (!v?.navigator) return;
    const el = v.navigator.element as HTMLElement;
    el.style.display = showNav ? "none" : "";
    setShowNav(!showNav);
  };

  const zoneLabel = (zid: number) =>
    manifest?.value_zones?.find(z => z.id === zid)?.label ?? `zone ${zid}`;
  const familyName = (fid: number) => {
    const fams = (manifest?.colour_families ?? []) as { id?: number; name?: string }[];
    return fams.find(f => f?.id === fid)?.name ?? null;
  };
  const areaPct = (r: RegionInfo) => {
    const ld = labelData.current;
    return ld ? ((100 * r.area) / (ld.data.width * ld.data.height)).toFixed(1) : null;
  };
  // Region bbox in ORIGINAL-image pixels (authoritative space).
  const bboxOriginal = (r: RegionInfo): string | null => {
    const ld = labelData.current;
    if (!ld || !imageWidth || !imageHeight) return null;
    const a = rescalePoint({ x: r.bbox[0], y: r.bbox[1] }, ld.data.width, ld.data.height, imageWidth, imageHeight);
    const b = rescalePoint({ x: r.bbox[2], y: r.bbox[3] }, ld.data.width, ld.data.height, imageWidth, imageHeight);
    return `${Math.round(a.x)},${Math.round(a.y)} → ${Math.round(b.x)},${Math.round(b.y)} px`;
  };

  const btn: React.CSSProperties = {
    padding: "5px 11px", fontSize: 12, borderRadius: 8, cursor: "pointer",
    background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)",
  };
  const btnOn: React.CSSProperties = { ...btn, background: "var(--accent)", color: "var(--paper)" };
  const kids = picked ? children.current.get(picked.id) ?? [] : [];
  const parent = picked?.parent_id != null ? regions.current?.get(picked.parent_id) : null;

  return (
    <div ref={wrapRef} className="flex flex-col h-full min-h-0">
      {!hideControls && (
        <div className="flex items-center gap-1.5 mb-2 flex-wrap">
          <button style={btn} title="Zoom in (+)"  onClick={() => vp()?.zoomBy(1.3)}>+</button>
          <button style={btn} title="Zoom out (−)" onClick={() => vp()?.zoomBy(1 / 1.3)}>−</button>
          <button style={btn} title="Fit (0)"      onClick={() => vp()?.goHome()}>Fit</button>
          <button style={btn} title="Actual pixels (1)"
                  onClick={() => { const v = vp(); if (v) v.zoomTo(v.imageToViewportZoom(1)); }}>100%</button>
          <button style={btn} title="Reset view"   onClick={resetView}>Reset</button>
          <button style={flip ? btnOn : btn} title="Mirror (H)" onClick={doFlip}>Mirror</button>
          <button style={btn} title="Fullscreen (F)"
                  onClick={() => { const v = viewerRef.current; if (v) v.setFullScreen(!v.isFullPage()); }}>⛶</button>
          <button style={showNav ? btnOn : btn} title="Navigator" onClick={toggleNav}>Map</button>
          {mode === "split" && (
            <label className="flex items-center gap-2 ml-2 text-xs" style={{ color: "var(--text-dim)" }}>
              Before/After
              <input type="range" min={0} max={1} step={0.01} value={split}
                     onChange={e => setSplit(Number(e.target.value))} style={{ width: 120 }} />
            </label>
          )}
          {labelMapUrl && (
            <span className="text-xs ml-auto" style={{ color: "var(--text-dim)" }}>
              Click: select · Shift-click: add/remove · Esc: clear
            </span>
          )}
        </div>
      )}

      <div className="relative flex-1 min-h-0 rounded-xl overflow-hidden"
           style={{ background: "var(--surface-2)", border: "1px solid var(--border)", minHeight: 320 }}>
        <div ref={hostRef} className="absolute inset-0" />

        {picked && !hideControls && (
          <div className="absolute left-3 bottom-3 p-3 rounded-xl text-xs"
               style={{ background: "var(--paper)", border: "1px solid var(--border-strong)",
                        boxShadow: "0 10px 30px rgba(63,48,28,0.18)", maxWidth: 260, zIndex: 10 }}>
            <div className="flex items-center gap-2 mb-1.5">
              <span style={{ width: 16, height: 16, borderRadius: 4, display: "inline-block",
                             background: `rgb(${picked.mean_rgb.join(",")})`,
                             border: "1px solid var(--border)" }} />
              <span className="font-medium" style={{ color: "var(--ink)" }}>
                Region #{picked.id}{selected.length > 1 ? ` (+${selected.length - 1} more)` : ""}
              </span>
              <button onClick={clearSelection}
                      style={{ marginLeft: "auto", background: "none", border: "none",
                               cursor: "pointer", color: "var(--text-dim)" }}>✕</button>
            </div>
            {/* Breadcrumb through the hierarchy */}
            <p className="mb-1" style={{ color: "var(--text-dim)" }}>
              Full image
              {parent && <> → <button onClick={() => selectRegion(parent.id)}
                          style={{ background: "none", border: "none", padding: 0, cursor: "pointer",
                                   color: "var(--accent)" }}>mass #{parent.id}</button></>}
              {" → "}<span style={{ color: "var(--ink)" }}>#{picked.id}</span>
            </p>
            <p style={{ color: "var(--text)" }}>Level: {picked.scale} · Value: {zoneLabel(picked.value_zone)}</p>
            {familyName(picked.colour_family_id) && (
              <p style={{ color: "var(--text)" }}>Colour family: {familyName(picked.colour_family_id)}</p>
            )}
            {areaPct(picked) && <p style={{ color: "var(--text-dim)" }}>≈{areaPct(picked)}% of the image</p>}
            {bboxOriginal(picked) && (
              <p style={{ color: "var(--text-dim)" }}>Bounds: {bboxOriginal(picked)}</p>
            )}
            {kids.length > 0 && (
              <p style={{ color: "var(--text-dim)" }}>
                {kids.length} sub-regions:{" "}
                {kids.slice(0, 6).map(k => (
                  <button key={k} onClick={() => selectRegion(k)}
                          style={{ background: "none", border: "none", padding: "0 3px",
                                   cursor: "pointer", color: "var(--accent)" }}>#{k}</button>
                ))}{kids.length > 6 ? "…" : ""}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
