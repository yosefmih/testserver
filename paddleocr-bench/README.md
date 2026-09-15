# paddleocr-bench

Benchmark harness for a self-hosted PaddleOCR-VL service. Upload a PDF, pick how
many pages go in each request and how many requests run concurrently, and the app
splits the PDF, sends every chunk to PaddleOCR, stores the markdown, JSON, and
figure images, and reports pages per second and request latency. This mirrors
the production shape a Celery worker would use: object storage in, OCR over HTTP,
object storage out.

```
browser ──upload──▶ paddleocr-bench ──PDF chunks + results──▶ S3 (or local dir)
                          │
                          └── POST /layout-parsing (presigned URL or base64) ──▶ paddleocr-vl-api ──▶ paddleocr-vlm (vLLM)
```

## Run locally without a GPU

`cmd/fakeocr` imitates the `/layout-parsing` endpoint with a fixed per-page delay.

```bash
export GOWORK=off
go run ./cmd/fakeocr &                                    # :8118, 0.3 s/page
PADDLEOCR_URL=http://localhost:8118 go run .              # :8096, stores under ./data
open http://localhost:8096
```

Without `S3_BUCKET` the app uses `LOCAL_DATA_DIR` and only base64 delivery works,
because there is nothing to presign.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `8096` | Listen port |
| `PADDLEOCR_URL` | `http://localhost:8080` | Base URL of the PaddleOCR-VL pipeline service |
| `OCR_TIMEOUT` | `15m` | Per-request timeout to PaddleOCR |
| `S3_BUCKET` | unset | Bucket for inputs, chunks, results, and job manifests |
| `S3_PREFIX` | `paddleocr-bench` | Key prefix inside the bucket |
| `AWS_REGION` | from the SDK chain | Credentials come from the default chain (env, pod identity, profile) |
| `LOCAL_DATA_DIR` | `./data` | Used only when `S3_BUCKET` is unset |
| `PRESIGN_TTL` | `1h` | Lifetime of the presigned chunk URLs handed to PaddleOCR |
| `DEFAULT_CHUNK_PAGES` | `10` | Form default for pages per request |
| `DEFAULT_CONCURRENCY` | `4` | Form default for concurrent requests |

## What gets stored

```
<prefix>/jobs/<job id>/job.json              manifest with per-chunk timings
<prefix>/jobs/<job id>/input.pdf
<prefix>/jobs/<job id>/chunks/<n>/input.pdf  the page range sent to OCR
<prefix>/jobs/<job id>/chunks/<n>/result.md  markdown for those pages
<prefix>/jobs/<job id>/chunks/<n>/result.json  prunedResult per page
<prefix>/jobs/<job id>/chunks/<n>/imgs/...   figures referenced from the markdown
```

Jobs run one at a time so a benchmark has the OCR service to itself. The job
page auto-refreshes while running, and `/api/jobs/<id>` returns the manifest
plus computed metrics for scripting.

## Deploying

Two charts for PaddleOCR itself, both one pod per GPU with containers talking over
localhost. The bench app is a Porter app (`porter.yaml`) on CPU nodes.

- `deploy/paddleocr-vl`: basic serving. Two containers, vLLM and the `paddlex --serve`
  pipeline. The pipeline serves one request at a time (PaddleX queues every request through
  a single worker thread because Paddle Inference predictors are not thread-safe), so this
  tops out around 1.6 pages/s per L4 with large requests.
- `deploy/paddleocr-vl-hps`: high-performance serving, the production shape. Three
  containers: the FastAPI gateway (same `/layout-parsing` API), Triton running
  `pipeline.instances` copies of the pipeline with dynamic batching, and vLLM. Images are
  built from upstream `deploy/paddleocr_vl_docker/hps` with Kaniko and pushed to ECR (see the
  values file for tags). The values file carries the VRAM, RAM and CPU budget for three
  instances on a g6.2xlarge; each instance costs ~3.9 GiB VRAM, so vLLM runs at
  `gpu-memory-utilization: 0.42`.

1. Mirror the two upstream images into ECR. The source registry is in Baidu
   Cloud and the images are 8 to 15 GB. Tags follow `paddleocr<major>.<minor>`;
   the newest published pair is `paddleocr3.6-nvidia-gpu-offline`.
2. Create a GPU node group with compute capability 8.0 or higher (g5, g6, g6e;
   not g4dn) and at least 100 GB of node disk. One node is enough.
3. Install the chart, pinning it to that node group:

   ```bash
   helm upgrade --install paddleocr-vl deploy/paddleocr-vl \
     --kube-context <ctx> --namespace paddleocr --create-namespace \
     --set registry=<account>.dkr.ecr.<region>.amazonaws.com \
     --set nodeGroupId=<porter node group id>
   ```

   `pipeline.gpuMode` controls how the layout model gets a GPU. `shared`
   (default) lets the pipeline container see the GPU the vlm container
   requested through `NVIDIA_VISIBLE_DEVICES=all`. If the node's container
   toolkit refuses that, use `dedicated` (a second GPU) or `cpu`.
4. Deploy this app with `PADDLEOCR_URL` set to the chart's in-cluster service,
   `http://paddleocr-vl.paddleocr.svc.cluster.local:8080`, and an S3 bucket the
   pod can read and write.

## Benchmark knobs worth sweeping

- Pages per request: PaddleOCR renders every page of a chunk before recognising
  any, so small chunks pipeline better but pay more HTTP overhead.
- Concurrency: vLLM batches across requests, so throughput should rise with
  concurrency until the GPU saturates. The pipeline service handles one request
  at a time unless deployed with the high-performance serving stack.
- Delivery: presigned URL keeps request bodies tiny; base64 measures the cost of
  pushing bytes through the pipeline service.
- Keep figure images: off to measure pure text throughput.
