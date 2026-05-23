# Assembly Line Optimize

Private visual-inspection project for checking whether an assembly-line image contains all required package components.

The current inspection target is:

1. Bottle
2. Warranty Service Manual
3. Battery Instruction Manual
4. Download Service Manual
5. Service QR Manual

The business rule is simple: if all five components are present, the result is `true`; if any one is missing, the result is `false`.

## Current Version

This repository captures the current working prototype:

- Local FastAPI inspection service with a Chinese web UI.
- Image and video upload support.
- Reserved camera/RTSP/folder-watch interface for future live stream input.
- Five-class business output.
- Current deployed model path: `models/current_2class_yolo26s_seg_best.pt`.
- Detection-time model selector:
  - `yolo26_2class_ocr`: old YOLO26 2-class localization plus PaddleOCR manual classification.
  - `yolo26_5class_direct`: Jesse-trained YOLO26 5-class direct detector.
- PaddleOCR-based manual-type identification.
- Rule editor for required classes, minimum counts, and confidence threshold.
- Scripts used to generate synthetic datasets and YOLO training datasets.

Large generated datasets and training runs are intentionally not committed to Git. The complete local workspace currently contains about 52 GB of generated images, YOLO runs, and intermediate artifacts; those are documented here and reproduced through the scripts.

## Architecture

The current deployed pipeline is:

1. A YOLO26 segmentation model detects two geometric classes:
   - `bottle`
   - generic `manual`
2. The service extracts each detected manual region.
3. PaddleOCR reads the manual crop.
4. Keyword rules classify OCR text into one of four manual business classes:
   - Warranty Service Manual
   - Battery Instruction Manual
   - Download Service Manual
   - Service QR Manual
5. The rule engine checks whether all five business classes are present.
6. The UI shows the final pass/fail result and annotated output.

This split was chosen because the four manuals have very similar physical shapes and differ mainly by printed text. A pure detector can locate manuals, while OCR gives a more explicit semantic check.

## Local Service

Run:

