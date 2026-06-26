"use client";
import { useState, useRef, DragEvent, ChangeEvent } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const MEDIUMS = [
  { id: "oil",        label: "Oil Paint",   icon: "🎨", tip: "Rich blending, slow drying. Best for realism and portraiture." },
  { id: "watercolor", label: "Watercolour", icon: "💧", tip: "Transparent layers. Work light-to-dark, preserve whites." },
  { id: "acrylic",    label: "Acrylic",     icon: "🖌️", tip: "Fast-drying, versatile. Can mimic oil or watercolour." },
  { id: "pencil",     label: "Pencil",      icon: "✏️", tip: "Graphite hatching. Build value through layered strokes." },
  { id: "charcoal",   label: "Charcoal",    icon: "⬛", tip: "Broad marks, erasable highlights. Great for tonal studies." },
];

const DETAIL_LEVELS = [
  { value: 1, label: "Foundation",    desc: "Basic shapes + primary contours only. Best for beginners." },
  { value: 2, label: "Simplified",    desc: "Major forms + key shadows. Quick study." },
  { value: 3, label: "Standard",      desc: "Balanced detail + colour zones. Most paintings." },
  { value: 4, label: "Detailed",      desc: "Fine regions, decorative elements, texture." },
  { value: 5, label: "Full Reference",desc: "Every detected layer — complete hierarchical breakdown." },
];

const VALUE_ZONE_OPTIONS = [3, 5, 7] as const;

