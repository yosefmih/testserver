# Multi-stage build for C audio worker - Kubernetes deployment
FROM alpine:3.19 AS builder

# Install build dependencies
RUN apk add --no-cache \
    build-base \
    gcc \
    make \
    pkgconfig \
    hiredis-dev \
    json-c-dev

# Set working directory
WORKDIR /app

# Copy source files
COPY Makefile ./
COPY src/ ./src/
COPY include/ ./include/

# Build optimized for Linux AMD64
RUN make clean && make release

# Production stage - minimal runtime for Kubernetes
FROM alpine:3.19

# Metadata for Kubernetes deployment
LABEL org.opencontainers.image.title="Audio Worker C" \
      org.opencontainers.image.description="High-performance C audio processing worker for Kubernetes" \
      org.opencontainers.image.version="1.0.0"

# Install runtime dependencies
RUN apk add --no-cache \
    hiredis \
    json-c \
    libgcc

# Create non-root user for security
RUN addgroup -g 1001 audioworker && \
    adduser -u 1001 -G audioworker -s /bin/sh -D audioworker

# Copy binary from builder
COPY --from=builder /app/build/audio_worker /usr/local/bin/audio_worker
RUN chmod +x /usr/local/bin/audio_worker

# Switch to non-root user
USER audioworker
WORKDIR /home/audioworker

# Health check for Kubernetes
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD audio_worker --version || exit 1

# Environment variables (same as Python version)
ENV REDIS_HOST="" \
    REDIS_PORT="6379" \
    REDIS_PASS="" \
    REDIS_URL=""

# Default: run continuously like Python worker
CMD ["audio_worker", "--verbose", "--duration", "0", "--timeout", "5"]