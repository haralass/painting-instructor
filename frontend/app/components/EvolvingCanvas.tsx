"use client";
import { useMemo } from "react";

/**
 * One deterministic painting, rendered at every stage of the painting
 * process — blank canvas, sketch, notan, block-in, colour, detail — so the
 * page can show the SAME picture being painted as you scroll, exactly the
 * journey the lesson takes a learner through.
 *
 * All stages are stacked and crossfaded via opacity so a scroll-driven
 * transition never re-renders SVG mid-frame.
 */

const W = 200;
const H = 150;

const GRAPHITE = "#6b6459";
const PAPER = "#fffdf7";
const NOTAN = ["#2b251b", "#8a8272", "#f3edde"];
const WARM = ["#c96f3a", "#b4511f", "#e0b26a", "#9d2f2f", "#c9932e", "#d9a05b"];
const COOL = ["#3e5c76", "#6f7d5c", "#7d92ab", "#41504f", "#5d6b7d"];
const ALL = [...WARM, ...COOL];

function mulberry32(seed: number) {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type PaintBlob = { x: number; y: number; r: number; path: string; ci: number; warm: boolean };

function blobPath(cx: number, cy: number, r: number, rand: () => number): string {
  const n = 8;
  const pts: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const rr = r * (0.75 + rand() * 0.5);
    pts.push([cx + Math.cos(a) * rr, cy + Math.sin(a) * rr * 0.85]);
  }
  let d = `M ${(pts[0][0] + pts[n - 1][0]) / 2} ${(pts[0][1] + pts[n - 1][1]) / 2}`;
  for (let i = 0; i < n; i++) {
    const p = pts[i];
    const nx = pts[(i + 1) % n];
    d += ` Q ${p[0]} ${p[1]} ${(p[0] + nx[0]) / 2} ${(p[1] + nx[1]) / 2}`;
  }
  return d + " Z";
}

function makeBlobs(seed: number, n = 80): PaintBlob[] {
  const rand = mulberry32(seed);
  const blobs: PaintBlob[] = [];
  for (let i = 0; i < n; i++) {
    const t = i / n;
    const r = (1 - t) * (1 - t) * 52 + 5 + rand() * 8;
    const x = 10 + rand() * (W - 20);
    const y = 8 + rand() * (H - 16);
    blobs.push({
      x, y, r,
      path: blobPath(x, y, r, rand),
      ci: Math.floor(rand() * 1000),
      warm: x < W * 0.55 ? rand() < 0.75 : rand() < 0.35,
    });
  }
  return blobs;
}

export const STAGE_VISUAL_COUNT = 6;

function StageLayer({ stage, blobs, seed }: { stage: number; blobs: PaintBlob[]; seed: number }) {
  switch (stage) {
    case 0: // stretched canvas — nothing but paper and its weave
      return (
        <>
          {Array.from({ length: 9 }, (_, i) => (
            <line key={i} x1={0} y1={(i + 1) * (H / 10)} x2={W} y2={(i + 1) * (H / 10)}
                  stroke="#e4dbc7" strokeWidth={0.4} />
          ))}
        </>
      );
    case 1: // sketch — graphite contours of the big masses only
      return (
        <>
          {blobs.slice(0, 14).map((b, i) => (
            <path key={i} d={b.path} fill="none" stroke={GRAPHITE}
                  strokeWidth={i < 5 ? 1.1 : 0.6} opacity={i < 5 ? 0.8 : 0.45} />
          ))}
          <line x1={W * 0.62} y1={4} x2={W * 0.62} y2={H - 4} stroke={GRAPHITE} strokeWidth={0.35} opacity={0.3} />
          <line x1={4} y1={H * 0.38} x2={W - 4} y2={H * 0.38} stroke={GRAPHITE} strokeWidth={0.35} opacity={0.3} />
        </>
      );
    case 2: // notan — light and dark resolved before any colour
      return (
        <>
          {blobs.slice(0, 30).map((b, i) => (
            <path key={i} d={b.path} fill={NOTAN[b.ci % 3]} />
          ))}
        </>
      );
    case 3: // block-in — the few big masses, thin flat colour
      return (
        <>
          {blobs.slice(0, 9).map((b, i) => {
            const pal = b.warm ? WARM : COOL;
            return <path key={i} d={b.path} fill={pal[b.ci % pal.length]} opacity={0.85} />;
          })}
        </>
      );
    case 4: // colour modelling — temperature over the whole surface
      return (
        <>
          {blobs.slice(0, 34).map((b, i) => {
            const pal = b.warm ? WARM : COOL;
            return <path key={i} d={b.path} fill={pal[b.ci % pal.length]} />;
          })}
        </>
      );
    default: { // detail — full regions, edges found, highlights placed
      const rand = mulberry32(seed * 17 + 3);
      return (
        <>
          {blobs.slice(0, 72).map((b, i) => (
            <path key={i} d={b.path} fill={ALL[b.ci % ALL.length]} opacity={0.95} />
          ))}
          {blobs.slice(0, 6).map((b, i) => (
            <path key={`e${i}`} d={b.path} fill="none" stroke="#241f16" strokeWidth={0.5} opacity={0.35} />
          ))}
          {Array.from({ length: 7 }, (_, i) => (
            <circle key={`h${i}`} cx={14 + rand() * (W - 28)} cy={10 + rand() * (H * 0.5)}
                    r={1.1 + rand() * 1.6} fill="#fff8ec" opacity={0.9} />
          ))}
        </>
      );
    }
  }
}

export default function EvolvingCanvas({
  stage,
  seed = 7,
  className = "",
}: {
  /** 0 canvas · 1 sketch · 2 notan · 3 block-in · 4 colour · 5 detail */
  stage: number;
  seed?: number;
  className?: string;
}) {
  const blobs = useMemo(() => makeBlobs(seed), [seed]);

  return (
    <div className={className} style={{ position: "relative", width: "100%", height: "100%" }}>
      {Array.from({ length: STAGE_VISUAL_COUNT }, (_, s) => (
        <svg
          key={s}
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="xMidYMid slice"
          aria-hidden
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            opacity: s === Math.min(Math.max(stage, 0), STAGE_VISUAL_COUNT - 1) ? 1 : 0,
            transition: "opacity 0.45s ease",
          }}
        >
          <rect width={W} height={H} fill={PAPER} />
          <StageLayer stage={s} blobs={blobs} seed={seed} />
        </svg>
      ))}
    </div>
  );
}
