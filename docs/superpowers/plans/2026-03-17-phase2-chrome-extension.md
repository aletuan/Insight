# Phase 2: Chrome Extension — Live Capture

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Manifest V3 Chrome extension that automatically captures every new bookmark and POSTs it to the FastAPI ingest API in real time.

**Architecture:** A Chrome extension service worker listens to `chrome.bookmarks.onCreated`, reads the bookmark details, and sends a `POST /api/items` request to the backend. An options page lets the user configure the API URL and API key, stored in `chrome.storage.sync`.

**Tech Stack:** Chrome Manifest V3, vanilla JavaScript, chrome.bookmarks API, chrome.storage API

**Spec:** `docs/superpowers/specs/2026-03-17-personal-knowledge-digest-design.md`

---

### Task 1: Extension scaffolding — manifest.json

**Files:**
- Create: `chrome-extension/manifest.json`

- [ ] **Step 1: Create manifest.json**

```json
// chrome-extension/manifest.json
{
  "manifest_version": 3,
  "name": "Insight — Bookmark Capture",
  "version": "1.0.0",
  "description": "Automatically sends new Chrome bookmarks to your Insight digest API.",
  "permissions": [
    "bookmarks",
    "storage"
  ],
  "host_permissions": [
    "http://localhost:8000/*"
  ],
  "background": {
    "service_worker": "background.js"
  },
  "options_page": "options.html",
  "icons": {
    "48": "icon48.png",
    "128": "icon128.png"
  }
}
```

Note: `host_permissions` allows fetch to the local API. If the user changes their API URL in options, they may need to update this — but for v1, localhost:8000 is the only target.

Icons are optional placeholders. The extension works without them.

- [ ] **Step 2: Commit**

```bash
git add chrome-extension/manifest.json
git commit -m "feat: add Chrome extension manifest (Manifest V3)"
```

---

### Task 2: Options page — configure API URL and key

**Files:**
- Create: `chrome-extension/options.html`
- Create: `chrome-extension/options.js`

- [ ] **Step 1: Create options.html**

```html
<!-- chrome-extension/options.html -->
<!DOCTYPE html>
<html>
<head>
  <title>Insight — Options</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 400px; margin: 40px auto; padding: 0 20px; }
    label { display: block; margin-top: 16px; font-weight: 600; font-size: 14px; }
    input { width: 100%; padding: 8px; margin-top: 4px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; box-sizing: border-box; }
    button { margin-top: 20px; padding: 8px 20px; background: #111; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
    #status { margin-top: 12px; color: #16a34a; font-size: 13px; }
  </style>
</head>
<body>
  <h2>Insight Settings</h2>

  <label for="apiUrl">API URL</label>
  <input type="text" id="apiUrl" placeholder="http://localhost:8000" />

  <label for="apiKey">API Key</label>
  <input type="text" id="apiKey" placeholder="your-api-key" />

  <button id="save">Save</button>
  <div id="status"></div>

  <script src="options.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create options.js**

```javascript
// chrome-extension/options.js
const DEFAULTS = {
  apiUrl: "http://localhost:8000",
  apiKey: "",
};

document.addEventListener("DOMContentLoaded", () => {
  // Load saved settings
  chrome.storage.sync.get(DEFAULTS, (items) => {
    document.getElementById("apiUrl").value = items.apiUrl;
    document.getElementById("apiKey").value = items.apiKey;
  });

  // Save settings
  document.getElementById("save").addEventListener("click", () => {
    const apiUrl = document.getElementById("apiUrl").value.replace(/\/+$/, "");
    const apiKey = document.getElementById("apiKey").value;

    chrome.storage.sync.set({ apiUrl, apiKey }, () => {
      const status = document.getElementById("status");
      status.textContent = "Saved.";
      setTimeout(() => { status.textContent = ""; }, 2000);
    });
  });
});
```

- [ ] **Step 3: Commit**

```bash
git add chrome-extension/options.html chrome-extension/options.js
git commit -m "feat: add options page for API URL and key configuration"
```

---

### Task 3: Background service worker — bookmark capture

**Files:**
- Create: `chrome-extension/background.js`

- [ ] **Step 1: Create background.js**

```javascript
// chrome-extension/background.js

