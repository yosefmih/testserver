# ---- Build Stage ----
# Using a specific Python version and OS release (Debian Bullseye) for reproducibility. Good.
# 'AS builder' names this stage, which is used later.
FROM python:3.13-bookworm AS builder

# Set the working directory in the container. Standard practice.
WORKDIR /app

# Install build dependencies.
# - 'apt-get update' and 'apt-get install' in one RUN layer is good for cache efficiency.
# - '--no-install-recommends' keeps the layer lean.
# - 'build-essential gfortran libopenblas-dev' are necessary for compiling packages like SciPy from source. Correct for a build stage.
# - 'rm -rf /var/lib/apt/lists/*' cleans up apt cache, reducing image size. Essential.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gfortran \
    libopenblas-dev \
    # psycopg2-binary usually doesn't need libpq-dev, but if building from source, it would.
    # libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file. This is done before pip commands to leverage Docker caching.
# If requirements.txt doesn't change, subsequent pip steps can be cached.
COPY requirements.txt .

# Create a wheelhouse for all dependencies.
# This pre-compiles all packages (including those with C extensions) into .whl files.
# '--no-cache-dir' for pip prevents caching, which is good for Docker image size.
# The wheels are stored in /app/wheels.
RUN pip wheel --no-cache-dir --wheel-dir=/app/wheels -r requirements.txt

# ---- Runtime Stage ----
# Using a 'slim' variant for the runtime image is a great optimization.
# It's much smaller as it doesn't include build tools or many development libraries.
FROM python:3.13-slim-bookworm

# Install ffmpeg, which is needed by pydub for MP3 processing
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory for the runtime stage.
WORKDIR /app

# Copy only the pre-built wheels from the builder stage.
# This is a key benefit of multi-stage builds.
COPY --from=builder /app/wheels /app/wheels

# Copy requirements.txt again for the runtime stage pip install
COPY requirements.txt .

# Install dependencies from the local wheelhouse.
# - '--no-index' tells pip not to look at PyPI.
# - '--find-links=/app/wheels' directs pip to use the wheels we just copied.
# This step is fast and doesn't require any build tools in the final image.
# Crucially, remove the /app/wheels directory after installation to save space.
RUN pip install --no-cache-dir --no-index --find-links=/app/wheels -r requirements.txt \
    && rm -rf /app/wheels

# Copy application code.
COPY server.py .
COPY server_ws.py .
# COPY client.py .
# COPY linkerd_test.py .
# COPY compute_pi.py .
# COPY ooms.py .
# COPY mining_simulator.py .
# COPY web_scraper.py .
# COPY audio_worker.py .
# COPY temporal_worker.py .
# COPY temporal_client.py .

# EXPOSE informs Docker that the container listens on these network ports at runtime.
# It's good documentation. The actual publishing is done with 'docker run -p'.
# Your server.py seems to default to port 3000 or use SERVER_PORT.
EXPOSE 3000
EXPOSE 8080
EXPOSE 9090

# === Build arg injection test ===
# ENV_A: set on Porter app as non-secret env var (no PORTER_ prefix)
# PORTER_ENV_A: set on Porter app as non-secret env var (has PORTER_ prefix)
# GHA_ONLY_VAR: set only in GHA workflow env block, not in Porter or --variables
# VARIABLES_FLAG_VAR: passed only via --variables flag

ARG ENV_A
ARG PORTER_ENV_A
ARG GHA_ONLY_VAR
ARG VARIABLES_FLAG_VAR

RUN echo "=== BUILD ARG TEST RESULTS ===" && \
    echo "ENV_A=${ENV_A:-NOT SET}" && \
    echo "PORTER_ENV_A=${PORTER_ENV_A:-NOT SET}" && \
    echo "GHA_ONLY_VAR=${GHA_ONLY_VAR:-NOT SET}" && \
    echo "VARIABLES_FLAG_VAR=${VARIABLES_FLAG_VAR:-NOT SET}" && \
    echo "=== END TEST RESULTS ==="

# CMD specifies the default command to run when the container starts.
# This is set to run server.py.
# If you want to run audio_worker.py, you'd typically:
# 1. Build two different images from this Dockerfile using the RUN_FILE ARG and change CMD to use it:
#    CMD ["python", "${RUN_FILE:-server.py}"]
#    Then build with: docker build --build-arg RUN_FILE=audio_worker.py -t myapp-worker .
# 2. Or, use a process manager like 'supervisor' if both must run in one container (less common for scaling).
CMD ["python", "server.py"]