# Start the Project

This project consists of three main components: a FastAPI backend, an ARQ worker, and a Next.js dashboard. All services require Redis to be running.

## 0. Start Redis
Ensure Redis is running on `localhost:6379`.
```bash
redis-server
```

## 1. Start FastAPI Backend
From the root directory:
```bash
python3 -m uvicorn pdf_engine.main:app --reload --port 8000
```

## 2. Start ARQ Worker
From the root directory:
```bash
python3 -m arq pdf_engine.worker.WorkerSettings
```

## 3. Start QA Dashboard
From the root directory:
```bash
cd qa-dashboard && npm run dev
```

## 4. CLI Utilities
These standalone scripts are useful for manual extraction and debugging without running the full web dashboard.

### PDF Extraction
Extracts text from all PDFs in the `./pdf/` folder and writes results to `./output/`.
```bash
python3 cli_extract.py
```

### Web Scraping
Scrapes a microsite URL and writes the normalized text to `./crawloutput/`.
```bash
python3 cli_crawl.py <url>
```
