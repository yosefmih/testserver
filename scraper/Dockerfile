# =============================================================================
# Stage 1: Build React Frontend
# =============================================================================
FROM node:18-alpine AS frontend-builder

WORKDIR /frontend

# Copy package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy frontend source code
COPY frontend/ ./

# Build for production
RUN npm run build

# =============================================================================
# Stage 2: Python Backend with Frontend Static Files
# =============================================================================
FROM python:3.9-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python application code
COPY *.py ./

# Copy built frontend from Stage 1
COPY --from=frontend-builder /frontend/dist ./static

# Create non-root user
RUN useradd -m -u 1000 scraper && \
    chown -R scraper:scraper /app

# Switch to non-root user
USER scraper

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=2)" || exit 1

# Run server with uvicorn (single worker for simplicity, can be scaled via K8s)
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]

