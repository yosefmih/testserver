FROM python:3.9-slim

WORKDIR /app

COPY server.py .
COPY compute_pi.py .
COPY requirements.txt .

RUN pip install -r requirements.txt

EXPOSE 3000
EXPOSE 9090

CMD ["python", "server.py"]