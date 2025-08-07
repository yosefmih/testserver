# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a test server repository containing multiple demonstration applications used to test a Platform-as-a-Service (PaaS) company's Kubernetes cluster and app-level interfaces. The repository serves as a collection of test workloads for validating the platform's functionality in customer accounts.

## Architecture

The repository follows a multi-app structure with several distinct applications:

### Core Applications

1. **Main Test Server** (`server.py`) - Python Flask server with comprehensive testing endpoints including health checks, CPU-intensive computations, memory testing, file operations, Redis integration, and audio processing
2. **Frontend App** (`frontend/`) - Next.js 15 application running on port 8091 with TypeScript support
3. **GitHub Release Crawler** (`github-release-crawler/`) - Monorepo containing:
   - Backend TypeScript service with Express server for analyzing GitHub releases
   - Frontend React/Vite app with Tailwind CSS
   - Slack notification microservice with PostgreSQL integration
   - All services include OpenTelemetry instrumentation for distributed tracing
4. **Stock Analysis Server** (`stockanalysis/`) - Node.js Express server for testing Kubernetes health checks and stock analysis
5. **Fibonacci Calculator** (`fibonacci/`) - Go module with iterative and recursive implementations

### Supporting Components

- **Porter YAML configurations** - Platform deployment configurations for various services
- **Dockerfiles** - Multi-architecture container builds (x86_64 and ARM64)
- **Python utilities** - Various test scripts for compute operations, AWS EC2 instance details, web scraping, etc.

## Development Commands

### Frontend (Next.js)
```bash
cd frontend/
npm run dev          # Development server on port 8091 with Turbopack
npm run build        # Production build
npm start            # Production server on port 8091
npm run lint         # ESLint
```

### GitHub Release Crawler
```bash
cd github-release-crawler/
npm run build        # TypeScript compilation
npm start            # Production server
npm run dev          # Development with ts-node
npm run lint         # ESLint
npm run typecheck    # TypeScript type checking
```

### GitHub Release Crawler Frontend
```bash
cd github-release-crawler/frontend-app/
npm run dev          # Vite development server
npm run build        # Production build
npm run preview      # Preview production build
npm run lint         # ESLint with strict warnings
npm run typecheck    # TypeScript type checking
```

### Slack Notification Service
```bash
cd github-release-crawler/slack-notification-service/
npm run build        # TypeScript compilation
npm start            # Production server
npm run dev          # Development with ts-node
npm run lint         # ESLint
npm run typecheck    # TypeScript type checking
```

### Stock Analysis Server
```bash
cd stockanalysis/
npm start            # Production server
npm run dev          # Development with nodemon
```

### Go Applications
```bash
cd fibonacci/
go run main.go <n>   # Calculate nth Fibonacci number
go mod tidy          # Clean up dependencies
```

### Python Applications
```bash
python server.py     # Main test server
python audio_worker.py    # Audio processing worker
python compute_pi.py      # Pi computation utility
pip install -r requirements.txt  # Install dependencies
```

## Technology Stack

- **Frontend**: Next.js 15, React 19, TypeScript, Tailwind CSS
- **Backend**: Node.js/Express, Python/Flask, Go
- **Databases**: PostgreSQL, Redis
- **Observability**: OpenTelemetry with OTLP exporters and Prometheus metrics
- **External APIs**: Anthropic AI SDK, Slack Web API, GitHub API
- **Containerization**: Docker with multi-architecture support
- **Platform**: Porter (Kubernetes PaaS)

## Key Architectural Patterns

- **Microservices Architecture**: Separate services for different concerns (notifications, analysis, frontend)
- **Distributed Tracing**: OpenTelemetry integration across all TypeScript services with traceparent header propagation
- **Health Check Endpoints**: All services implement `/health` endpoints for Kubernetes readiness/liveness probes
- **Environment-based Configuration**: Extensive use of environment variables and .env files
- **Multi-language Support**: Python, Node.js, TypeScript, and Go services coexisting

## Porter Platform Integration

The repository is designed to work with Porter, a Kubernetes PaaS platform:
- `porter.yaml` files define service configurations including scaling, resources, and domains
- Services are containerized and deployed to customer Kubernetes clusters
- Health checks and metrics endpoints are configured for platform monitoring
- Predeploy hooks execute compute tasks before service deployment

## Testing Applications

Each application serves specific testing purposes:
- **server.py**: Comprehensive load testing, memory/CPU stress testing, file I/O operations
- **stockanalysis/**: Basic health check validation and API response testing  
- **github-release-crawler**: Complex distributed system testing with multiple interconnected services
- **fibonacci/**: Simple compute workload testing with Go runtime
- **frontend/**: Modern React application deployment and performance testing