# Heavy Dockerfiles

Dockerfiles designed to stress-test a BuildKit-based Docker builder. Each targets a different build profile.

## Build Times (approx, no cache, single machine)

- **Dockerfile.opencv** — OpenCV + contrib from source (~15-25 min). CPU-heavy C++ compilation.
- **Dockerfile.ffmpeg** — FFmpeg with x264/x265/VP9/AV1 from source (~20-30 min). Multiple serial dependency compilations.
- **Dockerfile.python-ml** — Full ML stack: PyTorch, transformers, scikit-learn, etc (~10-15 min). Large downloads + wheel builds.
- **Dockerfile.node-monorepo** — Simulated large JS monorepo with 50 generated modules, Playwright, MUI, Three.js (~5-10 min). Tests npm install throughput.
- **Dockerfile.rust-ripgrep** — Ripgrep from source via cargo (~8-12 min). Full Rust compilation pipeline.
- **Dockerfile.go-k8s-tools** — Compiles kind, k9s, stern, logcli, promtool from source (~10-15 min). Many large Go module downloads.
- **Dockerfile.gcc** — GCC 13 from source (~30-60 min). The nuclear option.
- **Dockerfile.llvm** — LLVM/Clang 17 from source (~25-45 min). Massive C++ codebase with Ninja.

## Usage

```bash
# Build a specific one
docker build -f Dockerfile.opencv -t test-opencv .

# Or with your builder CLI
builder build -f Dockerfile.gcc .
```

All Dockerfiles are self-contained with no local file dependencies (they fetch sources from the internet).
