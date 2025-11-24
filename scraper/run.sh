#!/bin/bash
# Quick start script for Amharic Scraper Service

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "Warning: .env file not found. Please create one from .env.example"
    exit 1
fi

# Check Python version
python3 --version

# Install dependencies if needed
echo "Checking dependencies..."
pip install -q -r requirements.txt

# Start server
echo "Starting Amharic Scraper Service with uvicorn..."
echo "Server will be available at http://${SERVER_HOST:-0.0.0.0}:${SERVER_PORT:-8080}"
echo "API docs will be available at http://${SERVER_HOST:-0.0.0.0}:${SERVER_PORT:-8080}/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

uvicorn server:app --host ${SERVER_HOST:-0.0.0.0} --port ${SERVER_PORT:-8080} --reload

