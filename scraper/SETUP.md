# Amharic Scraper Setup Guide

## Quick Start

### 1. Install Dependencies

```bash
cd testserver/scraper
pip install -r requirements.txt
```

### 2. Configure Environment

#### Option A: Local Development (with AWS credentials)

Create a `.env` file with your AWS credentials:

```bash
# Create .env file
cat > .env << EOF
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
AWS_REGION=us-east-1
S3_BUCKET=your-bucket-name
EOF
```

#### Option B: EKS Deployment (with Pod Identity)

For EKS deployment, see [EKS_DEPLOYMENT.md](EKS_DEPLOYMENT.md) for detailed instructions.

No AWS credentials needed in `.env`:
```bash
# Create .env file
cat > .env << EOF
AWS_REGION=us-east-1
S3_BUCKET=your-bucket-name
EOF
```

The service will automatically use the IAM role attached to the pod.

**Note:** The service automatically detects whether to use IAM roles or access keys:
- If `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are set → uses access keys
- If they're not set → uses IAM role (EKS Pod Identity/IRSA)

### 3. Create S3 Bucket

Make sure your S3 bucket exists and your AWS credentials have the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket-name",
        "arn:aws:s3:::your-bucket-name/*"
      ]
    }
  ]
}
```

### 4. Start the Server

**Option A: Using the run script (with hot reload)**
```bash
./run.sh
```

**Option B: Using uvicorn directly**
```bash
uvicorn server:app --host 0.0.0.0 --port 8080
```

**Option C: For production**
```bash
uvicorn server:app --host 0.0.0.0 --port 8080 --workers 4
```

The server will start on `http://localhost:8080`

**Interactive API Docs:**
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

### 5. Test the API

In another terminal, test with the example client:

```bash
python3 example_client.py
```

Or use curl:

```bash
# Health check
curl http://localhost:8080/health

# Create a job
curl -X POST http://localhost:8080/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "seed_urls": ["https://en.wikipedia.org/wiki/Amharic"],
    "config": {
      "max_depth": 2,
      "max_pages": 20,
      "amharic_threshold": 0.2
    }
  }'

# Check job status (replace with your job ID)
curl http://localhost:8080/api/jobs/YOUR-JOB-ID
```

## Configuration Options

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | Yes | - | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Yes | - | AWS secret key |
| `AWS_REGION` | No | us-east-1 | AWS region |
| `S3_BUCKET` | Yes | - | S3 bucket name |
| `S3_METADATA_KEY` | No | scraper-metadata/jobs.json | Metadata file path |
| `S3_DATA_PREFIX` | No | scraper-data | Data storage prefix |
| `SERVER_HOST` | No | 0.0.0.0 | Server bind address |
| `SERVER_PORT` | No | 8080 | Server port |
| `MAX_CONCURRENT_JOBS` | No | 3 | Max parallel jobs |
| `WORKER_THREADS` | No | 5 | Worker threads per job |
| `DEFAULT_RATE_LIMIT` | No | 2.0 | Default rate limit (seconds) |
| `DEFAULT_MAX_DEPTH` | No | 3 | Default crawl depth |
| `DEFAULT_MAX_PAGES` | No | 1000 | Default max pages |
| `DEFAULT_AMHARIC_THRESHOLD` | No | 0.3 | Default Amharic threshold |

### Job Configuration

When creating a job, you can override defaults:

```json
{
  "seed_urls": ["https://example.com"],
  "config": {
    "max_depth": 3,           // Maximum link depth to follow
    "max_pages": 500,         // Maximum pages to scrape
    "rate_limit": 2.0,        // Seconds between requests per domain
    "timeout": 10,            // HTTP request timeout
    "same_domain_only": true, // Only follow links on same domain
    "amharic_threshold": 0.3  // Minimum Amharic % (0.0-1.0)
  }
}
```

## Understanding Amharic Detection

The scraper detects Amharic using Unicode Ethiopic script ranges:

- **ሀ-፼** (U+1200 to U+137F) - Core Ethiopic
- **ᎀ-Ᏽ** (U+1380 to U+139F) - Ethiopic Supplement
- **ⶀ-⷟** (U+2D80 to U+2DDF) - Ethiopic Extended