```bash
cd /mnt/f/CodexWorkspace/assembly_line_optimize
python3 -m pip install -r requirements.txt
python3 -m uvicorn local_inspection_service.server:app --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

Main files:

- `local_inspection_service/server.py`: FastAPI API, YOLO inference, OCR, rule engine, annotation rendering.
- `local_inspection_service/static/index.html`: web UI.
- `local_inspection_service/static/app.js`: frontend behavior, upload flow, progress bar, Chinese text.
- `local_inspection_service/static/styles.css`: UI styling.
- `local_inspection_service/data/config.json`: active local configuration.

## Runtime Notes

PaddleOCR is sensitive to PaddlePaddle runtime versions in this environment.

Known working setup:

- `paddleocr`
- `paddlepaddle==3.2.2`
- `numpy==2.3.5`
- `ultralytics`
- Python 3.12
- CUDA GPU is used by YOLO training/inference where available.

The server preloads `libgomp.so.1` from the local torch package when available and sets Paddle runtime flags to avoid the known PIR/oneDNN issues in this WSL environment.

## Current Performance

Measured on the local workstation:

- YOLO-only inference: about `0.08s` per image.
- PaddleOCR single manual crop, single direction: average about `2.67s`, median about `2.51s`.
- Old OCR strategy, four rotations per manual: about `49.6s` end to end.
- Current optimized YOLO+OCR strategy: about `15s` steady-state for a complete five-item image.

The remaining bottleneck is OCR. A complete true image still has four manual OCR passes.

## Source Assets

Core tracked assets:

- `standardized_manuals/`
  - Four perspective-corrected manual images.
  - `precise_individual_extraction_manifest.json` records source crop/corner metadata.
  - `corner_annotations/` contains source corner QA images.
- `backgrounds/`
  - Conveyor-surface background matched to the reference production view.
  - `background_manifest.json` records prompt/source notes.
- `generated_bottle_pose_collection/`
  - Generated bottle pose references used to replace proxy sticks/dots.
  - These references define bottle appearance and scale.
- `scripts/`
  - Reproducible generation and dataset-building scripts.

Important local-only generated folders, intentionally ignored by Git:

- `synthetic_1000_atom_proxy_combinations/`
- `synthetic_3000_atom_proxy_full_rotation_combinations/`
- `image2_optimized_1000_atom_proxy_combinations/`
- `image2_optimized_3000_atom_proxy_full_rotation_combinations/`
- `yolo26_seg_2class_visible_polygon_4000_full_rotation_trial/`
- `yolo26_seg_5class_visible_polygon_4000_full_rotation_trial/`

## Dataset Generation Design

The training data was built in stages.

### 1. Standardize the manuals

The four original manual images were extracted and perspective-corrected into clean top-down assets. These standardized manuals are the canonical sources used in synthetic composition.

Relevant script:

```text
scripts/extract_precise_manuals_from_individual_sources.py
```

### 2. Generate atom proxy combinations

The target scene is one conveyor background plus up to five components. The five components are:

- one bottle
- four manuals

The generated combinations are based on the non-empty subset logic:

- true class: all five components are present.
- false class: at least one component is missing.

The initial 1000-sample plan used a false-class distribution weighted toward realistic missing-part cases:

- missing one component: dominant share
- missing two or three components: smaller shares
- missing four or five components: excluded as unrealistic for this production case

Relevant scripts:

```text
scripts/generate_1000_atom_proxy_dataset.py
scripts/generate_31_item_proxy_combinations.py
```

### 3. Add full rotation coverage

The first datasets were too biased toward upright manuals. Real images showed that manuals can be rotated, inverted, or sideways. To reduce orientation bias, an additional 3000 samples were generated with broad random rotations.

Requirements used:

- Keep the original 1000 samples unchanged.
- Add 3000 new samples with full random orientation distribution.
- Use a random state instead of fixed angles such as 15 or 25 degrees.
- Preserve random position and layer ordering.
- Keep visible occlusion behavior realistic.

Relevant scripts:

```text
scripts/generate_3000_atom_proxy_full_rotation_dataset.py
scripts/replace_3000_full_rotation_proxy_with_bottle.py
```

### 4. Replace proxy bottle markers

Early composition used black sticks/dots as bottle proxies:

- horizontal/diagonal stick: bottle lying down in that direction.
- dot: upright bottle; the dot represented approximately the red cap diameter, not the full bottle size.

The proxies were later replaced with real bottle sprites from `generated_bottle_pose_collection/`. The bottle box length follows the proxy length; the width is based on the real bottle size relationship from the source reference photos.

### 5. Build YOLO labels

The final segmentation dataset uses visible polygons, not full hidden rectangles.

This means:

- If a manual is partially covered, only the visible part is labeled.
- If one object is above another, the lower object's hidden region is subtracted.
- Labels can be multi-edge polygons, not just rectangles.
- Bottle and manual masks are generated from the compositing geometry.

Relevant scripts:

```text
scripts/build_yolo26_seg_2class_visible_polygon_4000_dataset.py
scripts/build_yolo26_seg_5class_visible_polygon_4000_dataset.py
```

## Dataset Quality

The dataset quality improved through several rounds:

- Manual extraction was standardized from source images.
- The conveyor background was fixed to match the intended camera placement.
- Object placement and layer order were randomized.
- Bottle proxies were forced to stay above all manuals when required.
- Bottle proxies were replaced with generated bottle references.
- Full rotation coverage was added after real-image tests showed orientation bias.
- Visible polygon labels were adopted after full hidden boxes caused bad learning under occlusion.

Known limitations:

- Synthetic images are still not a complete substitute for real production photos.
- Manual classes are visually similar; pure YOLO manual classification may confuse classes unless enough real or high-quality synthetic text variation is included.
- OCR currently dominates runtime.
- Reflections on the bottle can still cause false positives in difficult real photos.
- Real camera calibration, lighting, lens distortion, and conveyor texture variation need more real-world validation.

## Training Runs

### Deployed two-class segmentation model

Current deployed model:

```text
models/current_2class_yolo26s_seg_best.pt
```

Original local training output:

```text
yolo26_seg_2class_visible_polygon_4000_full_rotation_trial/runs/yolo26s_seg_2class_visible_polygon_full_rotation_100e_img640_workers0/weights/best.pt
```

Training command:

```bash
yolo segment train \
  model=/mnt/f/CodexWorkspace/assembly_line_optimize/yolo26s-seg.pt \
  data=/mnt/f/CodexWorkspace/assembly_line_optimize/yolo26_seg_2class_visible_polygon_4000_full_rotation_trial/dataset/data.yaml \
  imgsz=640 epochs=100 batch=8 device=0 workers=0 \
  project=/mnt/f/CodexWorkspace/assembly_line_optimize/yolo26_seg_2class_visible_polygon_4000_full_rotation_trial/runs \
  name=yolo26s_seg_2class_visible_polygon_full_rotation_100e_img640_workers0 \
  exist_ok=True
