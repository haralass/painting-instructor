// The ONE image-space coordinate system (Phase 2 §3).
//
// Authoritative space: ORIGINAL image pixels — x∈[0,W), y∈[0,H) of the
// untouched reference. Every mask, region, overlay, selection, crop and
// progress upload maps through here; no component may hand-roll conversions.
//
// "Viewport" here is a pure description of the visible mapping, so the same
// math (and the tests) work for fit view, 100%, deep zoom, pans, resizes,
// fullscreen and mirrored view without touching OpenSeadragon itself.

export type Pt = { x: number; y: number };
export type BBox = { x: number; y: number; w: number; h: number };

/** Pure description of how the original image is currently mapped onto the
 *  screen: top-left of the image in element pixels, scale (element px per
 *  image px) and whether the view is mirrored horizontally. */
export type ViewState = {
  originX: number;   // element-px x of image (0,0) when not mirrored
  originY: number;
  scale: number;     // element px per original-image px (>0)
  mirrored: boolean;
  imageWidth: number;
  imageHeight: number;
};

/** Element/viewer pixels → original image pixels. */
export function viewportToImage(p: Pt, v: ViewState): Pt {
  let x = (p.x - v.originX) / v.scale;
  const y = (p.y - v.originY) / v.scale;
  if (v.mirrored) x = v.imageWidth - x;
  return { x, y };
}

/** Original image pixels → element/viewer pixels. */
export function imageToViewport(p: Pt, v: ViewState): Pt {
  const ix = v.mirrored ? v.imageWidth - p.x : p.x;
  return { x: v.originX + ix * v.scale, y: v.originY + p.y * v.scale };
}

/** Original pixels → normalized [0,1] coordinates (convenience form only —
 *  never a replacement for pixel space). */
export function pixelToNormalized(p: Pt, imageWidth: number, imageHeight: number): Pt {
  return { x: p.x / imageWidth, y: p.y / imageHeight };
}

export function normalizedToPixel(p: Pt, imageWidth: number, imageHeight: number): Pt {
  return { x: p.x * imageWidth, y: p.y * imageHeight };
}

/** Map a point between two raster grids that share the same image content
 *  (e.g. analysis label map ↔ full-resolution original). */
export function rescalePoint(p: Pt, fromW: number, fromH: number, toW: number, toH: number): Pt {
  return { x: (p.x * toW) / fromW, y: (p.y * toH) / fromH };
}

/** Clamp + round a selection bbox (original-image px) to an integer crop
 *  rect inside the full-resolution original — the exact rect a local
 *  analysis request must cut from the ORIGINAL file, never from a preview. */
export function bboxToCropRect(b: BBox, imageWidth: number, imageHeight: number): BBox {
  const x0 = Math.max(0, Math.floor(Math.min(b.x, b.x + b.w)));
  const y0 = Math.max(0, Math.floor(Math.min(b.y, b.y + b.h)));
  const x1 = Math.min(imageWidth, Math.ceil(Math.max(b.x, b.x + b.w)));
  const y1 = Math.min(imageHeight, Math.ceil(Math.max(b.y, b.y + b.h)));
  return { x: x0, y: y0, w: Math.max(0, x1 - x0), h: Math.max(0, y1 - y0) };
}

/** A bbox expressed in a mirrored view, converted back to true image space. */
export function unmirrorBBox(b: BBox, imageWidth: number): BBox {
  return { x: imageWidth - b.x - b.w, y: b.y, w: b.w, h: b.h };
}
