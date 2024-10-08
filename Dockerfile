# Use an official Python runtime as the base image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the Python script and HTML file into the container
COPY server.py .
COPY index.html .

# Make port 8000 available outside the container
EXPOSE 8000

# Run the Python script when the container launches
CMD ["python", "server.py"]