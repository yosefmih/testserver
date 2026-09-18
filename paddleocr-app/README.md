# paddleocr-app

End-to-end document OCR on a self-hosted PaddleOCR-VL. Upload a PDF in the browser; the
server splits it into page chunks, stores everything in S3, runs the chunks through
PaddleOCR concurrently, stitches the pages back into one markdown document (merging tables
and re-levelling headings across page boundaries via PaddleOCR's `restructure-pages`), and
serves the result as a zip download and an in-browser explorer.

The UI is two screens. The list shows every document as a card with its status, page
count, time taken, throughput, and buttons to download the submitted PDF, the output zip
(markdown plus images) and the bare markdown. Opening a card shows the document page: the
submitted PDF in a viewer on the left and, on the right, the recognised markdown for the
page being viewed, the full stitched document, or the raw markdown. A bar per OCR request
shows how long each took; clicking one jumps to its first page. The Timing button in the
header opens a breakdown: a timeline of every request on a shared clock, segmented by
stage (split the PDF, upload the chunk, OCR round trip, store pages and images), a table
with each request's start, end and per-stage seconds, and the job's phases (queue wait,
recognition span, restructure, archive, total). The OCR round trip is one figure because
the gateway does not report time spent inside the pod per request.

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
  (S3, streaming downloads), `app/pdf.py`, `app/assemble.py`, `app/jobs.py`.
- `frontend/` Svelte 5 + Vite single-page UI (pdf.js for the PDF viewer, marked +
  DOMPurify for markdown). `npm run build` produces `dist/`, which the Dockerfile copies
  into the Python package as `app/static`.
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

Everything the service persists lives in S3, so a local run needs a bucket (any prefix)
and AWS credentials in the environment. Point `PADDLEOCR_URL` at a real deployment through
`kubectl port-forward -n paddleocr svc/paddleocr-hps 8118:8080`, or fake the OCR endpoint
with the harness in `../paddleocr-bench` (`GOWORK=off PORT=8118 go run ./cmd/fakeocr`).

```bash
cd frontend && npm install && npm run build && cd ..
cp -R frontend/dist backend/app/static
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
AWS_PROFILE=<profile> S3_BUCKET=<bucket> S3_PREFIX=paddleocr-app-dev PADDLEOCR_URL=http://localhost:8118 .venv/bin/python -m app
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
| `S3_BUCKET` | required | Bucket for inputs, chunks, images, results and job manifests |
| `S3_PREFIX` | `paddleocr-app` | Key prefix inside the bucket |
| `S3_ENDPOINT_URL` | unset | Alternative S3 endpoint (MinIO, LocalStack) |
| `DEFAULT_CHUNK_PAGES` | `50` | Form default for pages per OCR request |
| `DEFAULT_CONCURRENCY` | `2` | Form default for requests in flight per job |
| `JOB_CONCURRENCY` | `50` | Jobs processed at once; effectively unlimited, the OCR fleet's capacity is the real limit |
| `OCR_BATCH_SIZE` | `8` | Chunks of one job released to the OCR service together, so Triton's dynamic batcher sees them arrive at once. Match the chart's `pipeline.maxBatchSize`; `1` disables grouping |
| `OCR_BATCH_WAIT_SECONDS` | `5` | How long a partial group waits for stragglers before going anyway |
| `RESTRUCTURE_PAGES` | `true` | Form default for the cross-page merge step |
| `MAX_UPLOAD_BYTES` | `536870912` | Upload size limit |
| `DRAIN_TIMEOUT_SECONDS` | `600` | How long shutdown waits for in-flight OCR requests |

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
   are concatenated in order. PaddleOCR derives image file names from bounding boxes when
   it regenerates markdown, so the stitched document is relinked to the page-prefixed
   names before it is stored. `result.md`, `result.zip` (markdown plus `imgs/`) and
   `result.pages.json` (per-page markdown for the explorer) are written next to the
   manifest, and downloads stream straight from S3.

## Shutdown, health and restarts

PaddleOCR's API is synchronous: a chunk's result only exists when its request returns, so
a request abandoned mid-way is GPU time thrown away. On SIGTERM the app therefore stops
taking new jobs and starting new chunks, waits up to `DRAIN_TIMEOUT_SECONDS` for chunks
already sent to PaddleOCR to come back, stores them, parks the job as queued with its
finished chunks intact, and exits. The next process re-queues the job and runs only the
chunks that are left, so a redeploy costs no duplicate work. Keep the drain timeout below
the pod's termination grace period (`porter.yaml`: 540 s inside 600 s) and chunks small
enough to finish within it (a 200-page chunk takes 4 to 5 minutes on one L4).

Two pods can work the same job at once, which is what happens during a rolling deploy:
the old pod drains while the new one starts. Each chunk is guarded by a lease object,
`chunks/<n>/lease.json`, holding the owner and an expiry 45 s out; the owner renews it
every 15 s while the chunk is in flight and deletes it when the chunk's pages are stored.
Claims use S3 conditional writes (create-only, or replace-if-ETag-matches for an expired
lease), so two pods racing for a chunk cannot both win. A pod that finds a live lease
held by someone else waits, polling for the finished pages every 10 s and adopting them
from `chunks/<n>/chunk.json` when they appear, and only takes the chunk over if the lease
lapses, which means the previous owner died. Assembly is guarded the same way by
`assembly.lease`. Verified: a job handed from a draining pod to a fresh pod runs every
chunk exactly once, with the manifest attributing each chunk to the pod that ran it.

Every attempt on a chunk is kept in the manifest with its pod, start, end and outcome, so
the timing panel still shows what a pod that died mid-request was doing: its attempt
appears as a hatched bar and the retry on the new pod as the solid one. Keep chunks small
enough to finish inside the drain budget (100 pages or fewer on an L4); a 300-page chunk
takes 8 to 10 minutes and outlives the grace period, so its work is lost on a redeploy.

- `GET /api/healthz` is liveness: always 200 while the process runs, with `ocrReady` and
  `draining` for diagnostics.
- `GET /api/readyz` is readiness: 503 while draining, 200 otherwise. `porter.yaml` uses
  it as the health check.
- `POST /api/jobs` answers 503 while draining.

## Autoscaling

`charts/paddleocr-vl-hps` ships a KEDA ScaledObject (`autoscaling.enabled: true`) that
scales the OCR deployment on `sum(max by (k8s_pod_name) (paddleocr_pending_pages))` read
from the cluster's Prometheus: replicas = ceil(pending pages / `pagesPerReplica`, 400 by
default), between `minReplicas` and `maxReplicas`. Scale-up adds up to two pods a minute;
scale-down waits 15 minutes of low backlog and then removes one pod per five minutes,
because a fresh pod takes about ten minutes to serve. Karpenter provisions and removes the
GPU nodes underneath. The pod carries `karpenter.sh/do-not-disrupt` so consolidation never
evicts a busy pod, a 15-minute termination grace period, and Triton and vLLM run as native
sidecars so a terminating pod stops the gateway first and its engines last: requests in
flight finish before the pod goes. `maxReplicas` is bounded by the account's G-instance
vCPU quota (32 vCPU = four g6.2xlarge) and the node pool limits, not by the chart.

## Autoscaling signal

`GET /api/metrics` is a Prometheus endpoint, scraped every 15 s by Porter through the
`metricsScraping` block in `porter.yaml`:

```
paddleocr_pending_pages 1240
paddleocr_pending_chunks 25
paddleocr_active_jobs 3
paddleocr_jobs_total{status="done"} 41
paddleocr_jobs_total{status="failed"} 1
paddleocr_draining 0
```

`paddleocr_pending_pages` counts pages in chunks that are queued or still running across
every unfinished job: work accepted but not finished. It is the input for scaling the
PaddleOCR pods, as replicas = ceil(pending_pages / pages each pod may leave waiting), which
a KEDA prometheus trigger against the cluster's Prometheus computes directly. GPU and CPU
utilisation are not usable signals for this stack (a saturated pod shows ~60% GPU and one
busy core), and Triton's queue counters only move once a pod is already full.

Sizing notes from the benchmark (`../paddleocr-bench`, results in the workstation
`weave-paddleocr-eval.md`): one L4 sustains 1.2 to 1.5 pages/s cold, so 50-page chunks with
2 to 3 in flight per pod keep the pod busy, and a 950-page document should be fanned across
several pods to finish in under 10 minutes.
