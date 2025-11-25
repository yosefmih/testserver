# Amharic Scraper Frontend

Modern React + TypeScript frontend for the Amharic Web Scraper service.

## Setup

```bash
# Install dependencies
npm install

# Start development server (with API proxy)
npm run dev

# Build for production
npm run build
```

## Development

The dev server runs on http://localhost:3000 and proxies API requests to http://localhost:8080.

Make sure the backend server is running on port 8080 before starting the frontend.

## Production Build

```bash
npm run build
```

This builds the app to `../static` directory, which the FastAPI server will serve.

## Project Structure

```
src/
├── components/       # React components
│   ├── JobForm.tsx
│   ├── JobCard.tsx
│   ├── JobList.tsx
│   └── JobModal.tsx
├── services/        # API service layer
│   └── api.ts
├── types/           # TypeScript types
│   └── index.ts
├── App.tsx          # Main app component
├── App.css          # Global styles
└── main.tsx         # Entry point
```

## Features

- ✅ Create scraping jobs
- ✅ View all jobs
- ✅ Real-time progress tracking
- ✅ Job details modal
- ✅ Auto-refresh for running jobs
- ✅ Responsive design
- ✅ TypeScript for type safety
- ✅ Modern React hooks