export default function HomePage() {
  const router    = useRouter();
  const inputRef  = useRef<HTMLInputElement>(null);

  const [file,        setFile]        = useState<File | null>(null);
  const [preview,     setPreview]     = useState<string | null>(null);
  const [medium,      setMedium]      = useState("oil");
  const [paletteSize, setPaletteSize] = useState(12);
  const [detailLevel, setDetailLevel] = useState(3);
  const [valueZones,  setValueZones]  = useState<3 | 5 | 7>(5);
  const [dragging,    setDragging]    = useState(false);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState<string | null>(null);

  function handleFile(f: File) {
    if (!f.type.startsWith("image/")) {
      setError("Please upload an image file (JPG, PNG, HEIC).");
      return;
    }
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setError(null);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }

  function onChange(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  }

  async function submit() {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file",         file);
      form.append("medium",       medium);
      form.append("palette_size", String(paletteSize));
      form.append("detail_level", String(detailLevel));
      form.append("value_zones",  String(valueZones));

      const res = await fetch(`${API}/jobs/`, { method: "POST", body: form });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `Server error: ${res.status}`);
      }
      const data = await res.json();
      router.push(`/results/${data.job_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed. Is the backend running?");
      setLoading(false);
    }
  }

  const selectedMedium = MEDIUMS.find(m => m.id === medium);
  const selectedDetail = DETAIL_LEVELS.find(d => d.value === detailLevel);

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 py-16"
          style={{ background: "var(--bg)" }}>

      {/* Header */}
      <div className="text-center mb-10">
        <h1 className="text-4xl font-bold mb-3" style={{ color: "var(--accent)" }}>
          Painting Instructor
        </h1>
        <p className="text-lg max-w-md mx-auto" style={{ color: "var(--text-dim)" }}>
          Upload a reference photo. Get a structured, step-by-step painting lesson —
          hierarchical layers from basic shapes to full detail.
        </p>
      </div>

      <div className="w-full max-w-2xl space-y-6">

        {/* Drop zone */}
        <div
          onClick={() => inputRef.current?.click()}
          onDrop={onDrop}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          className="relative cursor-pointer rounded-xl border-2 border-dashed transition-colors flex items-center justify-center"
          style={{
            borderColor: dragging ? "var(--accent)" : "var(--border)",
            background:  dragging ? "rgba(200,150,90,0.05)" : "var(--surface)",
            minHeight:   preview  ? "auto" : 200,
          }}
        >
          {preview ? (
            <img src={preview} alt="preview" className="w-full rounded-xl object-contain max-h-80" />
          ) : (
            <div className="text-center py-12 px-6">
              <div className="text-5xl mb-4">🖼️</div>
              <p className="font-medium mb-1" style={{ color: "var(--text)" }}>
                Drop your reference photo here
              </p>
              <p className="text-sm" style={{ color: "var(--text-dim)" }}>
                JPG, PNG, HEIC — any size
              </p>
            </div>
          )}
          <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={onChange} />
        </div>

        {preview && (
          <button className="text-sm underline" style={{ color: "var(--text-dim)" }}
                  onClick={() => { setFile(null); setPreview(null); }}>
            Choose a different photo
          </button>
        )}

        {/* Medium selector */}
        <div>
          <label className="block text-sm font-medium mb-3" style={{ color: "var(--text-dim)" }}>
            Painting medium
          </label>
          <div className="flex flex-wrap gap-2">
            {MEDIUMS.map(m => (
              <button key={m.id} onClick={() => setMedium(m.id)}
                      className="px-4 py-2 rounded-lg border text-sm font-medium transition-colors"
                      style={{
                        background:  medium === m.id ? "var(--accent)" : "var(--surface)",
                        color:       medium === m.id ? "#0f0e0d"       : "var(--text)",
                        borderColor: medium === m.id ? "var(--accent)" : "var(--border)",
                      }}>
                {m.icon} {m.label}
              </button>
            ))}
          </div>
          {selectedMedium && (
            <p className="text-xs mt-2" style={{ color: "var(--text-dim)" }}>{selectedMedium.tip}</p>
          )}
        </div>

        {/* Palette size */}
        <div>
          <label className="block text-sm font-medium mb-3" style={{ color: "var(--text-dim)" }}>
            Palette size — <span style={{ color: "var(--accent)" }}>{paletteSize} colours</span>
          </label>
          <input type="range" min={6} max={32} step={2} value={paletteSize}
                 onChange={e => setPaletteSize(Number(e.target.value))}
                 className="w-full accent-yellow-600" />
          <div className="flex justify-between text-xs mt-1" style={{ color: "var(--text-dim)" }}>
            <span>6 (minimal)</span><span>32 (detailed)</span>
          </div>
        </div>

        {/* Value zones */}
        <div>
          <label className="block text-sm font-medium mb-3" style={{ color: "var(--text-dim)" }}>
            Value zones
          </label>
          <div className="flex gap-2">
            {VALUE_ZONE_OPTIONS.map(n => (
              <button key={n} onClick={() => setValueZones(n)}
                      className="px-5 py-2 rounded-lg border text-sm font-medium transition-colors"
                      style={{
                        background:  valueZones === n ? "var(--accent)" : "var(--surface)",
                        color:       valueZones === n ? "#0f0e0d"       : "var(--text)",
                        borderColor: valueZones === n ? "var(--accent)" : "var(--border)",
                      }}>
                {n} zones
              </button>
            ))}
          </div>
          <p className="text-xs mt-2" style={{ color: "var(--text-dim)" }}>
            3 = shadow / midtone / light &nbsp;·&nbsp; 5 = standard &nbsp;·&nbsp; 7 = maximum tonal range
          </p>
        </div>

        {/* Detail level */}
        <div>
          <label className="block text-sm font-medium mb-3" style={{ color: "var(--text-dim)" }}>
            Starting detail level
          </label>
          <div className="flex flex-wrap gap-2">
            {DETAIL_LEVELS.map(d => (
              <button key={d.value} onClick={() => setDetailLevel(d.value)}
                      className="px-3 py-2 rounded-lg border text-sm font-medium transition-colors"
                      style={{
                        background:  detailLevel === d.value ? "var(--accent)" : "var(--surface)",
                        color:       detailLevel === d.value ? "#0f0e0d"       : "var(--text)",
                        borderColor: detailLevel === d.value ? "var(--accent)" : "var(--border)",
                      }}>
                {d.label}
              </button>
            ))}
          </div>
          {selectedDetail && (
            <p className="text-xs mt-2" style={{ color: "var(--text-dim)" }}>{selectedDetail.desc}</p>
          )}
        </div>

        {/* Error */}
        {error && (
          <p className="text-sm px-4 py-3 rounded-lg" style={{ background: "#2a1010", color: "#e07070" }}>
            {error}
          </p>
        )}

        {/* Submit */}
        <button onClick={submit} disabled={!file || loading}
                className="w-full py-4 rounded-xl font-semibold text-base transition-all"
                style={{
                  background: (!file || loading) ? "var(--accent-dim)" : "var(--accent)",
                  color:  "#0f0e0d",
                  cursor: (!file || loading) ? "not-allowed" : "pointer",
                  opacity:(!file || loading) ? 0.7 : 1,
                }}>
          {loading ? "Uploading…" : "Generate Tutorial →"}
        </button>

      </div>
    </main>
  );
}