### Threshold Examples

- `0.1` (10%) - Very permissive, includes pages with small Amharic snippets
- `0.3` (30%) - Balanced, good for mixed content sites
- `0.5` (50%) - Strict, only predominantly Amharic pages
- `0.8` (80%) - Very strict, almost pure Amharic content

## Monitoring Jobs

### Job Lifecycle

1. **queued** - Job created, waiting for worker
2. **running** - Actively scraping pages
3. **completed** - Finished successfully
4. **failed** - Encountered an error
5. **cancelled** - User cancelled the job

### Progress Tracking

Poll the status endpoint to track progress:

```bash
watch -n 2 "curl -s http://localhost:8080/api/jobs/YOUR-JOB-ID | jq"
```

Key metrics:
- `pages_scraped` - Total pages processed
- `pages_amharic` - Pages that passed Amharic threshold
- `queue_size` - URLs remaining to process
- `current_url` - Currently scraping URL
- `elapsed_seconds` - Time elapsed

## S3 Output Structure

### Text Files

```
s3://your-bucket/scraper-data/
  └── {job-id}/
      ├── abc123...def.txt  (URL hash)
      ├── 789xyz...456.txt
      └── ...
```

Each file contains:
- Plain text (HTML removed)
- UTF-8 encoded
- Metadata in S3 object properties

### Metadata File

```
s3://your-bucket/scraper-metadata/jobs.json
```

Contains all job metadata in JSON format.

## Troubleshooting

### "Missing required configuration"

Make sure `.env` file exists and contains all required variables:
```bash
cat .env | grep -E "AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|S3_BUCKET"
```

### "Worker pool is full"

The server has reached maximum concurrent jobs. Either:
- Wait for jobs to complete
- Increase `MAX_CONCURRENT_JOBS` in `.env`
- Cancel some running jobs

### S3 Access Denied

Check:
1. AWS credentials are correct
2. Bucket exists in the specified region
3. IAM user/role has PutObject and GetObject permissions

### No Amharic Text Found

If pages aren't being saved:
1. Verify target sites actually contain Amharic text
2. Lower the `amharic_threshold` (try 0.1)
3. Check the job progress - pages may be scraped but not Amharic

### Connection Refused

Make sure the server is running:
```bash
curl http://localhost:8080/health
```

If not running, start it:
```bash
python3 server.py
```

## Production Deployment

### Using systemd (Linux)

Create `/etc/systemd/system/amharic-scraper.service`:

```ini
[Unit]
Description=Amharic Web Scraper Service
After=network.target

[Service]
Type=simple
User=scraper
WorkingDirectory=/opt/amharic-scraper
EnvironmentFile=/opt/amharic-scraper/.env
ExecStart=/usr/bin/python3 /opt/amharic-scraper/server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable amharic-scraper
sudo systemctl start amharic-scraper
```

### Using Docker

Create `Dockerfile` in the scraper directory:

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
CMD ["python", "server.py"]
```

Build and run:
```bash
docker build -t amharic-scraper .
docker run -d -p 8080:8080 --env-file .env amharic-scraper
```

## Performance Tips

1. **Rate Limiting**: Respect target websites - use 2-5 seconds between requests
2. **Worker Count**: More workers = more concurrent jobs, but more memory
3. **Max Pages**: Limit pages to avoid long-running jobs
4. **Same Domain**: Enable to stay focused on target sites
5. **Depth Limit**: Lower depth (1-2) for faster, focused crawls

## Best Practices

1. **Test First**: Start with small jobs (max_pages: 10-20) to test
2. **Monitor Progress**: Watch the first few jobs to tune parameters
3. **Respect Robots.txt**: The scraper honors robots.txt automatically
4. **Rate Limiting**: Use appropriate delays to avoid overwhelming sites
5. **Error Handling**: Check failed jobs and adjust configuration
6. **Storage**: Monitor S3 usage, especially for large scraping projects

## Support

For issues or questions:
1. Check the logs in the terminal where server.py is running
2. Review the job error field in the status response
3. Verify AWS credentials and S3 permissions
4. Test with small jobs first to isolate issues

