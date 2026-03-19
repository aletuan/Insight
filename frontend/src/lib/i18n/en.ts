const en = {
  // Nav
  appName: "Insight",
  navDigest: "Digest",
  navSearch: "Search",
  navTimeline: "Timeline",

  // Common
  loading: "Loading...",
  errorBackend: "Failed to load. Is the backend running?",

  // Digest
  digestNoDigest: "No digest available for this date.",
  digestErrorLoad: "Failed to load digest. Is the backend running?",
  digestGoToday: "Go to today",
  digestPrev: "prev",
  digestNext: "next",
  digestItems: "items",
  digestClusters: "clusters",
  digestMinRead: "min read",
  digestConnections: "Connections",

  // Search
  searchPlaceholder: "Search your knowledge...",
  searching: "Searching...",
  searchFailed: "Search failed. Is the backend running?",
  searchNoResults: "No results found.",

  // Timeline
  timelineAll: "All",
  timelineBookmarks: "Bookmarks",
  timelineYouTube: "YouTube",
  timelineX: "X",
  timelineThreads: "Threads",
  timelineManual: "Manual",
  timelineLoadMore: "Load more",
  timelineNoItems: "No items yet.",
  timelineError: "Failed to load items. Is the backend running?",
} as const;

export type TranslationKeys = keyof typeof en;
export default en;