const DEFAULTS = {
  apiUrl: "http://localhost:8000",
  apiKey: "",
};

/**
 * Send a bookmark to the Insight API.
 */
async function sendBookmark(url, title) {
  const settings = await chrome.storage.sync.get(DEFAULTS);

  if (!settings.apiKey) {
    console.warn("[Insight] No API key configured. Open extension options.");
    return;
  }

  const endpoint = `${settings.apiUrl}/api/items`;

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": settings.apiKey,
      },
      body: JSON.stringify({
        url: url,
        title: title || url,
        source: "chrome",
        timestamp: new Date().toISOString(),
      }),
    });

    if (!response.ok) {
      console.error("[Insight] API error:", response.status, await response.text());
    } else {
      console.log("[Insight] Bookmark sent:", title);
    }
  } catch (err) {
    console.error("[Insight] Failed to reach API:", err.message);
  }
}

/**
 * Listen for new bookmarks.
 */
chrome.bookmarks.onCreated.addListener(async (id, bookmark) => {
  // Folders don't have a URL — skip them
  if (!bookmark.url) return;

  await sendBookmark(bookmark.url, bookmark.title);
});
```

- [ ] **Step 2: Commit**

```bash
git add chrome-extension/background.js
git commit -m "feat: add background service worker for bookmark capture"
```

---

### Task 4: Manual testing — load and verify

This task has no code to write. It validates the extension end-to-end.

**Prerequisites:**
- The Phase 1 FastAPI backend is running: `cd backend && uvicorn app.main:app --reload --port 8000`
- A `.env` file in `backend/` with `API_KEY=change-me` (or whatever key you choose)

- [ ] **Step 1: Load the extension as unpacked**

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer mode** (toggle in top right)
3. Click **Load unpacked**
4. Select the `chrome-extension/` directory
5. Verify the extension appears with no errors

- [ ] **Step 2: Configure the extension**

1. Click **Details** on the Insight extension, then **Extension options** (or right-click the extension icon > Options)
2. Set **API URL** to `http://localhost:8000`
3. Set **API Key** to `change-me` (must match `API_KEY` in backend `.env`)
4. Click **Save**

- [ ] **Step 3: Test bookmark capture**

1. Navigate to any page (e.g., `https://news.ycombinator.com`)
2. Press `Cmd+D` (Mac) or `Ctrl+D` (Windows/Linux) to bookmark it
3. Confirm the bookmark is saved

- [ ] **Step 4: Verify the item arrived in the API**

```bash
curl http://localhost:8000/api/items
```

Expected: The bookmarked URL appears in the `items` array with `"source": "chrome"` and `"status": "pending"`.

- [ ] **Step 5: Check service worker logs for errors**

1. Go to `chrome://extensions/`
2. Click **Inspect views: service worker** under the Insight extension
3. Check the Console tab — you should see `[Insight] Bookmark sent: <title>`

- [ ] **Step 6: Test error handling — stop the backend**

1. Stop the uvicorn server (`Ctrl+C`)
2. Bookmark another page
3. Check service worker console — should see `[Insight] Failed to reach API: ...`
4. Restart the backend — the missed bookmark will not be retried (acceptable for v1)

---

## Phase 2 Completion Checklist

- [ ] `chrome-extension/manifest.json` uses Manifest V3 with `bookmarks` and `storage` permissions
- [ ] `chrome-extension/background.js` listens to `chrome.bookmarks.onCreated` and POSTs to the API
- [ ] `chrome-extension/options.html` + `options.js` allow configuring API URL and API key
- [ ] Settings persist in `chrome.storage.sync`
- [ ] Extension loads as unpacked with no errors in `chrome://extensions/`
- [ ] Bookmarking a page in Chrome creates an item in the backend within seconds
- [ ] Missing API key logs a warning instead of crashing
- [ ] Network errors are caught and logged, not thrown
