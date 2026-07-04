"use client";
import { useEffect, useRef } from "react";
import { gsap } from "gsap";

/**
 * Splits text into per-character spans and reveals them with a staggered
 * 3D rotation. Words stay unbreakable so lines wrap naturally.
 */
export default function KineticTitle({
  text,
  className = "",
  delay = 0,
  gradient = false,
}: {
  text: string;
  className?: string;
  delay?: number;
  /* Applied per-char: background-clip:text on a parent doesn't paint through
     transformed child spans, so a gradient wrapper would render invisible. */
  gradient?: boolean;
}) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const chars = el.querySelectorAll<HTMLElement>(".kchar");
    const anim = gsap.fromTo(
      chars,
      { yPercent: 115, rotateX: -80, opacity: 0 },
      { yPercent: 0, rotateX: 0, opacity: 1, duration: 1.15, ease: "power4.out", stagger: 0.032, delay }
    );
    return () => {
      anim.kill();
    };
  }, [delay, text]);

  return (
    <span ref={ref} aria-label={text} className={className} style={{ perspective: 900, display: "inline-block" }}>
      {text.split(" ").map((word, wi) => (
        <span key={wi} aria-hidden style={{ display: "inline-block", whiteSpace: "nowrap" }}>
          {word.split("").map((c, ci) => (
            <span
              key={ci}
              className={`kchar${gradient ? " text-gradient" : ""}`}
              style={{ display: "inline-block", transformStyle: "preserve-3d", willChange: "transform" }}
            >
              {c}
            </span>
          ))}
          {wi < text.split(" ").length - 1 && <span className="kchar" style={{ display: "inline-block" }}>&nbsp;</span>}
        </span>
      ))}
    </span>
  );
}
