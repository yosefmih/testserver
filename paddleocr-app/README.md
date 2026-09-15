# paddleocr-app

End-to-end document OCR on a self-hosted PaddleOCR-VL. Upload a PDF in the browser; the
server splits it into page chunks, stores everything in S3, runs the chunks through
PaddleOCR concurrently, stitches the pages back into one markdown document (merging tables
and re-levelling headings across page boundaries via PaddleOCR's `restructure-pages`), and
serves the result as a preview and a zip download.

```
browser ── upload ──▶ paddleocr-app (FastAPI + embedded Svelte UI)
                         │  input.pdf, chunks/<n>/input.pdf, imgs/, result.md, result.zip
                         ├──────────────────────────────────────────────────▶ S3 (or a local dir)
                         │  POST /layout-parsing per chunk, POST /restructure-pages once
                         └──────────────────────────────────────────────────▶ paddleocr-hps (gateway → Triton pipeline → vLLM), one pod per GPU
```

## Layout

- `backend/` Python service: `app/main.py` (HTTP API + static UI), `app/worker.py` (job
  queue: chunk → OCR → store → assemble), `app/ocr.py` (PaddleOCR client), `app/storage.py`
  (S3 or local files), `app/pdf.py`, `app/assemble.py`, `app/jobs.py`.
- `frontend/` Svelte 5 + Vite single-page UI. `npm run build` produces `dist/`, which the
  Dockerfile copies into the Python package as `app/static`.
- `Dockerfile` builds both stages into one image; `python -m app` serves the UI and API on
  `PORT`.
- `charts/paddleocr-vl-hps/` Helm chart for PaddleOCR-VL high-performance serving: one pod
  with the vLLM sidecar, the Triton pipeline (`pipeline.instances` copies) and the gateway.
  `values.yaml` is sized for a g6.2xlarge (L4), `values-g6xlarge.yaml` for a g6.xlarge,
  `values-g6e-8xlarge.yaml` for an L40S, `values-stock-vllm.yaml` swaps in upstream vLLM.
- `scripts/` `build-paddleocr-images.sh` builds the two PaddleOCR images Baidu does not
  publish and mirrors the vLLM image into ECR; `deploy-paddleocr.sh` installs the chart on
  the GPU node group; `build-app-image.sh` builds this app's image. `common.sh` holds the
  shared defaults.
- `porter.yaml` deploys this app as a private Porter web service on CPU nodes.

## Run locally

Without a GPU, fake the OCR endpoint with the harness in `../paddleocr-bench`:

```bash
(cd ../paddleocr-bench && GOWORK=off PORT=8118 go run ./cmd/fakeocr) &

cd frontend && npm install && npm run build && cd ..
cp -R frontend/dist backend/app/static
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
PADDLEOCR_URL=http://localhost:8118 LOCAL_DATA_DIR=./data .venv/bin/python -m app
open http://localhost:8080
```

For UI work, `npm run dev` in `frontend/` serves the app with hot reload and proxies `/api`
to the backend on 8080.

## Deploy

Set `AWS_PROFILE` for the account that owns the ECR registry, then:

1. Build and push the PaddleOCR images once per SDK version:

   ```bash
   ECR_REGISTRY=<account>.dkr.ecr.us-east-1.amazonaws.com KUBE_CONTEXT=fir-fir scripts/build-paddleocr-images.sh
   ```

   The script downloads Baidu's HPS SDK tarball and the gateway sources from PaddleOCR at a
   pinned commit, assembles the build context, and runs three pods in the cluster (two
   Kaniko builds, one crane mirror) that push straight to ECR; the base images are 8 to
   15 GB and never touch this machine. `BUILDER=docker` builds locally instead;
   `NODE_GROUP_ID=<id>` pins the build pods to a Porter node group.
2. Install PaddleOCR on the GPU node group (Karpenter provisions the node):

   ```bash
   KUBE_CONTEXT=fir-fir NODE_GROUP_ID=<gpu node group id> INSTANCE_TYPES=g6.2xlarge scripts/deploy-paddleocr.sh
   ```

   The service is reachable in-cluster at `http://paddleocr-hps.paddleocr.svc.cluster.local:8080`.
3. Build this app's image (`scripts/build-app-image.sh`) or let Porter build it from
   `porter.yaml`. Set `S3_BUCKET` to a bucket the pod can read and write (Pod Identity or
   an instance role) and `PADDLEOCR_URL` to the service above.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `8080` | Listen port |
| `PADDLEOCR_URL` | `http://localhost:8118` | Base URL of the PaddleOCR-VL service |
| `OCR_TIMEOUT_SECONDS` | `900` | Per-request timeout; a 50-page chunk takes ~40 s on an L4 |
| `OCR_ATTEMPTS` | `3` | Attempts per chunk before the job fails |
| `S3_BUCKET` | unset | Bucket for inputs, chunks, images, results and job manifests |
| `S3_PREFIX` | `paddleocr-app` | Key prefix inside the bucket |
| `LOCAL_DATA_DIR` | `./data` | Used instead of S3 when `S3_BUCKET` is unset |
| `DEFAULT_CHUNK_PAGES` | `50` | Form default for pages per OCR request |
| `DEFAULT_CONCURRENCY` | `2` | Form default for requests in flight per job |
| `JOB_CONCURRENCY` | `1` | Jobs processed at once |
| `RESTRUCTURE_PAGES` | `true` | Form default for the cross-page merge step |
| `MAX_UPLOAD_BYTES` | `536870912` | Upload size limit |

## How a job runs

1. Upload stores `jobs/<id>/input.pdf` and `job.json`, then queues the job. Manifests are
   reloaded on start, so a restart re-queues unfinished jobs and skips chunks already done.
2. The worker splits the PDF with pypdf into `chunk_pages` ranges and sends up to
   `concurrency` chunks at a time to `POST /layout-parsing` (base64 PDF, markdown images
   returned inline). Each chunk's pages, images and pruned layout results are stored under
   `jobs/<id>/chunks/<n>/` and `jobs/<id>/imgs/`. Image keys are prefixed with the page
   number because PaddleOCR names them by bounding box and two pages can collide.
3. When every chunk is done the pages are stitched: `POST /restructure-pages` with all
   pruned results and `concatenatePages: true` merges tables split across pages and
   re-levels headings; if that call fails, or the job was submitted without it, the pages
   are concatenated in order. `result.md` and `result.zip` (markdown plus `imgs/`) are
   written next to the manifest.

Sizing notes from the benchmark (`../paddleocr-bench`, results in the workstation
`weave-paddleocr-eval.md`): one L4 sustains 1.2 to 1.5 pages/s cold, so 50-page chunks with
2 to 3 in flight per pod keep the pod busy, and a 950-page document should be fanned across
several pods to finish in under 10 minutes.
