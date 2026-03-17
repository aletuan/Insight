# Personal Knowledge Digest — Design Specification

Version 1.0 · March 17, 2026

## Overview

A personal system that automatically captures saved content from multiple platforms (Chrome bookmarks, YouTube likes, X.com, Threads), enriches it with AI-generated summaries and embeddings, clusters items by theme, and delivers a structured daily digest — without requiring ongoing manual effort.

The paradigm shift: from "retrieval on demand" to "proactive synthesis." The user never searches for what they saved — they receive a morning digest that tells them what they've been thinking about.

## Architecture

**Monolith — single FastAPI process.**

All responsibilities live in one process: HTTP API, background enrichment, scheduled jobs (clustering + digest generation), and content fetching. This is the right choice for a single-user localhost tool processing ~10 items/day.

```
Capture Sources (Chrome Ext, iOS Shortcut, YouTube Cron, Bookmark Import)
        │
        │  POST /api/items (API key header)
        ▼
┌─────────────────────────────────┐
│       FastAPI Monolith          │
│   (uvicorn, single process)     │
│                                 │
│  ┌──────────┐ ┌──────────────┐  │
│  │API Router│ │  Enrichment  │  │
│  │  (CRUD)  │ │   Worker     │  │
│  └──────────┘ │(asyncio bg)  │  │
│               │ Haiku+OpenAI │  │
│  ┌──────────┐ └──────────────┘  │
│  │Scheduler │ ┌──────────────┐  │
│  │(APSched) │ │   Content    │  │
│  │cluster + │ │   Fetcher    │  │
│  │ digest   │ │(trafilatura) │  │
│  └──────────┘ └──────────────┘  │
└─────────────────────────────────┘
        │
        ▼
  PostgreSQL + pgvector
        ▲
        │  API calls
  Next.js 14 Frontend
```

### Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend API | Python + FastAPI + uvicorn |
| Database | PostgreSQL + pgvector |
| ORM | SQLAlchemy |
| Validation | Pydantic |
| Task scheduling | APScheduler (in-process) |
| Background tasks | asyncio (in-process) |
| Content extraction | trafilatura / readability-lxml |
| AI — summaries/tags | Anthropic Claude Haiku |
| AI — digest generation | Anthropic Claude Sonnet |
| AI — embeddings | OpenAI text-embedding-3-small (1536 dims) |
| Clustering | scikit-learn K-means + silhouette scoring |
| Frontend | Next.js 14 (App Router) |
| Chrome Extension | Manifest V3, vanilla JS |
| Hosting (v1) | localhost (Mac) |

## Data Model

### Tables

**items** — every saved item

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| url | TEXT | Original URL (unique, upsert on conflict) |
| title | TEXT | Page/video title |
| source | ENUM | chrome, youtube, x, threads, manual |
| raw_content | TEXT | Full text / transcript / description |
| summary | TEXT | AI-generated 3-4 sentence summary |
| tags | TEXT[] | AI-extracted topic tags |
| embedding | VECTOR(1536) | text-embedding-3-small vector |
| cluster_id | INT | FK to clusters (updated nightly) |
| created_at | TIMESTAMP | When item was saved |
| processed_at | TIMESTAMP | When AI enrichment completed |

**clusters** — current cluster assignments (rebuilt nightly)

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| label | TEXT | AI-generated cluster name |
| centroid | VECTOR(1536) | Cluster centroid |
| item_count | INT | Number of items |
| created_at | TIMESTAMP | When this clustering run happened |

**digests** — generated daily digests (immutable once created)

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| date | DATE | Digest date (unique) |
| content | JSONB | Full digest: clusters, insights, connections |
| item_count | INT | Total items covered |
| created_at | TIMESTAMP | When generated |

**digest_items** — join table

| Column | Type | Description |
|--------|------|-------------|
| digest_id | INT | FK to digests |
| item_id | UUID | FK to items |

### Key Constraints

- **Deduplication**: unique constraint on `items.url`, upsert on conflict (update title/timestamp if re-saved)
- **Clusters are ephemeral**: rebuilt from scratch every night, old rows replaced
- **Digests are immutable**: once generated, never modified — historical record preserved

## API Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | /api/items | Ingest a new saved item | API key header |
| GET | /api/items | List/search items (supports ?q= for semantic search) | None (local) |
| GET | /api/digest/today | Get today's generated digest | None (local) |
| GET | /api/digest/:date | Get digest for specific date | None (local) |
| POST | /api/digest/generate | Manually trigger digest generation | None (local) |
| GET | /api/clusters | List current clusters + item counts | None (local) |

Auth: simple static API key in env var, sent as header by capture sources. No auth on read endpoints (localhost only).

## AI Pipeline

### Stage 1 — Enrichment (on ingest, async)

```
Item saved → fetch full page content (trafilatura) → Claude Haiku → OpenAI embeddings → update DB
```

- Triggered immediately via asyncio background task when an item is ingested
- Haiku generates: 3-4 sentence summary + topic tags (single prompt, structured JSON response)
- OpenAI embeds the concatenation of `title + summary` (not raw content — cleaner semantic signal)
- Target latency: under 5 minutes per item

### Stage 2 — Clustering (nightly cron, 3:00 AM)

```
Load all embeddings → K-means (k=3 to 7) → silhouette scoring → assign cluster_id → generate labels
```

- APScheduler runs at 3:00 AM
- Tests k=3,4,5,6,7 via silhouette scoring, picks best fit
- After clustering, Haiku generates a short label for each cluster from item titles/summaries
- Replaces previous cluster assignments entirely

### Stage 3 — Digest generation (daily cron, 7:00 AM)

