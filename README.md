# Painting Instructor — AI Art Tutor

Upload a reference photo. Get a complete painting tutorial built on real art fundamentals.

## What it generates

| Output | Description |
|--------|-------------|
| **Line Art** | 3-layer composite: silhouette (thick) + interior forms (thin) + background (XDoG) |
| **Notan** | 3-zone LAB value study — shadow / midtone / light |
| **Colour Temperature** | Warm/cool map via LAB b-channel (Gurney method) |
| **Light Direction** | Sobel gradient histogram + 5 Gurney modelling zones |
| **Colour Palette** | 32-colour LAB K-means++ chart sorted by area coverage |
| **Paint by Numbers** | BiSeNet face-aware regions with bilateralFilter×4 pre-processing |
| **Dot to Dot** | Skeleton-traced numbered dots following actual contour paths |
| **Tutorial Video** | Progressive animation: blank → outline → values → colour → detail |
| **PDF Book** | All pages assembled A4 for print |

## Stack

- **Backend**: Python 3.14, FastAPI, Celery + Redis
- **ML**: kornia (DexiNed), controlnet_aux (LineartDetector), facexlib (BiSeNet), rembg (BiRefNet)
- **Vision**: OpenCV, scikit-image, scikit-learn, PyWavelets, sknw, shapely
- **Frontend**: Next.js 16 (App Router), TypeScript, Tailwind CSS
- **Video**: OpenCV VideoWriter (progressive layer animation)

## Run locally

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Worker (separate terminal)
celery -A workers.tasks worker --loglevel=info

# Frontend
cd frontend
npm install
npm run dev         # → http://localhost:3000
```

Redis must be running on `localhost:6379` (or set `REDIS_URL` env var).

## Architecture

```
Upload → FastAPI → Celery task → 8-step pipeline → MP4 + PDF + PNG pages
                                                  ↑
                             line_art → dot_to_dot (shared edge map)
                             line_art + notan + color_by_number → video
```

## Art principles implemented

- **Notan** (Japanese): value structure before colour
- **Gurney 5-zone model**: highlight, halftone, core shadow, reflected light, cast shadow
- **LAB colour space** throughout: perceptually uniform, better than RGB for all art operations
- **Bilateral filter ×4** in LAB: edge-preserving smoothing for paint-by-numbers
- **BiSeNet face parsing**: 19 zones prevent facial features merging in region segmentation
- **Pole of inaccessibility**: deepest interior point for number label placement
- **XDoG**: eXtended Difference of Gaussians for expressive background line art
- **Variable line weight**: silhouette thick, interior thin, background 30% — illustration standard