```

The `workers=0` setting is intentional in this WSL environment because multiprocessing socket behavior caused worker failures.

Recorded metrics for the two-class model:

- Test box mAP50-95: about `0.990`
- Test mask mAP50-95: about `0.948`
- Bottle mask mAP50-95: about `0.904`
- Manual mask mAP50-95: about `0.992`

### Five-class YOLO model

The Jesse-trained five-class segmentation model is available as a selectable local-service model:

```text
models/current_5class_yolo26s_seg_best.pt
```

Original local training output:

```text
yolo26_seg_5class_visible_polygon_4000_full_rotation_trial/runs/yolo26s_seg_5class_visible_polygon_full_rotation_100e_img640_workers0/weights/best.pt
```

Goal:

- Detect Bottle directly.
- Detect each of the four manual types directly.
- Reduce or remove OCR dependency if class performance is reliable enough.

This is selectable in the UI, but the old YOLO+OCR path remains the default because real-photo validation is still needed.

## Why OCR Was Added

The manuals are physically similar:

- same paper size
- similar rectangular shape
- similar color
- different printed text

The detector is strong at finding paper-like objects, but it can confuse manual types because type identity is mainly textual. OCR makes the class decision based on text evidence rather than only object shape.

The current plan is to keep both methods:

1. YOLO+OCR mode: more explainable, slower, better when text needs verification.
2. Pure five-class YOLO mode: faster, simpler, but must prove reliable on real photos.

The local service now exposes both modes through the detection tool model selector.

## Future Directions

Planned improvements:

1. Add a hybrid inference mode with OCR fallback only on low-confidence five-class YOLO predictions.
2. Validate the five-class YOLO model against real production photos.
3. Add real-photo validation set from the actual production camera.
4. Add camera/live-stream input:
   - local camera index
   - RTSP URL
   - folder watch
5. Add calibration tools:
   - fixed conveyor ROI
   - perspective normalization
   - camera exposure/lighting check
6. Add confidence dashboards:
   - per-class count
   - per-frame history
   - false-positive/false-negative review queue
7. Add dataset regeneration controls to the UI:
   - upload new component photos
   - generate synthetic combinations
   - start training manually
8. Add export/deployment targets:
   - ONNX
   - TensorRT
   - Windows executable or installer
   - localhost service package
9. Improve speed:
   - OCR only on cropped header/title regions
   - use model-derived orientation instead of multi-rotation OCR
   - use lightweight manual image classifier as OCR fallback/replacement
   - run OCR in a worker queue for video frames

## Repository Policy

This repository is private.

Tracked:

- source code
- local service UI
- generation scripts
- core source assets
- current deployable model weight
- documentation

Not tracked:

- 11GB+ image datasets
- full YOLO run folders
- temporary uploads/outputs
- Python virtual environments
- intermediate generated batches

The ignored artifacts are reproducible from the tracked scripts and documented local paths.
