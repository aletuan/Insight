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
