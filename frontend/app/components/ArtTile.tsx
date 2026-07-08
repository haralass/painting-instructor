"use client";
import { useMemo } from "react";

/**
 * Deterministic generative "painting" used across the marketing sections.
 * One seeded blob field, rendered in different modes — so the level cards
 * genuinely show the SAME painting refined from 4 masses to 80 regions,
 * mirroring what the analysis pipeline does to a real photo.
 */

const WARM = ["#c96f3a", "#b4511f", "#e0b26a", "#9d2f2f", "#c9932e", "#d9a05b"];
const COOL = ["#3e5c76", "#6f7d5c", "#7d92ab", "#41504f", "#5d6b7d"];
const ALL = [...WARM, ...COOL];
const NOTAN = ["#2b251b", "#8a8272", "#f3edde"];

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
  | "palette" | "numbers" | "dots" | "light"
  | "subject" | "depth" | "locallight" | "traps" | "edges" | "focus";

// Greys for the de-emphasised halves of the new study modes
const GREY = ["#a8a193", "#8a8272", "#6b6258", "#c4bcac"];

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
      ) : mode === "depth" ? (
        <>
          {/* Atmospheric perspective: pale cool distance, warm dark foreground */}
          <defs>
            <linearGradient id={`dp-${seed}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#dfe6ea" />
              <stop offset="45%" stopColor="#9fb0bd" />
              <stop offset="100%" stopColor="#f3edde" />
            </linearGradient>
          </defs>
          <rect width={W} height={H} fill={`url(#dp-${seed})`} />
          {shown.map((b, i) => {
            const far = b.y < H * 0.38, mid = b.y < H * 0.68;
            const pal = far ? ["#b9c6cf", "#a5b5c2"] : mid ? COOL : WARM;
            return <path key={i} d={b.path} fill={pal[b.ci % pal.length]}
                         opacity={far ? 0.45 : mid ? 0.7 : 0.95} />;
          })}
        </>
      ) : mode === "locallight" ? (
        <>
          {/* Left: flat local colour (albedo). Right: the light alone. */}
          <defs>
            <clipPath id={`ll-l-${seed}`}><rect x={0} y={0} width={W / 2} height={H} /></clipPath>
            <clipPath id={`ll-r-${seed}`}><rect x={W / 2} y={0} width={W / 2} height={H} /></clipPath>
            <radialGradient id={`ll-g-${seed}`} cx="0.75" cy="0.2" r="1.1">
              <stop offset="0%" stopColor="#f7f2e4" />
              <stop offset="60%" stopColor="#9a917f" />
              <stop offset="100%" stopColor="#4a443a" />
            </radialGradient>
          </defs>
          <rect width={W} height={H} fill="#fffdf7" />
          <g clipPath={`url(#ll-l-${seed})`}>
            {shown.map((b, i) => (
              <path key={i} d={b.path} fill={ALL[b.ci % ALL.length]} />
            ))}
          </g>
          <g clipPath={`url(#ll-r-${seed})`}>
            <rect width={W} height={H} fill={`url(#ll-g-${seed})`} />
            {shown.map((b, i) => (
              <path key={i} d={b.path} fill={GREY[b.ci % GREY.length]} opacity={0.35} />
            ))}
          </g>
          <line x1={W / 2} y1={0} x2={W / 2} y2={H} stroke="#2b251b" strokeWidth={1.2} opacity={0.5} />
        </>
      ) : mode === "focus" ? (
        <>
          {/* Rule-of-thirds grid, one winning focal ring, one subdued rival */}
          <rect width={W} height={H} fill="#fffdf7" />
          {shown.map((b, i) => (
            <path key={i} d={b.path} fill={ALL[b.ci % ALL.length]} opacity={0.35} />
          ))}
          {[W / 3, (2 * W) / 3].map(x => (
            <line key={`v${x}`} x1={x} y1={0} x2={x} y2={H} stroke="#2b251b" strokeWidth={0.7} opacity={0.35} />
          ))}
          {[H / 3, (2 * H) / 3].map(y => (
            <line key={`h${y}`} x1={0} y1={y} x2={W} y2={y} stroke="#2b251b" strokeWidth={0.7} opacity={0.35} />
          ))}
          <circle cx={(2 * W) / 3} cy={H / 3} r={26} fill="none" stroke="#b4511f" strokeWidth={2.2} opacity={0.9} />
          <circle cx={W / 3 - 10} cy={(2 * H) / 3} r={17} fill="none" stroke="#3e5c76" strokeWidth={1.4} strokeDasharray="5 4" opacity={0.75} />
        </>
      ) : mode === "traps" ? (
        <>
          {/* Notan field with tinted rings where simultaneous contrast bites */}
          <rect width={W} height={H} fill="#f3edde" />
          {shown.map((b, i) => (
            <path key={i} d={b.path} fill={NOTAN[b.ci % 3]} />
          ))}
          {[[W * 0.28, H * 0.32, 22, "#3e5c76"], [W * 0.68, H * 0.62, 26, "#b4511f"], [W * 0.82, H * 0.22, 15, "#3e5c76"]].map(([cx, cy, r, c], i) => (
            <g key={i}>
              <circle cx={cx as number} cy={cy as number} r={r as number} fill={c as string} opacity={0.22} />
              <circle cx={cx as number} cy={cy as number} r={r as number} fill="none" stroke={c as string} strokeWidth={1.4} strokeDasharray="4 3" opacity={0.85} />
            </g>
          ))}
        </>
      ) : mode === "palette" ? (
        <>
          <rect width={W} height={H} fill="#f3edde" />
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
          <rect width={W} height={H} fill={mode === "notan" ? "#f3edde" : "#fffdf7"} />
          {shown.map((b, i) => {
            if (mode === "line") {
              return <path key={i} d={b.path} fill="none" stroke="#2b251b" strokeWidth={i < 5 ? 1.7 : 0.8} opacity={i < 5 ? 0.9 : 0.4} />;
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
                    <text x={b.x} y={b.y + 2.8} fontSize={8} fill="#241f16" textAnchor="middle" fontFamily="monospace" fontWeight="bold">
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
                    <circle key={k} cx={px} cy={py} r={1.6} fill="#b4511f" opacity={0.85} />
                  ))}
                </g>
              );
            }
            if (mode === "subject") {
              // Subject in full colour, surroundings desaturated and lifted
              const focal = Math.hypot(b.x - W * 0.58, b.y - H * 0.45) < 46;
              return focal
                ? <path key={i} d={b.path} fill={ALL[b.ci % ALL.length]} />
                : <path key={i} d={b.path} fill={GREY[b.ci % GREY.length]} opacity={0.35} />;
            }
            if (mode === "edges") {
              // Warm crisp edges on the focal point, cool soft edges elsewhere
              const focal = Math.hypot(b.x - W * 0.58, b.y - H * 0.45) < 52;
              return <path key={i} d={b.path} fill="none"
                           stroke={focal ? "#b4511f" : "#3e5c76"}
                           strokeWidth={focal ? 1.8 : 0.8}
                           opacity={focal ? 0.95 : 0.3} />;
            }
            // colour
            return <path key={i} d={b.path} fill={ALL[b.ci % ALL.length]} opacity={0.92} />;
          })}
        </>
      )}
    </svg>
  );
}
