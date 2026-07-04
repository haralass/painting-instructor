"use client";
import { useMemo } from "react";

/**
 * Deterministic generative "painting" used across the marketing sections.
 * One seeded blob field, rendered in different modes — so the level cards
 * genuinely show the SAME painting refined from 4 masses to 80 regions,
 * mirroring what the analysis pipeline does to a real photo.
 */

const WARM = ["#dca55e", "#bf5b45", "#e9ddc8", "#a4683f", "#f2c078", "#8f4632"];
const COOL = ["#7d92ab", "#8a9179", "#5d6b7d", "#41504f", "#6d7f8f"];
const ALL = [...WARM, ...COOL];
const NOTAN = ["#0d0c0a", "#7a736a", "#e9e2d6"];

const W = 200;
const H = 150;

function mulberry32(seed: number) {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type PaintBlob = {
  x: number;
  y: number;
  r: number;
  path: string;
  ci: number;
  warm: boolean;
};

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

export type ArtMode =
  | "colour" | "line" | "notan" | "temperature"
  | "palette" | "numbers" | "dots" | "light";

export default function ArtTile({
  mode,
  seed = 7,
  count = 40,
  className = "",
}: {
  mode: ArtMode;
  seed?: number;
  count?: number;
  className?: string;
}) {
  const blobs = useMemo(() => makeBlobs(seed), [seed]);
  const shown = blobs.slice(0, count);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={className}
      style={{ display: "block", width: "100%", height: "100%" }}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden
    >
      {mode === "light" ? (
        <>
          <defs>
            <radialGradient id={`lg-${seed}`} cx="0.72" cy="0.2" r="1.15">
              <stop offset="0%" stopColor="#f7d9a8" />
              <stop offset="40%" stopColor="#c98d4a" />
              <stop offset="75%" stopColor="#6d5a48" />
              <stop offset="100%" stopColor="#3d4a58" />
            </radialGradient>
          </defs>
          <rect width={W} height={H} fill={`url(#lg-${seed})`} />
          {shown.map((b, i) => (
            <path key={i} d={b.path} fill="#1a222c" opacity={0.08 + (b.x / W) * 0.14} />
          ))}
        </>
      ) : mode === "palette" ? (
        <>
          <rect width={W} height={H} fill="#14100c" />
          {ALL.slice(0, 10).map((c, i) => (
            <rect
              key={i}
              x={14 + (i % 5) * 36}
              y={20 + Math.floor(i / 5) * 60}
              width={28}
              height={44}
              rx={7}
              fill={c}
            />
          ))}
        </>
      ) : (
        <>
          <rect width={W} height={H} fill={mode === "notan" ? "#e9e2d6" : mode === "line" ? "#14100c" : "#171310"} />
          {shown.map((b, i) => {
            if (mode === "line") {
              return <path key={i} d={b.path} fill="none" stroke="#dca55e" strokeWidth={i < 5 ? 1.7 : 0.8} opacity={i < 5 ? 0.95 : 0.45} />;
            }
            if (mode === "notan") {
              return <path key={i} d={b.path} fill={NOTAN[b.ci % 3]} />;
            }
            if (mode === "temperature") {
              const pal = b.warm ? WARM : COOL;
              return <path key={i} d={b.path} fill={pal[b.ci % pal.length]} />;
            }
            if (mode === "numbers") {
              return (
                <g key={i}>
                  <path d={b.path} fill={ALL[b.ci % ALL.length]} opacity={0.6} stroke="#6b6258" strokeWidth={0.6} />
                  {i < 12 && (
                    <text x={b.x} y={b.y + 2.8} fontSize={8} fill="#f7f2e9" textAnchor="middle" fontFamily="monospace" fontWeight="bold">
                      {(b.ci % 12) + 1}
                    </text>
                  )}
                </g>
              );
            }
            if (mode === "dots") {
              if (i >= 10) return null;
              const rand = mulberry32(seed * 31 + i);
              const pts = Array.from({ length: 7 }, (_, k) => {
                const a = (k / 7) * Math.PI * 2;
                return [b.x + Math.cos(a) * b.r * (0.7 + rand() * 0.4), b.y + Math.sin(a) * b.r * 0.6 * (0.7 + rand() * 0.4)];
              });
              return (
                <g key={i}>
                  {pts.map(([px, py], k) => (
                    <circle key={k} cx={px} cy={py} r={1.6} fill="#dca55e" opacity={0.85} />
                  ))}
                </g>
              );
            }
            // colour
            return <path key={i} d={b.path} fill={ALL[b.ci % ALL.length]} opacity={0.92} />;
          })}
        </>
      )}
    </svg>
  );
}
