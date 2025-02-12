FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

# Install python and pip
RUN apt-get update && apt-get install -y \
    python3.9 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY server.py .
COPY compute_pi.py .
COPY gpu_benchmark.py .
COPY requirements.txt .

# Install PyTorch with CUDA support
RUN pip3 install --no-cache-dir -r requirements.txt

EXPOSE 3000
EXPOSE 9090

ARG RUN_FILE
RUN echo "RUN_FILE is set to $RUN_FILE"

# Set environment variable to enable CUDA
ENV NVIDIA_VISIBLE_DEVICES all
ENV NVIDIA_DRIVER_CAPABILITIES compute,utility

CMD ["python3", "server.py"]