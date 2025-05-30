# ---- Build Stage ----
# Using a specific Python version and OS release (Debian Bullseye) for reproducibility. Good.
# 'AS builder' names this stage, which is used later.
FROM python:3.10-bullseye AS builder

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
FROM python:3.9-slim-bullseye

# Install ffmpeg, which is needed by pydub for MP3 processing
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory for the runtime stage.
WORKDIR /app

# Copy only the pre-built wheels from the builder stage.
# This is a key benefit of multi-stage builds.
COPY --from=builder /app/wheels /app/wheels

# Install dependencies from the local wheelhouse.
# - '--no-index' tells pip not to look at PyPI.
# - '--find-links=/app/wheels' directs pip to use the wheels we just copied.
# This step is fast and doesn't require any build tools in the final image.
# Crucially, remove the /app/wheels directory after installation to save space.
RUN pip install --no-cache-dir --no-index --find-links=/app/wheels -r requirements.txt \
    && rm -rf /app/wheels

# Copy application code.
# CONSIDERATION: Only copy files essential for running the application.
# Are all these files needed for the server/worker to run in production?
# Files like client.py, linkerd_test.py, compute_pi.py, large_file.dat,
# ooms.py, mining_simulator.py, web_scraper.py might be for testing or other utilities.
# If they are not needed at runtime, removing them will make the image smaller and more secure.
COPY server.py .
COPY audio_worker.py . # Assuming audio_worker is also run, perhaps in a different container/CMD
# COPY client.py .
# COPY linkerd_test.py .
# COPY compute_pi.py .
# COPY large_file.dat . # Large data files should generally not be in images if possible.
# COPY ooms.py .
# COPY mining_simulator.py .
# COPY web_scraper.py .

# EXPOSE informs Docker that the container listens on these network ports at runtime.
# It's good documentation. The actual publishing is done with 'docker run -p'.
# Your server.py seems to default to port 3000 or use SERVER_PORT.
EXPOSE 3000
# What is port 9090 used for? If not used by server.py or audio_worker.py, it could be removed.
EXPOSE 9090

# ARG allows passing variables at build-time (docker build --build-arg RUN_FILE=...).
ARG RUN_FILE
# This RUN command just echoes the value during the build process, it's for debugging build args.
RUN echo "RUN_FILE is set to ${RUN_FILE:-server.py}" # Added a default for clarity in the log

# ARG for GitHub token.
ARG PORTER_PASS_THOUGH_GITHUB_TOKEN
# Logging the token during build means it appears in build logs. Be mindful of sensitive tokens.
# For pip installing from private GitHub repos, consider using SSH keys with BuildKit secrets for better security.
RUN echo "PORTER_PASS_THOUGH_GITHUB_TOKEN during build: ${PORTER_PASS_THOUGH_GITHUB_TOKEN:-not set}"

# CMD specifies the default command to run when the container starts.
# This is set to run server.py.
# If you want to run audio_worker.py, you'd typically:
# 1. Build two different images from this Dockerfile using the RUN_FILE ARG and change CMD to use it:
#    CMD ["python", "${RUN_FILE:-server.py}"]
#    Then build with: docker build --build-arg RUN_FILE=audio_worker.py -t myapp-worker .
# 2. Or, use a process manager like 'supervisor' if both must run in one container (less common for scaling).
CMD ["python", "server.py"]