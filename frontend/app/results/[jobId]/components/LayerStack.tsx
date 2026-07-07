// ── Layered image composition ─────────────────────────────────────────────────
export default function LayerStack({
  assets,
  imageWidth,
  imageHeight,
  maxHeight = 520,
}: {
  assets:      string[];
  imageWidth?:  number;
  imageHeight?: number;
  maxHeight?:   number;
}) {
  if (assets.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text-dim)", background: "var(--surface)", borderRadius: 12 }}>
        No layers selected — enable at least one above
      </div>
    );
  }

  const aspectStyle = imageWidth && imageHeight
    ? { aspectRatio: `${imageWidth}/${imageHeight}` }
    : {};

  return (
    <div key={assets.join("|")}
         className="layer-transition"
         style={{ position: "relative", width: "100%", maxHeight, overflow: "hidden", borderRadius: 12, ...aspectStyle }}>
      {assets.map((url, i) => (
        <img
          key={url}
          src={url}
          alt=""
          style={{
            position:     i === 0 ? "relative" : "absolute",
            top:          0,
            left:         0,
            width:        "100%",
            height:       "100%",
            objectFit:    "contain",
            mixBlendMode: i === 0 ? "normal" : "multiply",
            opacity:      0.85,
          }}
        />
      ))}
    </div>
  );
}
