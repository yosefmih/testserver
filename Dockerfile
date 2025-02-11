FROM python:3.9-slim

WORKDIR /app

COPY server.py .
COPY compute_pi.py .
COPY requirements.txt .

RUN pip install -r requirements.txt

EXPOSE 3000
EXPOSE 9090

RUN echo "RUN_FILE is set to $RUN_FILE"

CMD ["python", "server.py"]