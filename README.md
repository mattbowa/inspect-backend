# SEO Agent

AI-powered SEO auditing platform. Submit a URL, get back a scored report with prioritised fixes.

## How it works

A scan runs a 4-stage pipeline in the background:

1. **Crawl** — Playwright visits up to N pages, extracting titles, meta descriptions, H1s, word counts, internal links, and images
2. **Embed** — Each page is embedded with fastembed and stored in Qdrant for similarity search
3. **Agent pipeline** — Four agents analyse the crawled data in sequence:
   - **Technical** — Rule-based checks (missing titles, duplicate titles, missing H1, thin content, images without alt text)
   - **Content** — Claude analyses pages with issues and suggests improved titles, descriptions, and content
   - **Linking** — Qdrant vector similarity finds topically related pages that aren't linked to each other
   - **Strategy** — Claude synthesises all findings into a prioritised top-5 action list and calculates an SEO score
4. **Score** — `100 - (errors × 10) - (warnings × 3)`

## Stack

- **FastAPI** — REST API
- **Celery + Redis** — async task queue
- **PostgreSQL** — persistent scan history
- **fastembed** — local embeddings (no API call)
- **Playwright** — JavaScript-capable crawler
- **Claude Haiku** — content suggestions and strategy synthesis

## Setup

**1. Configure environment**

```bash
cp .env.example .env
```

Edit `.env` and set your Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-...
REDIS_URL=redis://redis:6379
DATABASE_URL=postgresql://seo:seo@postgres:5432/seo
```

**2. Build and start**

```bash
docker compose up --build
```

Services:
| Service | URL |
|---|---|
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Redis | localhost:6379 |
| PostgreSQL | localhost:5432 |

## Usage

**Start a scan**

```bash
curl -X POST http://localhost:8000/scans \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "max_pages": 20}'
```

```json
{ "scan_id": "abc-123", "status": "pending", "url": "https://example.com" }
```

**Poll status**

```bash
curl http://localhost:8000/scans/abc-123/status
```

Status values: `pending` → `crawling` → `analysing` → `done` / `failed`

**Get report**

```bash
curl http://localhost:8000/reports/abc-123 | python3 -m json.tool
```

**View scan history**

```bash
# All scans
curl http://localhost:8000/history | python3 -m json.tool

# Filter by domain
curl "http://localhost:8000/history?domain=petstock" | python3 -m json.tool
```

```json
[
  {
    "scan_id": "abc-123",
    "url": "https://example.com",
    "seo_score": 74,
    "status": "done",
    "created_at": "2026-03-29T06:00:00"
  }
]
```

```json
{
  "scan_id": "abc-123",
  "url": "https://example.com",
  "seo_score": 74,
  "top_actions": ["Add missing H1 tags to 3 pages...", "..."],
  "agents": [
    {
      "agent": "technical",
      "summary": "Found 2 errors and 5 warnings across 12 pages.",
      "issues": [
        {
          "page_url": "https://example.com/about",
          "severity": "error",
          "type": "missing_h1",
          "description": "Page has no H1 tag.",
          "suggestion": "Add a single H1 that reflects the page's primary topic."
        }
      ]
    }
  ]
}
```

## Issue severity levels

| Severity  | Meaning                  | Score impact |
| --------- | ------------------------ | ------------ |
| `error`   | Critical SEO problem     | -10 pts      |
| `warning` | Should be fixed          | -3 pts       |
| `info`    | Opportunity / suggestion | 0 pts        |

## Production database

By default Postgres runs as a Docker container with data persisted in a named volume (`postgres_data`). To use a managed database in production (e.g. [Neon](https://neon.tech) free tier), just update `DATABASE_URL` in your `.env`:

```
DATABASE_URL=postgresql://user:password@your-host/dbname
```

No code changes required.

## Project structure

```
app/
├── api/          # FastAPI route handlers (scans, reports, history)
├── agents/       # technical, content, linking, strategy
├── services/     # crawler, embeddings
├── workers/      # Celery app and tasks
├── models/       # Pydantic schemas
├── database.py   # SQLAlchemy models + DB helpers
└── config.py     # Settings
```
