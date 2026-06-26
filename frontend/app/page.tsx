"use client";
import { useState, useRef, DragEvent, ChangeEvent } from "react";
import { useRouter } from "next/navigation";

const MEDIUMS = [
  { id: "oil",        label: "Oil Paint",    icon: "🎨" },
  { id: "watercolor", label: "Watercolour",  icon: "💧" },
  { id: "acrylic",    label: "Acrylic",      icon: "🖌️" },
  { id: "pencil",     label: "Pencil",       icon: "✏️" },
  { id: "charcoal",   label: "Charcoal",     icon: "🪨" },
];

const COLOR_COUNTS = [16, 24, 32, 48];

export default function HomePage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile]           = useState<File | null>(null);
  const [preview, setPreview]     = useState<string | null>(null);
  const [medium, setMedium]       = useState("oil");
  const [nColors, setNColors]     = useState(32);
  const [dragging, setDragging]   = useState(false);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);

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
      form.append("file", file);
      form.append("medium", medium);
      form.append("n_colors", String(nColors));

      const res = await fetch("http://localhost:8000/jobs/", {
        method: "POST",
        body: form,
      });

      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      router.push(`/results/${data.job_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed. Is the backend running?");
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 py-16"
          style={{ background: "var(--bg)" }}>

      {/* Header */}
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold mb-3" style={{ color: "var(--accent)" }}>
          Painting Instructor
        </h1>
        <p className="text-lg max-w-md mx-auto" style={{ color: "var(--text-dim)" }}>
          Upload a photo. We break it down into every step a painter needs —
          outlines, values, colours, and a progressive video tutorial.
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
            minHeight: preview ? "auto" : 220,
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
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={onChange}
          />
        </div>

        {preview && (
          <button
            className="text-sm underline"
            style={{ color: "var(--text-dim)" }}
            onClick={() => { setFile(null); setPreview(null); }}
          >
            Choose a different photo
          </button>
        )}

        {/* Medium */}
        <div>
          <label className="block text-sm font-medium mb-3" style={{ color: "var(--text-dim)" }}>
            Painting medium
          </label>
          <div className="flex flex-wrap gap-2">
            {MEDIUMS.map(m => (
              <button
                key={m.id}
                onClick={() => setMedium(m.id)}
                className="px-4 py-2 rounded-lg border text-sm font-medium transition-colors"
                style={{
                  background:   medium === m.id ? "var(--accent)" : "var(--surface)",
                  color:        medium === m.id ? "#0f0e0d"       : "var(--text)",
                  borderColor:  medium === m.id ? "var(--accent)" : "var(--border)",
                }}
              >
                {m.icon} {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* Colour count */}
        <div>
          <label className="block text-sm font-medium mb-3" style={{ color: "var(--text-dim)" }}>
            Palette size — {nColors} colours
          </label>
          <div className="flex gap-2">
            {COLOR_COUNTS.map(n => (
              <button
                key={n}
                onClick={() => setNColors(n)}
                className="px-4 py-2 rounded-lg border text-sm font-medium transition-colors"
                style={{
                  background:  nColors === n ? "var(--accent)" : "var(--surface)",
                  color:       nColors === n ? "#0f0e0d"       : "var(--text)",
                  borderColor: nColors === n ? "var(--accent)" : "var(--border)",
                }}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        {/* Error */}
        {error && (
          <p className="text-sm px-4 py-3 rounded-lg" style={{ background: "#2a1010", color: "#e07070" }}>
            {error}
          </p>
        )}

        {/* Submit */}
        <button
          onClick={submit}
          disabled={!file || loading}
          className="w-full py-4 rounded-xl font-semibold text-base transition-all"
          style={{
            background: (!file || loading) ? "var(--accent-dim)" : "var(--accent)",
            color: "#0f0e0d",
            cursor: (!file || loading) ? "not-allowed" : "pointer",
            opacity: (!file || loading) ? 0.7 : 1,
          }}
        >
          {loading ? "Uploading…" : "Generate Tutorial →"}
        </button>
      </div>
    </main>
  );
}
