# Phase 6: YouTube API + iOS Shortcut

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand capture sources by adding nightly YouTube liked-video sync via the YouTube Data API v3 and documenting an iOS Shortcut workflow for sharing X.com/Threads posts to the ingest API.

**Architecture:** A new YouTube sync service handles OAuth2 token management and fetches liked videos via the YouTube Data API v3. An APScheduler job triggers the sync nightly at 2:00 AM (before clustering at 3:00 AM), pulling only videos liked since the last successful sync. The iOS Shortcut is not backend code — it is a user-created Shortcuts.app workflow that POSTs to the existing `POST /api/items` endpoint via the Share Sheet.

**Tech Stack:** google-api-python-client, google-auth-oauthlib, google-auth-httplib2, APScheduler, pytest, respx (HTTP mocking)

**Spec:** `docs/superpowers/specs/2026-03-17-personal-knowledge-digest-design.md`

---

### Task 1: YouTube OAuth2 setup and token management

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/.env.example`
- Modify: `backend/app/config.py`
- Create: `backend/app/services/youtube_auth.py`

- [ ] **Step 1: Add YouTube dependencies to requirements.txt**

Append to `backend/requirements.txt`:

```txt
google-api-python-client==2.159.0
google-auth-oauthlib==1.2.1
google-auth-httplib2==0.2.0
```

- [ ] **Step 2: Add YouTube env vars to .env.example**

Append to `backend/.env.example`:

```env
# YouTube OAuth2
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_TOKEN_PATH=youtube_token.json
```

- [ ] **Step 3: Add YouTube settings to config.py**

Add these fields to the `Settings` class in `backend/app/config.py`:

```python
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_token_path: str = "youtube_token.json"
    youtube_sync_hour: int = 2
```

- [ ] **Step 4: Create youtube_auth.py**

```python
# backend/app/services/youtube_auth.py
"""
YouTube OAuth2 token management.

First-time setup requires an interactive browser flow:
    python -m app.services.youtube_auth

After that, the refresh token is persisted to disk and reused by the
nightly sync job.
"""
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def _token_path() -> Path:
    return Path(settings.youtube_token_path)


