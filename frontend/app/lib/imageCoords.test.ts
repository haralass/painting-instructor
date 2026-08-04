// Coordinate round-trip tests (Phase 2 §3): fit, 100%, deep zoom, pan,
// resized workspace, fullscreen and mirrored view.
import { describe, expect, it } from "vitest";
import {
  BBox, Pt, ViewState, bboxToCropRect, imageToViewport, normalizedToPixel,
  pixelToNormalized, rescalePoint, unmirrorBBox, viewportToImage,
} from "./imageCoords";

const IMG = { imageWidth: 4032, imageHeight: 3024 };

// Named viewport situations from the spec.
const VIEWS: Record<string, ViewState> = {
  fit:        { originX: 0,    originY: 62,   scale: 1280 / 4032, mirrored: false, ...IMG },
  hundred:    { originX: -900, originY: -400, scale: 1,           mirrored: false, ...IMG },
  deepZoom:   { originX: -20000, originY: -18000, scale: 6.5,     mirrored: false, ...IMG },
  panned:     { originX: 314.2, originY: -777.7, scale: 0.73,     mirrored: false, ...IMG },
  resized:    { originX: 12,   originY: 3,    scale: 390 / 4032,  mirrored: false, ...IMG },
  fullscreen: { originX: 0,    originY: 129,  scale: 2560 / 4032, mirrored: false, ...IMG },
  mirrored:   { originX: 40,   originY: 62,   scale: 0.31,        mirrored: true,  ...IMG },
  mirroredZoom: { originX: -5000, originY: -900, scale: 3.2,      mirrored: true,  ...IMG },
};

const Pts: Pt[] = [
  { x: 0, y: 0 }, { x: 4031, y: 3023 }, { x: 2016, y: 1512 }, { x: 17.25, y: 2900.5 },
];

describe("viewport↔image round-trip", () => {
  for (const [name, view] of Object.entries(VIEWS)) {
    it(`survives ${name} view`, () => {
      for (const p of Pts) {
        const back = viewportToImage(imageToViewport(p, view), view);
        expect(back.x).toBeCloseTo(p.x, 6);
        expect(back.y).toBeCloseTo(p.y, 6);
      }
    });
  }

  it("mirrors around the vertical axis", () => {
    const v = VIEWS.mirrored;
    const left = imageToViewport({ x: 0, y: 10 }, v);
    const right = imageToViewport({ x: IMG.imageWidth, y: 10 }, v);
    expect(left.x).toBeGreaterThan(right.x); // left edge renders on the right
  });
});

describe("normalized coordinates", () => {
  it("round-trips and never replaces pixel space", () => {
    for (const p of Pts) {
      const n = pixelToNormalized(p, IMG.imageWidth, IMG.imageHeight);
      expect(n.x).toBeGreaterThanOrEqual(0);
      expect(n.x).toBeLessThanOrEqual(1);
      const back = normalizedToPixel(n, IMG.imageWidth, IMG.imageHeight);
      expect(back.x).toBeCloseTo(p.x, 6);
      expect(back.y).toBeCloseTo(p.y, 6);
    }
  });
});

describe("grid rescaling (label map ↔ original)", () => {
  it("maps analysis-grid pixels onto the original and back", () => {
    const p = { x: 337, y: 450 };                       // label-map pixel
    const up = rescalePoint(p, 675, 900, 4050, 5400);   // → original
    const back = rescalePoint(up, 4050, 5400, 675, 900);
    expect(up).toEqual({ x: 2022, y: 2700 });
    expect(back.x).toBeCloseTo(p.x, 6);
    expect(back.y).toBeCloseTo(p.y, 6);
  });
});

describe("crop rects for local analysis", () => {
  it("clamps to the original bounds and normalises negative extents", () => {
    const b: BBox = { x: -50.4, y: 2900.2, w: 300, h: 400 };
    const crop = bboxToCropRect(b, IMG.imageWidth, IMG.imageHeight);
    expect(crop).toEqual({ x: 0, y: 2900, w: 250, h: 124 });
    const neg: BBox = { x: 500, y: 500, w: -100, h: -100 };
    expect(bboxToCropRect(neg, IMG.imageWidth, IMG.imageHeight))
      .toEqual({ x: 400, y: 400, w: 100, h: 100 });
  });

  it("unmirrors a bbox drawn in mirrored view", () => {
    const b: BBox = { x: 100, y: 40, w: 300, h: 200 };
    const un = unmirrorBBox(b, 1000);
    expect(un).toEqual({ x: 600, y: 40, w: 300, h: 200 });
    expect(unmirrorBBox(un, 1000)).toEqual(b); // involution
  });
});
