"use client";
// Real image workspace (Phase 2): OpenSeadragon zoom/pan with aligned overlay
// images, fit / 100% / flip / minimap controls, and click-to-inspect regions
// resolved against the existing merge-tree hierarchy — pixel → region id via
// the RGB-encoded level label map, then regions.json for the metadata.
import { useEffect, useRef, useState } from "react";
import OpenSeadragon from "openseadragon";
import type { Manifest } from "../lib/manifest";

type RegionInfo = {
  id: number; scale: string; area: number; centroid: [number, number];
  mean_rgb: [number, number, number]; value_zone: number;
  colour_family_id: number; importance: number; parent_id: number | null;
};

type Props = {
  referenceUrl: string;
  overlays: string[];        // already-ordered overlay image URLs
  opacity: number;           // overlay opacity 0..1
  imageWidth?: number;
  imageHeight?: number;
  labelMapUrl?: string;      // RGB-encoded region ids for the current level
  regionsUrl?: string;       // regions.json for this job
  manifest?: Manifest | null;
};

export default function Viewer({
  referenceUrl, overlays, opacity, imageWidth, imageHeight,
  labelMapUrl, regionsUrl, manifest,
}: Props) {
  const hostRef   = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null);
  const labelData = useRef<{ url: string; data: ImageData } | null>(null);
  const regions   = useRef<Map<number, RegionInfo> | null>(null);
  const [picked, setPicked] = useState<RegionInfo | null>(null);
  const [flip, setFlip] = useState(false);
  // OSD v6 creates its drawer asynchronously; TiledImage construction asserts
  // on it, so overlay adds must wait until the drawer AND base image exist.
  const [ready, setReady] = useState(false);

  // ── Viewer lifecycle ────────────────────────────────────────────────────
  useEffect(() => {
    if (!hostRef.current || !referenceUrl) return;
    const viewer = OpenSeadragon({
      element: hostRef.current,
      tileSources: { type: "image", url: referenceUrl },
      crossOriginPolicy: "Anonymous",
      showNavigator: true,
      navigatorPosition: "BOTTOM_RIGHT",
      showNavigationControl: false,   // we render our own control row
      gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
      maxZoomPixelRatio: 8,
      visibilityRatio: 0.6,
      animationTime: 0.4,
      prefixUrl: "",                  // no default button images needed
    });
    viewerRef.current = viewer;

    viewer.addHandler("canvas-click", (e) => {
      if (!e.quick) return;
      const img = viewer.viewport.viewerElementToImageCoordinates(e.position);
      pickRegion(Math.round(img.x), Math.round(img.y));
    });

    setReady(false);
    let cancelled = false;
    const poll = () => {
      if (cancelled) return;
      if (viewer.drawer && viewer.world.getItemCount() > 0) setReady(true);
      else setTimeout(poll, 60);
    };
    viewer.addOnceHandler("open", poll);
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as { __osdViewer?: OpenSeadragon.Viewer }).__osdViewer = viewer;
    }

    // React StrictMode double-mounts effects in dev: the first viewer is
    // destroyed while its async image loads are still resolving, which would
    // assert inside OSD. Cancel first, then destroy.
    return () => { cancelled = true; viewerRef.current = null; viewer.destroy(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [referenceUrl]);

  // ── Overlay images track the active layer set ───────────────────────────
  // join(): the parent rebuilds the overlays array every render; keying the
  // effect on the joined string stops pointless remove/re-add churn.
  const overlayKey = overlays.join("|");
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer?.world || !viewer.drawer || !ready) return;
    while (viewer.world.getItemCount() > 1) {
      viewer.world.removeItem(viewer.world.getItemAt(1));
    }
    overlays.forEach(url => {
      viewer.addTiledImage({
        tileSource: { type: "image", url }, opacity,
        // The viewer may be torn down (mode switch, StrictMode) while this
        // image is still loading — swallow the resulting error.
        error: () => {},
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlayKey, ready]);

  // Opacity live-updates without re-adding images.
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer?.world) return;
    for (let i = 1; i < viewer.world.getItemCount(); i++) {
      viewer.world.getItemAt(i).setOpacity(opacity);
    }
  }, [opacity]);

  // ── Region lookup data (lazy) ───────────────────────────────────────────
  async function ensureLookups(): Promise<boolean> {
    if (!labelMapUrl || !regionsUrl) return false;
    try {
      if (!regions.current) {
        const res = await fetch(regionsUrl);
        if (!res.ok) return false;
        const list: RegionInfo[] = await res.json();
        regions.current = new Map(list.map(r => [r.id, r]));
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
      }
      return true;
    } catch { return false; }
  }

  async function pickRegion(x: number, y: number) {
    if (!(await ensureLookups()) || !labelData.current || !regions.current) return;
    const { data } = labelData.current;
    // The label map shares the analysis pixel grid; the reference may be the
    // full-resolution original — scale coordinates across (§21.D).
    const sx = imageWidth ? data.width / imageWidth : 1;
    const sy = imageHeight ? data.height / imageHeight : 1;
    const px = Math.min(data.width - 1, Math.max(0, Math.round(x * sx)));
    const py = Math.min(data.height - 1, Math.max(0, Math.round(y * sy)));
    const o = (py * data.width + px) * 4;
    const id = data.data[o] + (data.data[o + 1] << 8) - 1;   // 0 encodes "none"
    setPicked(id >= 0 ? regions.current.get(id) ?? null : null);
  }

  // ── Controls ────────────────────────────────────────────────────────────
  const vp = () => viewerRef.current?.viewport;
  const fitView   = () => vp()?.goHome();
  const actualPx  = () => { const v = vp(); if (v) v.zoomTo(v.imageToViewportZoom(1)); };
  const zoomBy    = (f: number) => vp()?.zoomBy(f);
  const doFlip    = () => { const v = vp(); if (v) { v.setFlip(!flip); setFlip(!flip); } };

  const zoneLabel = (zid: number) =>
    manifest?.value_zones?.find(z => z.id === zid)?.label ?? `zone ${zid}`;
  const familyName = (fid: number) => {
    const fams = (manifest?.colour_families ?? []) as { id?: number; name?: string }[];
    return fams.find(f => f?.id === fid)?.name ?? null;
  };
  const areaPct = (r: RegionInfo) =>
    imageWidth && imageHeight ? ((100 * r.area) / (imageWidth * imageHeight)).toFixed(1) : null;

  const btn: React.CSSProperties = {
    padding: "5px 12px", fontSize: 12, borderRadius: 8, cursor: "pointer",
    background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)",
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center gap-1.5 mb-2 flex-wrap">
        <button style={btn} onClick={fitView}>Fit</button>
        <button style={btn} onClick={actualPx}>100%</button>
        <button style={btn} onClick={() => zoomBy(1.4)}>+</button>
        <button style={btn} onClick={() => zoomBy(1 / 1.4)}>−</button>
        <button style={{ ...btn, ...(flip ? { background: "var(--accent)", color: "var(--paper)" } : {}) }}
                onClick={doFlip}>Flip</button>
        {labelMapUrl && (
          <span className="text-xs ml-2" style={{ color: "var(--text-dim)" }}>
            Click a region to inspect it
          </span>
        )}
      </div>

      <div className="relative flex-1 min-h-0 rounded-xl overflow-hidden"
           style={{ background: "var(--surface-2)", border: "1px solid var(--border)", minHeight: 320 }}>
        <div ref={hostRef} className="absolute inset-0" />

        {picked && (
          <div className="absolute left-3 bottom-3 p-3 rounded-xl text-xs"
               style={{ background: "var(--paper)", border: "1px solid var(--border-strong)",
                        boxShadow: "0 10px 30px rgba(63,48,28,0.18)", maxWidth: 240, zIndex: 10 }}>
            <div className="flex items-center gap-2 mb-1.5">
              <span style={{ width: 16, height: 16, borderRadius: 4, display: "inline-block",
                             background: `rgb(${picked.mean_rgb.join(",")})`,
                             border: "1px solid var(--border)" }} />
              <span className="font-medium" style={{ color: "var(--ink)" }}>
                Region #{picked.id}
              </span>
              <button onClick={() => setPicked(null)}
                      style={{ marginLeft: "auto", background: "none", border: "none",
                               cursor: "pointer", color: "var(--text-dim)" }}>✕</button>
            </div>
            <p style={{ color: "var(--text)" }}>Value family: {zoneLabel(picked.value_zone)}</p>
            {familyName(picked.colour_family_id) && (
              <p style={{ color: "var(--text)" }}>Colour family: {familyName(picked.colour_family_id)}</p>
            )}
            {areaPct(picked) && (
              <p style={{ color: "var(--text-dim)" }}>≈{areaPct(picked)}% of the image</p>
            )}
            {picked.parent_id != null && (
              <p style={{ color: "var(--text-dim)" }}>
                Part of mass #{picked.parent_id} at the simpler level
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