def _build_client_config() -> dict:
    """Build the OAuth client config dict from env vars."""
    return {
        "installed": {
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def load_credentials() -> Credentials | None:
    """Load saved credentials from disk. Returns None if not found or expired
    and un-refreshable."""
    path = _token_path()
    if not path.exists():
        return None

    creds = Credentials.from_authorized_user_file(str(path), SCOPES)

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)
        return creds

    return None


def _save_credentials(creds: Credentials) -> None:
    """Persist credentials to disk."""
    path = _token_path()
    path.write_text(creds.to_json())


def authorize_interactive() -> Credentials:
    """Run the interactive OAuth2 browser flow. Used for first-time setup."""
    if not settings.youtube_client_id or not settings.youtube_client_secret:
        print("Error: YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    client_config = _build_client_config()
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=8090, prompt="consent")
    _save_credentials(creds)
    print(f"Token saved to {_token_path()}")
    return creds


if __name__ == "__main__":
    authorize_interactive()
```

- [ ] **Step 5: Install new dependencies**

```bash
cd backend
pip install -r requirements.txt
```

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/.env.example backend/app/config.py backend/app/services/youtube_auth.py
git commit -m "feat: add YouTube OAuth2 token management"
```

---

### Task 2: YouTube sync service — fetch liked videos

**Files:**
- Create: `backend/app/services/youtube_sync.py`

- [ ] **Step 1: Create youtube_sync.py**

```python
# backend/app/services/youtube_sync.py
"""
Nightly YouTube liked-video sync.

Fetches the authenticated user's liked videos from the YouTube Data API v3
and upserts them as items with source=youtube.
"""
import logging
from datetime import datetime, timezone

from googleapiclient.discovery import build
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Item, SourceType
from app.services.youtube_auth import load_credentials

logger = logging.getLogger(__name__)

# Max results per page (YouTube API maximum is 50)
PAGE_SIZE = 50
# Safety cap to avoid runaway pagination on first sync
MAX_PAGES = 20


def _build_youtube_client():
    """Build an authenticated YouTube API client."""
    creds = load_credentials()
    if creds is None:
        raise RuntimeError(
            "YouTube credentials not found. Run: python -m app.services.youtube_auth"
        )
    return build("youtube", "v3", credentials=creds)


def _parse_duration(iso_duration: str) -> str:
    """Convert ISO 8601 duration (PT1H2M3S) to human-readable string."""
    import re

    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration or "")
    if not match:
        return ""
    hours, minutes, seconds = match.groups(default="0")
    parts = []
    if int(hours) > 0:
        parts.append(f"{int(hours)}h")
    if int(minutes) > 0:
        parts.append(f"{int(minutes)}m")
    if int(seconds) > 0:
        parts.append(f"{int(seconds)}s")
    return " ".join(parts) if parts else ""


def fetch_liked_videos(since: datetime | None = None) -> list[dict]:
    """Fetch liked videos from YouTube. If `since` is provided, stop paginating
    once we reach videos published before that timestamp.

    Returns a list of dicts ready for DB insertion.
    """
    youtube = _build_youtube_client()
    items = []
    page_token = None

    for _ in range(MAX_PAGES):
        request = youtube.videos().list(
            part="snippet,contentDetails",
            myRating="like",
            maxResults=PAGE_SIZE,
            pageToken=page_token,
        )
        response = request.execute()

        for video in response.get("items", []):
            snippet = video["snippet"]
            published_at = datetime.fromisoformat(
                snippet["publishedAt"].replace("Z", "+00:00")
            )

            # If we have a since marker and this video was liked/published before it,
            # we've caught up — stop fetching.
            # Note: YouTube returns liked videos in reverse-chronological order of
            # when they were rated, so once we pass the boundary, all remaining are older.
            if since and published_at < since:
                return items

            video_id = video["id"]
            duration = _parse_duration(
                video.get("contentDetails", {}).get("duration", "")
            )
            channel = snippet.get("channelTitle", "")
            description = snippet.get("description", "")

            # Build raw_content from available metadata
            raw_content_parts = []
            if channel:
                raw_content_parts.append(f"Channel: {channel}")
            if duration:
                raw_content_parts.append(f"Duration: {duration}")
            if description:
                raw_content_parts.append(f"\n{description}")

            items.append(
                {
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "title": snippet.get("title", video_id),
                    "source": SourceType.youtube,
                    "raw_content": "\n".join(raw_content_parts) if raw_content_parts else None,
                }
            )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return items


async def sync_liked_videos() -> int:
    """Main entry point for the nightly sync job.

    Fetches liked videos since the most recent YouTube item in the database,
    upserts them, and returns the count of new items added.
    """
    # Find the most recent YouTube item to use as the sync boundary
    from sqlalchemy import select, func

    async with async_session() as session:
        result = await session.execute(
            select(func.max(Item.created_at)).where(Item.source == SourceType.youtube)
        )
        last_sync = result.scalar_one_or_none()

    logger.info(
        "Starting YouTube sync (since=%s)",
        last_sync.isoformat() if last_sync else "beginning",
    )

    videos = fetch_liked_videos(since=last_sync)

    if not videos:
        logger.info("No new liked videos found")
        return 0

    inserted = 0
    async with async_session() as session:
        for video in videos:
            stmt = (
                insert(Item)
                .values(**video)
                .on_conflict_do_nothing(index_elements=["url"])
            )
            result = await session.execute(stmt)
            if result.rowcount > 0:
                inserted += 1
        await session.commit()

    logger.info("YouTube sync complete: %d new items from %d liked videos", inserted, len(videos))
    return inserted
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/youtube_sync.py
git commit -m "feat: add YouTube liked-video sync service"
```

---

### Task 3: Register YouTube sync as APScheduler nightly job

**Files:**
- Modify: `backend/app/scheduler.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add YouTube sync job to scheduler.py**

Add the YouTube sync job to the existing `backend/app/scheduler.py`. Insert alongside the existing clustering and digest jobs:

```python
# Add this import at the top of backend/app/scheduler.py
import asyncio
from app.services.youtube_sync import sync_liked_videos

# Add this job registration inside the function that configures the scheduler
# (alongside the existing clustering and digest jobs):

def _run_youtube_sync():
    """Wrapper to run the async sync in APScheduler's sync context."""
    asyncio.run(sync_liked_videos())

scheduler.add_job(
    _run_youtube_sync,
    "cron",
    hour=settings.youtube_sync_hour,
    minute=0,
    id="youtube_sync",
    replace_existing=True,
    misfire_grace_time=3600,
)
```

The full scheduler.py should look like this after modification:

```python
# backend/app/scheduler.py
import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def _run_youtube_sync():
    """Wrapper to run the async YouTube sync in APScheduler's sync context."""
    from app.services.youtube_sync import sync_liked_videos
    asyncio.run(sync_liked_videos())


def start_scheduler():
    """Configure and start all scheduled jobs."""
    from app.services.clustering import run_clustering
    from app.services.digest import generate_digest

    def _run_clustering():
        asyncio.run(run_clustering())

    def _run_digest():
        asyncio.run(generate_digest())

    scheduler.add_job(
        _run_clustering,
        "cron",
        hour=settings.clustering_hour,
        minute=0,
        id="nightly_clustering",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        _run_digest,
        "cron",
        hour=settings.digest_hour,
        minute=0,
        id="daily_digest",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # YouTube liked-video sync — runs before clustering
    scheduler.add_job(
        _run_youtube_sync,
        "cron",
        hour=settings.youtube_sync_hour,
        minute=0,
        id="youtube_sync",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: clustering@%02d:00, digest@%02d:00, youtube_sync@%02d:00",
        settings.clustering_hour,
        settings.digest_hour,
        settings.youtube_sync_hour,
    )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Verify main.py startup hooks call start_scheduler()**

Confirm `backend/app/main.py` already has the scheduler startup in its lifespan or startup event. It should contain something like:

```python
from app.scheduler import start_scheduler, stop_scheduler

@app.on_event("startup")
async def startup():
    start_scheduler()

@app.on_event("shutdown")
async def shutdown():
    stop_scheduler()
```

If it uses the newer lifespan pattern instead, the scheduler calls should already be present from Phase 4. No change needed if so.

- [ ] **Step 3: Commit**

```bash
git add backend/app/scheduler.py backend/app/main.py
git commit -m "feat: register YouTube sync as nightly APScheduler job at 2:00 AM"
```

---

### Task 4: iOS Shortcut documentation / setup guide

**Files:**
- Create: `backend/docs/ios-shortcut-setup.md`

This task produces documentation only — no backend code changes. The iOS Shortcut is built entirely within Apple's Shortcuts.app by the user.

- [ ] **Step 1: Create the iOS Shortcut setup guide**

```markdown
# iOS Shortcut Setup — Capture X.com & Threads Posts

This guide walks you through creating an iOS Shortcut that sends shared
posts from X.com (Twitter) and Threads to your Insight API via the
Share Sheet.

## Prerequisites

- iOS 16+ with Shortcuts app installed
- Your Insight backend running and accessible from your phone
  (e.g., via Tailscale, Cloudflare Tunnel, or local network)
- Your API URL and API key

## Create the Shortcut

1. Open **Shortcuts** on your iPhone/iPad
2. Tap **+** to create a new shortcut
3. Tap the shortcut name at the top and rename it to **Save to Insight**
4. Tap **ⓘ** (info) at the bottom → enable **Show in Share Sheet**
5. Under "Share Sheet Types", select **URLs** only

### Add Actions

Add the following actions in order:

**Action 1: Get URLs from Input**
- Search for "Get URLs from" and select **Get URLs from Input**
- This extracts the URL from whatever is shared

**Action 2: Set Variable**
- Action: **Set Variable**
- Name: `shared_url`
- Value: Output of previous action

**Action 3: If (detect source)**
- Action: **If**
- Input: `shared_url`
- Condition: **contains** `twitter.com` or `x.com`
- Then → **Set Variable** `source` to `x`
- Otherwise → **Set Variable** `source` to `threads`

**Action 4: Get Contents of URL (POST to API)**
- Action: **Get Contents of URL**
- URL: `http://<YOUR_API_URL>/api/items`
- Method: **POST**
- Headers:
  - `Content-Type`: `application/json`
  - `X-API-Key`: `<YOUR_API_KEY>`
- Request Body (JSON):
  ```json
  {
    "url": shared_url,
    "title": shared_url,
    "source": source
  }
  ```

**Action 5: Show Notification**
- Action: **Show Notification**
- Title: "Saved to Insight"
- Body: `shared_url`

## Usage

1. In X.com or Threads app, tap **Share** on any post
2. Scroll the share sheet and tap **Save to Insight**
3. You'll see a brief notification confirming the save

The item appears in your Insight backend with `source=x` or
`source=threads` and `status=pending`. The enrichment pipeline will
fetch the content, generate a summary, and include it in your next
daily digest.

## Troubleshooting

- **"Could not connect to server"**: Ensure your backend is reachable
  from your phone. If running on localhost, use a tunnel service like
  Tailscale or Cloudflare Tunnel.
- **401 Unauthorized**: Double-check the API key in the shortcut matches
  the `API_KEY` in your backend `.env`.
- **The URL is blank**: Make sure "Share Sheet Types" is set to **URLs**.
  Some apps share text instead of URLs — in that case, add a "Match URLs
  in Text" action before "Get URLs from Input".

## Shortcut Download

Since Shortcuts cannot be version-controlled, the configuration above
is the canonical reference. If you need to recreate it, follow the
steps above — it takes about 2 minutes.
```

- [ ] **Step 2: Commit**

```bash
git add backend/docs/ios-shortcut-setup.md
git commit -m "docs: add iOS Shortcut setup guide for X.com and Threads capture"
```

---

### Task 5: End-to-end test

**Files:**
- Create: `backend/tests/test_youtube_sync.py`

All tests mock the YouTube API — no real API calls or credentials required.

- [ ] **Step 1: Create test_youtube_sync.py**

```python
# backend/tests/test_youtube_sync.py
"""
Tests for YouTube sync service.

All YouTube API calls are mocked — no credentials or network access needed.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, SourceType
from app.services.youtube_sync import (
    _parse_duration,
    fetch_liked_videos,
    sync_liked_videos,
)


# --- Unit tests for duration parsing ---


def test_parse_duration_hours_minutes_seconds():
    assert _parse_duration("PT1H2M3S") == "1h 2m 3s"


def test_parse_duration_minutes_only():
    assert _parse_duration("PT15M") == "15m"


def test_parse_duration_hours_only():
    assert _parse_duration("PT2H") == "2h"


def test_parse_duration_empty():
    assert _parse_duration("") == ""
    assert _parse_duration(None) == ""


# --- Mock YouTube API response ---


def _make_youtube_response(videos: list[dict], next_page_token: str | None = None) -> dict:
    """Build a mock YouTube API response."""
    items = []
    for v in videos:
        items.append({
            "id": v["id"],
            "snippet": {
                "title": v["title"],
                "description": v.get("description", ""),
                "channelTitle": v.get("channel", "Test Channel"),
                "publishedAt": v.get(
                    "published_at",
                    "2026-03-17T12:00:00Z",
                ),
            },
            "contentDetails": {
                "duration": v.get("duration", "PT10M30S"),
            },
        })
    resp = {"items": items}
    if next_page_token:
        resp["nextPageToken"] = next_page_token
    return resp


def _mock_youtube_client(responses: list[dict]):
    """Create a mock YouTube API client that returns the given responses
    in sequence."""
    mock_client = MagicMock()
    mock_videos = MagicMock()
    mock_client.videos.return_value = mock_videos

    mock_list = MagicMock()
    mock_videos.list.return_value = mock_list

    # Each call to execute() returns the next response
    mock_list.execute.side_effect = responses

    return mock_client


# --- Tests for fetch_liked_videos ---


@patch("app.services.youtube_sync._build_youtube_client")
def test_fetch_liked_videos_returns_items(mock_build):
    response = _make_youtube_response([
        {"id": "abc123", "title": "Cool Video", "channel": "Tech Channel", "duration": "PT15M"},
        {"id": "def456", "title": "Another Video", "channel": "Science", "duration": "PT1H2M"},
    ])
    mock_build.return_value = _mock_youtube_client([response])

    videos = fetch_liked_videos()

    assert len(videos) == 2
    assert videos[0]["url"] == "https://www.youtube.com/watch?v=abc123"
    assert videos[0]["title"] == "Cool Video"
    assert videos[0]["source"] == SourceType.youtube
    assert "Tech Channel" in videos[0]["raw_content"]
    assert "15m" in videos[0]["raw_content"]


@patch("app.services.youtube_sync._build_youtube_client")
def test_fetch_liked_videos_stops_at_since(mock_build):
    since = datetime(2026, 3, 16, 0, 0, 0, tzinfo=timezone.utc)
    response = _make_youtube_response([
        {"id": "new1", "title": "New Video", "published_at": "2026-03-17T12:00:00Z"},
        {"id": "old1", "title": "Old Video", "published_at": "2026-03-15T12:00:00Z"},
    ])
    mock_build.return_value = _mock_youtube_client([response])

    videos = fetch_liked_videos(since=since)

    assert len(videos) == 1
    assert videos[0]["url"] == "https://www.youtube.com/watch?v=new1"


@patch("app.services.youtube_sync._build_youtube_client")
def test_fetch_liked_videos_paginates(mock_build):
    page1 = _make_youtube_response(
        [{"id": "p1v1", "title": "Page 1 Video"}],
        next_page_token="page2token",
    )
    page2 = _make_youtube_response(
        [{"id": "p2v1", "title": "Page 2 Video"}],
    )
    mock_build.return_value = _mock_youtube_client([page1, page2])

    videos = fetch_liked_videos()

    assert len(videos) == 2
    assert videos[0]["title"] == "Page 1 Video"
    assert videos[1]["title"] == "Page 2 Video"


@patch("app.services.youtube_sync._build_youtube_client")
def test_fetch_liked_videos_empty(mock_build):
    response = _make_youtube_response([])
    mock_build.return_value = _mock_youtube_client([response])

    videos = fetch_liked_videos()

    assert videos == []


# --- Integration test for sync_liked_videos (uses test DB) ---


@pytest.mark.asyncio
@patch("app.services.youtube_sync._build_youtube_client")
@patch("app.services.youtube_sync.async_session")
async def test_sync_liked_videos_inserts_items(mock_session_factory, mock_build, setup_db):
    """End-to-end test: mock YouTube API → sync → verify DB inserts."""
    from tests.conftest import TestSession

    # Configure mock to use test DB session
    mock_session_factory.side_effect = TestSession

    response = _make_youtube_response([
        {"id": "sync1", "title": "Synced Video 1", "channel": "Channel A"},
        {"id": "sync2", "title": "Synced Video 2", "channel": "Channel B"},
    ])
    mock_build.return_value = _mock_youtube_client([response])

    count = await sync_liked_videos()

    assert count == 2

    # Verify items exist in DB
    async with TestSession() as session:
        result = await session.execute(
            select(Item).where(Item.source == SourceType.youtube)
        )
        items = result.scalars().all()
        assert len(items) == 2
        urls = {item.url for item in items}
        assert "https://www.youtube.com/watch?v=sync1" in urls
        assert "https://www.youtube.com/watch?v=sync2" in urls


@pytest.mark.asyncio
@patch("app.services.youtube_sync._build_youtube_client")
@patch("app.services.youtube_sync.async_session")
async def test_sync_liked_videos_deduplicates(mock_session_factory, mock_build, setup_db):
    """Running sync twice with the same videos should not create duplicates."""
    from tests.conftest import TestSession

    mock_session_factory.side_effect = TestSession

    response = _make_youtube_response([
        {"id": "dup1", "title": "Duplicate Video"},
    ])

    # Run sync twice
    mock_build.return_value = _mock_youtube_client([response])
    await sync_liked_videos()

    mock_build.return_value = _mock_youtube_client([response])
    count = await sync_liked_videos()

    assert count == 0  # Second run inserts nothing

    async with TestSession() as session:
        result = await session.execute(
            select(Item).where(Item.source == SourceType.youtube)
        )
        items = result.scalars().all()
        assert len(items) == 1


# --- Test for OAuth credential loading failure ---


@patch("app.services.youtube_sync.load_credentials", return_value=None)
def test_build_youtube_client_raises_without_credentials(mock_creds):
    with pytest.raises(RuntimeError, match="YouTube credentials not found"):
        _mock = _build_youtube_client()


# Need to import the actual function for this test
from app.services.youtube_sync import _build_youtube_client as _real_build


@patch("app.services.youtube_sync.load_credentials", return_value=None)
def test_build_client_raises_without_creds(mock_creds):
    with pytest.raises(RuntimeError, match="YouTube credentials not found"):
        _real_build()
```

- [ ] **Step 2: Run the tests**

```bash
cd backend
python -m pytest tests/test_youtube_sync.py -v
```

Expected output:
```
test_parse_duration_hours_minutes_seconds PASSED
test_parse_duration_minutes_only PASSED
test_parse_duration_hours_only PASSED
test_parse_duration_empty PASSED
test_fetch_liked_videos_returns_items PASSED
test_fetch_liked_videos_stops_at_since PASSED
test_fetch_liked_videos_paginates PASSED
test_fetch_liked_videos_empty PASSED
test_sync_liked_videos_inserts_items PASSED
test_sync_liked_videos_deduplicates PASSED
test_build_client_raises_without_creds PASSED
```

- [ ] **Step 3: Run the full test suite to ensure no regressions**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: All tests pass, including existing Phase 1-5 tests.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_youtube_sync.py
git commit -m "test: add YouTube sync tests with mocked API"
```

- [ ] **Step 5: Manual verification — YouTube OAuth flow**

This step requires real YouTube API credentials and is done once interactively:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. Enable the **YouTube Data API v3**
4. Create OAuth 2.0 credentials (Desktop application type)
5. Copy the Client ID and Client Secret to `backend/.env`:
   ```env
   YOUTUBE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   YOUTUBE_CLIENT_SECRET=your-client-secret
   ```
6. Run the interactive auth flow:
   ```bash
   cd backend
   python -m app.services.youtube_auth
   ```
7. A browser window opens — sign in and grant YouTube read access
8. Verify `youtube_token.json` was created in the backend directory

- [ ] **Step 6: Manual verification — trigger sync**

```bash
cd backend
python -c "
import asyncio
from app.services.youtube_sync import sync_liked_videos
count = asyncio.run(sync_liked_videos())
print(f'Synced {count} videos')
"
```

Then verify items appeared:

```bash
curl http://localhost:8000/api/items?source=youtube
```

Expected: Items with `"source": "youtube"` and `"status": "pending"` (enrichment will process them asynchronously).

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "chore: Phase 6 complete — YouTube sync and iOS Shortcut documentation"
```

---

## Phase 6 Completion Checklist

- [ ] `google-api-python-client`, `google-auth-oauthlib`, and `google-auth-httplib2` added to `requirements.txt`
- [ ] `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_TOKEN_PATH` in `.env.example` and `config.py`
- [ ] `youtube_auth.py` handles OAuth2 token persistence and refresh
- [ ] `youtube_auth.py` can be run as `python -m app.services.youtube_auth` for interactive setup
- [ ] `youtube_sync.py` fetches liked videos via YouTube Data API v3
- [ ] `youtube_sync.py` extracts video title, description, channel, and duration
- [ ] `youtube_sync.py` upserts items with `source=youtube` and deduplicates on URL
- [ ] `youtube_sync.py` only fetches videos liked since the last sync
- [ ] APScheduler job `youtube_sync` runs at 2:00 AM (before clustering at 3:00 AM)
- [ ] All YouTube API calls are mocked in tests — no real credentials needed for CI
- [ ] Duration parsing handles all ISO 8601 variants (hours, minutes, seconds)
- [ ] Missing credentials raises a clear error message
- [ ] iOS Shortcut setup guide documents Share Sheet → POST /api/items workflow
- [ ] iOS Shortcut correctly sets `source=x` for X.com and `source=threads` for Threads
- [ ] All tests pass: `python -m pytest tests/ -v`
