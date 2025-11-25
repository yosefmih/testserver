# Quick Start Guide

Get the Amharic Web Scraper running in 5 minutes!

## Prerequisites

- Python 3.9+
- Node.js 18+ and npm
- AWS credentials (or EKS Pod Identity)
- S3 bucket

## Step 1: Backend Setup

```bash
# Navigate to scraper directory
cd testserver/scraper

# Install Python dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Edit .env and add your AWS credentials and S3 bucket
# For local dev:
#   AWS_ACCESS_KEY_ID=xxx
#   AWS_SECRET_ACCESS_KEY=xxx
#   S3_BUCKET=your-bucket-name

# Start backend server
uvicorn server:app --host 0.0.0.0 --port 8080
```

Backend will be available at http://localhost:8080

## Step 2: Frontend Setup (Development)

In a new terminal:

```bash
# Navigate to frontend directory
cd testserver/scraper/frontend

# Install dependencies (first time only)
npm install

# Start React dev server
npm run dev
```

Frontend will be available at http://localhost:3000

## Step 3: Use the App

1. Open http://localhost:3000 in your browser
2. Enter seed URLs (one per line)
3. Configure scraping parameters
4. Click "Start Scraping"
5. Watch progress in real-time!

## Production Deployment

### Build Frontend

```bash
cd frontend
npm run build
```

This builds the React app to `../static/` directory.

### Run Backend

```bash
uvicorn server:app --host 0.0.0.0 --port 8080 --workers 4
```

Now visit http://localhost:8080 - the backend serves the built React app!

### Docker

```bash
# Build image
docker build -t amharic-scraper .

# Run container
docker run -p 8080:8080 \
  -e S3_BUCKET=your-bucket \
  -e AWS_REGION=us-east-1 \
  amharic-scraper
```

### EKS/Kubernetes

See [EKS_DEPLOYMENT.md](EKS_DEPLOYMENT.md) for detailed Kubernetes deployment with Pod Identity.

## Quick Test

### Using the UI

1. Enter a test URL: `https://en.wikipedia.org/wiki/Amharic`
2. Set max_pages to `10`
3. Set amharic_threshold to `0.1` (lower for testing)
4. Click "Start Scraping"
5. Watch the job progress!

### Using curl

```bash
# Create a job
curl -X POST http://localhost:8080/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "seed_urls": ["https://en.wikipedia.org/wiki/Amharic"],
    "config": {
      "max_pages": 10,
      "amharic_threshold": 0.1
    }
  }'

# Get job status (replace JOB_ID)
curl http://localhost:8080/api/jobs/JOB_ID
```

## Troubleshooting

### Backend won't start

- Check Python version: `python --version` (need 3.9+)
- Verify .env file exists and has correct values
- Check S3 bucket exists and credentials work

### Frontend won't start

- Check Node version: `node --version` (need 18+)
- Run `npm install` in frontend directory
- Make sure backend is running on port 8080

### No Amharic text found

- Lower the `amharic_threshold` (try 0.1)
- Check if target websites actually have Amharic text
- View job details to see what's happening

### CORS errors in browser

- Make sure you're accessing frontend via localhost:3000 (dev)
- Or build and serve via backend at localhost:8080 (prod)
- Don't access frontend as file:// URLs

## Architecture

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       ↓ (Development)
┌─────────────┐      Proxy      ┌─────────────┐
│  React Dev  │ ─────────────→  │   FastAPI   │
│  Port 3000  │   /api/*        │   Port 8080 │
└─────────────┘                 └──────┬──────┘
                                       │
                                       ↓
                                 ┌─────────┐
                                 │   S3    │
                                 └─────────┘

       ↓ (Production)
┌─────────────┐
│   FastAPI   │ ← Serves React build + API
│   Port 8080 │
└──────┬──────┘
       │
       ↓
 ┌─────────┐
 │   S3    │
 └─────────┘
```

## Next Steps

- Read [README.md](README.md) for full documentation
- Check [SETUP.md](SETUP.md) for detailed configuration
- Review [EKS_DEPLOYMENT.md](EKS_DEPLOYMENT.md) for Kubernetes

## Support

Check logs in terminal where backend is running for detailed error messages.

Happy scraping! 🚀

