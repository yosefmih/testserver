FROM python:3.10-slim-bullseye

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    htop \
    strace \
    lsof \
    net-tools \
    curl \
    vim-tiny \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir celery[librabbitmq] memory-profiler psutil

COPY celery_app.py .
COPY trigger_tasks.py .
COPY start_worker.sh .

RUN chmod +x /app/start_worker.sh

CMD ["/app/start_worker.sh"]