```
Fetch items since last digest, grouped by cluster → Claude Sonnet → structured digest JSON
```

- Configurable time (default 7:00 AM)
- Sonnet receives all items per cluster and generates:
  - Insight paragraph (3-5 sentences) per cluster — synthesizes, doesn't just list
  - Cross-cluster connections when detected
- Output stored as JSONB in digests table
- Skips generation if no new items since last digest

### Cost Estimate (~10 items/day)

- Haiku: ~10 calls/day → negligible
- OpenAI embeddings: ~10 calls/day → negligible
- Sonnet: 1 call/day → ~$0.01-0.05/day
- **Total: well under $1/month**

## Capture Sources

### Chrome Extension (Manifest V3)

- Listens to `chrome.bookmarks.onCreated`
- POSTs `{url, title, source: 'chrome', timestamp}` to `/api/items`
- Options page to configure API URL + key
- ~50 lines of vanilla JS

### YouTube Likes (nightly sync)

- YouTube Data API v3 with OAuth2
- APScheduler job runs nightly, pulls liked videos since last sync
- Extracts: video title, description, channel, duration, transcript (if available)

### X.com / Threads (iOS Shortcut)

- No public API for likes — iOS Share Sheet workaround
- iOS Shortcut: user taps Share → auto-POST to `/api/items`
- Friction: 2 taps (acceptable given platform constraints)

### Chrome Bookmark Import (one-time)

- CLI script parses NETSCAPE-Bookmark-file-1 HTML format
- Backfills historical data into items table
- Expected volume: <500 bookmarks, no batching needed

## Frontend

### Design Principles

- **Content-first reader layout** — narrow column (640px max), generous whitespace, no visual clutter
- **Typography**: Source Serif 4 (serif) for headings and insight paragraphs, Inter (sans) for UI elements and navigation
- **Source labels are whispers** — tiny monospace abbreviations (bm, yt, x, th), not colorful badges
- **Insight is the star** — cluster name + AI paragraph dominate, item links are secondary
- **No boxes, cards, or borders around content** — just typography and spacing
- **Navigation disappears** — land on today's digest, everything else is one click away

### Views

**1. Daily Digest (primary screen, `/digest/[date]`)**
- Date header with item count and estimated read time
- Clusters with: name, insight paragraph, list of items with source abbreviation + link
- Cross-cluster connections section when detected
- Date navigation (prev/next)

**2. Semantic Search (`/search`)**
- Single input field, underline style
- Results ranked by vector similarity
- Each result: source abbreviation, title link, summary excerpt

**3. Timeline (`/timeline`)**
- Chronological list grouped by day
- Filterable by source
- Each item: timestamp, source abbreviation, title

## Project Structure

```
insight/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + startup/shutdown
│   │   ├── config.py            # Settings (env vars, API keys)
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── schemas.py           # Pydantic request/response
│   │   ├── database.py          # DB connection + session
│   │   ├── routers/
│   │   │   ├── items.py         # POST/GET /api/items
│   │   │   ├── digest.py        # GET /api/digest/*
│   │   │   └── clusters.py      # GET /api/clusters
│   │   ├── services/
│   │   │   ├── enrichment.py    # Haiku summary + OpenAI embed
│   │   │   ├── content.py       # URL → full text extraction
│   │   │   ├── clustering.py    # K-means + silhouette
│   │   │   └── digest.py        # Sonnet digest generation
│   │   └── scheduler.py         # APScheduler config
│   ├── scripts/
│   │   └── import_bookmarks.py  # Chrome HTML bookmark importer
│   ├── requirements.txt
│   └── .env                     # API keys, DB URL
├── frontend/
│   ├── src/app/
│   │   ├── page.tsx             # → redirects to /digest/today
│   │   ├── digest/
│   │   │   └── [date]/page.tsx  # Digest view
│   │   ├── search/page.tsx      # Semantic search
│   │   └── timeline/page.tsx    # Chronological view
│   ├── src/components/
│   │   ├── DigestCluster.tsx    # Cluster card with insight
│   │   ├── ItemCard.tsx         # Single item display
│   │   ├── SourceBadge.tsx      # bm|yt|x|th label
│   │   ├── SearchBar.tsx        # Search input
│   │   └── Nav.tsx              # Top nav
│   └── package.json
└── chrome-extension/
    ├── manifest.json            # Manifest V3
    ├── background.js            # onBookmarkCreated → POST
    └── options.html             # Configure API URL + key
```

## Build Phases

| Phase | What | Goal |
|-------|------|------|
| 1 | Ingest API + Postgres schema + bookmark importer | Data foundation |
| 2 | Chrome Extension → POST to API | Live capture |
| 3 | AI Enrichment pipeline (summarize + embed) | Every item gets AI context |
| 4 | Clustering + Digest Generator | First real digest |
| 5 | Web App — digest view + search | Daily usable product |
| 6 | YouTube API + iOS Shortcut | Expand capture sources |

Each phase is independently useful. Phases 1-2 give working capture; 3-4 are the core value; 5 makes it a daily habit; 6 expands coverage.

## V1 Success Criteria

- Bookmarks from Chrome appear in the system within 60 seconds
- Every item has a 3-sentence AI summary within 5 minutes
- A digest is generated every morning with 3-7 thematic clusters
- Each cluster has an AI-written insight that synthesizes — not just lists
- Can search across all items using natural language
- Total setup time under 2 hours from scratch

## Non-Goals (v1)

- Social features, sharing, or collaboration
- Mobile app (responsive web is sufficient)
- Real-time sync (nightly batch is acceptable for YouTube)
- TikTok / Instagram integration
- Multi-user support
- Docker / containerization (localhost only)
