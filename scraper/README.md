# Amharic Web Scraper Service

A RESTful web scraping service that crawls websites and extracts Amharic text content, storing it in S3.

## Features

- 🌐 **HTTP API** - Submit scraping jobs via REST API
- 📊 **Job Tracking** - Monitor job progress and status
- 🔤 **Amharic Detection** - Automatically detects and filters Amharic text using Unicode Ethiopic script
- ☁️ **S3 Storage** - Saves scraped text to AWS S3
- 🔄 **Concurrent Jobs** - Process multiple scraping jobs in parallel
- 🤖 **Respectful Crawling** - Honors robots.txt and implements rate limiting
- 📝 **Metadata Management** - Single JSON file in S3 for job state tracking

## Architecture

```
Client → Flask Server → Job Manager → Worker Pool → Scraper Engine
                          ↓                            ↓
                    S3 Metadata Store            S3 Text Storage
```

## Installation

### Local Development

1. Navigate to the scraper directory:
```bash
cd testserver/scraper
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
# For local development with AWS credentials
cat > .env << EOF
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
S3_BUCKET=your-bucket-name
EOF
```

### EKS Deployment

For production deployment on Amazon EKS with Pod Identity, see [EKS_DEPLOYMENT.md](EKS_DEPLOYMENT.md).

## Configuration

### Authentication Methods

The service supports two authentication methods:

1. **AWS Access Keys** (local development):
   - Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
   
2. **EKS Pod Identity/IRSA** (production):
   - Leave access keys unset
   - Attach IAM role to service account
   - Service automatically uses pod's IAM role

### Required Environment Variables

- `S3_BUCKET` - S3 bucket name for storage (required)
- `AWS_REGION` - AWS region (default: us-east-1)

### Optional Environment Variables

- `AWS_ACCESS_KEY_ID` - AWS access key (not needed for EKS Pod Identity)
- `AWS_SECRET_ACCESS_KEY` - AWS secret key (not needed for EKS Pod Identity)

Optional configuration:

- `SERVER_PORT` - Server port (default: 8080)
- `MAX_CONCURRENT_JOBS` - Maximum parallel jobs (default: 3)
- `DEFAULT_MAX_DEPTH` - Default crawl depth (default: 3)
- `DEFAULT_MAX_PAGES` - Default max pages per job (default: 1000)
- `DEFAULT_AMHARIC_THRESHOLD` - Minimum Amharic % (default: 0.3)

## Usage

### Starting the Server

```bash
python server.py
```

The server will start on `http://localhost:8080` by default.

### API Endpoints

#### 1. Create Scraping Job

**POST** `/api/scrape`

Submit a new scraping job with seed URLs and configuration.

```bash
curl -X POST http://localhost:8080/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "seed_urls": [
      "https://ethiopianews.com",
      "https://example-amharic-site.com"
    ],
    "config": {
      "max_depth": 2,
      "max_pages": 100,
      "rate_limit": 2.0,
      "timeout": 10,
      "same_domain_only": true,
      "amharic_threshold": 0.3
    }
  }'
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2025-11-24T10:30:00.000000"
}
```

#### 2. Check Job Status

**GET** `/api/jobs/{job_id}`

Get current status and progress of a scraping job.

```bash
curl http://localhost:8080/api/jobs/550e8400-e29b-41d4-a716-446655440000
```

Response:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "seed_urls": ["https://ethiopianews.com"],
  "config": {...},
  "created_at": "2025-11-24T10:30:00.000000",
  "started_at": "2025-11-24T10:30:05.000000",
  "completed_at": null,
  "progress": {
    "pages_scraped": 45,
    "pages_amharic": 12,
    "queue_size": 120,
    "current_url": "https://ethiopianews.com/page5"
  },
  "stats": {
    "total_bytes": 123456,
    "elapsed_seconds": 60.5
  },
  "error": null
}
```

Job statuses:
- `queued` - Job is waiting to start
- `running` - Job is currently being processed
- `completed` - Job finished successfully
- `failed` - Job encountered an error
- `cancelled` - Job was cancelled by user

#### 3. List All Jobs

**GET** `/api/jobs?limit=100`

List all scraping jobs (most recent first).

```bash
curl http://localhost:8080/api/jobs?limit=50
```

#### 4. Cancel Job

**DELETE** `/api/jobs/{job_id}`

Cancel a running or queued job.

```bash
curl -X DELETE http://localhost:8080/api/jobs/550e8400-e29b-41d4-a716-446655440000
```

#### 5. Health Check

**GET** `/health`

Check server health and active job count.

```bash
curl http://localhost:8080/health
```

## S3 Storage Structure

### Scraped Text Files

```
s3://your-bucket/scraper-data/{job_id}/{url_hash}.txt
```

Each text file contains:
- Pure text content (HTML removed)
- UTF-8 encoding
- Metadata stored in S3 object metadata

### Job Metadata

```
s3://your-bucket/scraper-metadata/jobs.json
```

Single JSON file containing all job metadata with optimistic locking for concurrent updates.

## Amharic Detection

The scraper uses Unicode Ethiopic script ranges to detect Amharic text:

- **U+1200 to U+137F** - Core Ethiopic
- **U+1380 to U+139F** - Ethiopic Supplement  
- **U+2D80 to U+2DDF** - Ethiopic Extended

Text is saved only if the percentage of Amharic characters exceeds the threshold (default: 30%).

## Configuration Options

### Job Config Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_depth` | int | 3 | Maximum crawl depth |
| `max_pages` | int | 1000 | Maximum pages to scrape |
| `rate_limit` | float | 2.0 | Seconds between requests per domain |
| `timeout` | int | 10 | Request timeout in seconds |
| `same_domain_only` | bool | true | Only follow links on same domain |
| `amharic_threshold` | float | 0.3 | Minimum Amharic percentage (0.0-1.0) |

## Development

### Project Structure

```
scraper/
├── server.py              # Flask HTTP server
├── job_manager.py         # Job lifecycle management
├── worker.py              # Background worker pool
├── scraper_engine.py      # Core scraping logic
├── amharic_detector.py    # Amharic language detection
├── text_processor.py      # HTML to text extraction
├── s3_storage.py          # S3 upload operations
├── s3_metadata.py         # S3 metadata management
├── url_utils.py           # URL utilities
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

### Testing

Test Amharic detection:
```python
from amharic_detector import AmharicDetector

detector = AmharicDetector(threshold=0.3)
is_amharic, pct, stats = detector.detect("ሰላም እንደምን አለህ")
print(f"Is Amharic: {is_amharic}, Percentage: {pct:.2%}")
```

## Troubleshooting

### Common Issues

1. **"Missing required configuration"**
   - Ensure all required environment variables are set in `.env`

2. **"Worker pool is full"**
   - Increase `MAX_CONCURRENT_JOBS` or wait for jobs to complete

3. **S3 Permission Errors**
   - Verify AWS credentials have S3 read/write permissions
   - Check bucket exists and is accessible

4. **Rate Limiting**
   - Increase `rate_limit` config if getting blocked by websites
   - Some sites may require more aggressive rate limiting

## License

MIT License - See LICENSE file for details

## Author

Built for Amharic text collection and corpus building.

