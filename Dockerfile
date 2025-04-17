FROM python:3.9-slim-bullseye

WORKDIR /app

COPY server.py .
COPY client.py .
COPY linkerd_test.py .
COPY compute_pi.py .
COPY requirements.txt .
COPY large_file.dat .
COPY ooms.py .

RUN pip install -r requirements.txt

EXPOSE 3000
EXPOSE 9090

ARG RUN_FILE
RUN echo "RUN_FILE is set to $RUN_FILE"

# Declare the pass-through token as a build argument
ARG PORTER_PASS_THOUGH_GITHUB_TOKEN
# Log the value during build (will appear in build logs)
RUN echo "PORTER_PASS_THOUGH_GITHUB_TOKEN during build: ${PORTER_PASS_THOUGH_GITHUB_TOKEN:-not set}"

CMD ["python", "server.py"]