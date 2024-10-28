FROM python:3.9-slim

WORKDIR /app

COPY server.py .

EXPOSE 3000

CMD ["python", "server.py"]