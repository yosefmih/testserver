# Building and Deploying the Image

## Single Image Architecture

The Dockerfile uses a **multi-stage build** to create a single container image that includes:

1. **React Frontend** (built in Stage 1)
2. **FastAPI Backend** (Stage 2, serves API + frontend static files)

## Building the Image

### Local Build

```bash
cd testserver/scraper

# Build the image
docker build -t amharic-scraper:latest .

# Test locally
docker run -p 8080:8080 \
  -e S3_BUCKET=your-bucket \
  -e AWS_REGION=us-east-1 \
  amharic-scraper:latest
```

Then access:
- **UI**: http://localhost:8080/
- **API Docs**: http://localhost:8080/docs
- **Health**: http://localhost:8080/health

### Build for Registry

```bash
# Tag for your registry
docker build -t your-registry/amharic-scraper:v1.0.0 .

# Push to registry
docker push your-registry/amharic-scraper:v1.0.0
```

## How It Works

### Multi-Stage Build Process

**Stage 1: Frontend Builder**
```dockerfile
FROM node:18-alpine AS frontend-builder
# Installs npm dependencies
# Builds React app with Vite
# Output: /frontend/dist/ directory
```

**Stage 2: Final Image**
```dockerfile
FROM python:3.9-slim
# Installs Python dependencies
# Copies Python code
# Copies built frontend from Stage 1 to /app/static/
# FastAPI serves both API and frontend
```

### Runtime Behavior

When the container starts:

1. **Uvicorn starts** on port 8080
2. **FastAPI serves**:
   - `/` → React app (`/app/static/index.html`)
   - `/static/*` → Frontend assets (JS, CSS, etc.)
   - `/api/*` → Backend API endpoints
   - `/docs` → Swagger UI
   - `/health` → Health check

All from a **single process** in a **single container**!

## Kubernetes Deployment

### ConfigMap for Environment

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: scraper-config
data:
  AWS_REGION: "us-east-1"
  S3_BUCKET: "your-bucket-name"
  SERVER_PORT: "8080"
  # ... other config
```

### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: amharic-scraper
spec:
  replicas: 2
  selector:
    matchLabels:
      app: amharic-scraper
  template:
    metadata:
      labels:
        app: amharic-scraper
    spec:
      serviceAccountName: amharic-scraper  # For Pod Identity
      containers:
      - name: scraper
        image: your-registry/amharic-scraper:v1.0.0
        ports:
        - containerPort: 8080
        envFrom:
        - configMapRef:
            name: scraper-config
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

### Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: amharic-scraper
spec:
  selector:
    app: amharic-scraper
  ports:
  - port: 80
    targetPort: 8080
  type: ClusterIP
```

## Image Size Optimization

The multi-stage build keeps the image small:

- **Stage 1** (node:18-alpine): ~200MB (discarded)
- **Final image** (python:3.9-slim): ~350-400MB
  - Python runtime: ~150MB
  - Python packages: ~100MB
  - Built frontend: ~2-5MB
  - Application code: ~1MB

Frontend is built and optimized (minified, tree-shaken) before being added to the final image.

## Build Arguments (Optional)

You can add build args for flexibility:

```dockerfile
ARG NODE_VERSION=18
ARG PYTHON_VERSION=3.9

FROM node:${NODE_VERSION}-alpine AS frontend-builder
# ...

FROM python:${PYTHON_VERSION}-slim
# ...
```

Then build with:
```bash
docker build \
  --build-arg NODE_VERSION=20 \
  --build-arg PYTHON_VERSION=3.11 \
  -t amharic-scraper:latest .
```

## Verification

After building, verify the image:

```bash
# Check image size
docker images amharic-scraper:latest

# Inspect layers
docker history amharic-scraper:latest

# Run and check logs
docker run -p 8080:8080 \
  -e S3_BUCKET=test-bucket \
  -e AWS_REGION=us-east-1 \
  amharic-scraper:latest

# In another terminal, test endpoints
curl http://localhost:8080/health
curl http://localhost:8080/  # Should return HTML
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build and Push Image

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Login to Registry
        uses: docker/login-action@v2
        with:
          registry: your-registry.com
          username: ${{ secrets.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}
      
      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: testserver/scraper
          push: true
          tags: |
            your-registry/amharic-scraper:${{ github.ref_name }}
            your-registry/amharic-scraper:latest
          cache-from: type=registry,ref=your-registry/amharic-scraper:latest
          cache-to: type=inline
```

## Troubleshooting

### Build Fails at Frontend Stage

```bash
# Check if package.json exists
ls -la frontend/package.json

# Try building frontend locally first
cd frontend
npm install
npm run build
```

### Container Starts but UI Not Loading

```bash
# Check if static files were copied
docker run --rm amharic-scraper:latest ls -la /app/static/

# Should see: index.html, assets/, etc.
```

### High Memory Usage

- Consider using `--workers 1` (already default)
- Adjust `MAX_CONCURRENT_JOBS` in config
- Set appropriate K8s resource limits

## Best Practices

1. **Tag Images Properly**: Use semantic versioning (v1.0.0)
2. **Security Scanning**: Scan images before deployment
3. **Resource Limits**: Set appropriate CPU/memory limits in K8s
4. **Health Checks**: Already configured in Dockerfile
5. **Log Aggregation**: FastAPI logs to stdout (K8s compatible)
6. **Secrets Management**: Use K8s secrets for sensitive data, never in image

## Alternative: Separate Containers (Not Recommended)

If you ever need to separate them:

**Frontend Container:**
- nginx serving React build
- Routes `/api/*` to backend service

**Backend Container:**
- Only FastAPI

But this is more complex and unnecessary for this use case. **Single container is better** for:
- Simpler deployment
- No service mesh needed
- Lower latency (no network hop)
- Easier development/testing
- Lower resource usage

