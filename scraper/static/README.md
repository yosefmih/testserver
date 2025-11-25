# Web Frontend

This directory contains the web-based frontend for the Amharic Web Scraper.

## Features

- 📝 **Job Creation Form** - Submit scraping jobs with custom configuration
- 📊 **Jobs Dashboard** - View all jobs with real-time status updates
- 🔍 **Job Details Modal** - Inspect individual job progress and configuration
- ⚡ **Auto-Refresh** - Running jobs automatically update every 5 seconds
- 📱 **Responsive Design** - Works on desktop, tablet, and mobile

## Access

Once the server is running, access the frontend at:

```
http://localhost:8080/
```

## Usage

### Creating a Job

1. Enter seed URLs (one per line)
2. Configure scraping parameters:
   - **Max Depth**: How many levels deep to crawl
   - **Max Pages**: Maximum pages to scrape
   - **Rate Limit**: Delay between requests (in seconds)
   - **Timeout**: Request timeout
   - **Same Domain Only**: Restrict to seed URL domains
   - **Amharic Threshold**: Minimum Amharic percentage to save (0.0-1.0)
3. Click "Start Scraping"

### Monitoring Jobs

- Jobs appear in the dashboard with color-coded status:
  - 🟢 **Green** - Running
  - 🔵 **Blue** - Completed
  - 🔴 **Red** - Failed
  - 🟡 **Yellow** - Queued

- Click any job to view detailed information
- Running jobs show a progress bar
- Jobs auto-refresh every 5 seconds

### Job Statuses

- **queued** - Waiting to start
- **running** - Currently scraping
- **completed** - Finished successfully
- **failed** - Encountered an error
- **cancelled** - Manually stopped

## Development

The frontend is a single-page application (SPA) built with vanilla JavaScript. No build step required!

### File Structure

```
static/
├── index.html    # Complete SPA (HTML, CSS, JS)
└── README.md     # This file
```

### Customization

To customize the frontend:

1. Edit `index.html`
2. The API base URL is automatically set to `window.location.origin`
3. Refresh the browser to see changes

### API Integration

The frontend communicates with these API endpoints:

- `POST /api/scrape` - Create new job
- `GET /api/jobs?limit=50` - List all jobs
- `GET /api/jobs/{job_id}` - Get job details

All API calls use JSON and follow REST conventions.

## Features Detail

### Auto-Refresh
- Jobs list refreshes automatically if any job is running
- Refresh interval: 5 seconds
- Manual refresh button available

### Progress Tracking
- Real-time updates for:
  - Pages scraped
  - Amharic pages found
  - Queue size
  - Elapsed time
- Visual progress bar for running jobs

### Responsive Design
- Mobile-friendly layout
- Touch-optimized controls
- Adaptive grid system

## Browser Compatibility

Works with all modern browsers:
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Opera 76+

## Security Note

The frontend is served from the same origin as the API, so no CORS configuration is needed.

For production deployments behind a proxy/load balancer, ensure proper CORS headers are set if the frontend is served from a different domain.

