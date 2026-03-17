# Phase 5: Web App — Digest View + Search

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a content-first Next.js 14 web app with three views — daily digest, semantic search, and timeline — that calls the FastAPI backend and makes the system a daily-usable product.

**Architecture:** Next.js 14 App Router frontend at `localhost:3000` calling the FastAPI backend at `localhost:8000`. All data fetching happens client-side via a thin fetch wrapper. No server-side data fetching or BFF — the browser talks directly to the API. Styling via Tailwind CSS with a reader-focused typography system using Source Serif 4 and Inter.

**Tech Stack:** Next.js 14 (App Router), TypeScript, Tailwind CSS 3, Google Fonts (Source Serif 4, Inter, JetBrains Mono)

**Spec:** `docs/superpowers/specs/2026-03-17-personal-knowledge-digest-design.md`

---

### Task 1: Next.js project scaffolding

**Files:**
- Create: `frontend/` directory via create-next-app
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Scaffold Next.js project**

```bash
cd /Users/andy/Workspace/Startup/Insight
npx create-next-app@14 frontend --typescript --tailwind --eslint --app --src-dir --no-import-alias
```

When prompted, accept defaults (use App Router, src/ directory, no import alias).

- [ ] **Step 2: Update `frontend/tailwind.config.ts` with custom fonts and theme**

```ts
// frontend/tailwind.config.ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Source Serif 4"', "Georgia", "serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "monospace"],
      },
      maxWidth: {
        content: "640px",
      },
      colors: {
        ink: "#1a1a1a",
        "ink-light": "#6b7280",
        "ink-faint": "#9ca3af",
        surface: "#fafaf9",
        "surface-hover": "#f5f5f4",
        accent: "#2563eb",
        "accent-hover": "#1d4ed8",
      },
    },
  },
  plugins: [],
};
export default config;
```

- [ ] **Step 3: Replace `frontend/src/app/globals.css`**

```css
/* frontend/src/app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html {
    font-size: 17px;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  body {
    @apply bg-surface text-ink font-sans leading-relaxed;
  }

  h1, h2, h3 {
    @apply font-serif font-semibold tracking-tight;
  }

  h1 {
    @apply text-3xl leading-tight;
  }

  h2 {
    @apply text-xl leading-snug;
  }

  a {
    @apply text-accent hover:text-accent-hover transition-colors duration-150;
  }

  /* Insight paragraphs use serif */
  .prose-insight {
    @apply font-serif text-base leading-relaxed text-ink;
  }

  /* Source badges — tiny monospace whispers */
  .source-badge {
    @apply font-mono text-[10px] uppercase tracking-widest text-ink-faint select-none;
  }

  /* Underline input style */
  .input-underline {
    @apply w-full bg-transparent border-0 border-b border-ink-faint
           focus:border-ink focus:outline-none focus:ring-0
           font-sans text-lg py-2 transition-colors duration-200
           placeholder:text-ink-faint;
  }
}
```

- [ ] **Step 4: Update `frontend/src/app/layout.tsx` with Google Fonts**

```tsx
// frontend/src/app/layout.tsx
import type { Metadata } from "next";
import { Source_Serif_4, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Insight",
  description: "Personal Knowledge Digest",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${sourceSerif.variable} ${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 5: Verify it runs**

```bash
cd /Users/andy/Workspace/Startup/Insight/frontend
npm run dev
```

Visit `http://localhost:3000` — should see a blank page with the correct background color (`#fafaf9`).

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Next.js 14 frontend with Tailwind and typography system"
```

---

### Task 2: Layout and Nav component

**Files:**
- Create: `frontend/src/components/Nav.tsx`
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Create `frontend/src/components/Nav.tsx`**

```tsx
// frontend/src/components/Nav.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/digest/today", label: "Digest" },
  { href: "/search", label: "Search" },
  { href: "/timeline", label: "Timeline" },
];

export default function Nav() {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/digest/today") {
      return pathname.startsWith("/digest");
    }
    return pathname.startsWith(href);
  };

  return (
    <nav className="w-full border-b border-stone-200">
      <div className="max-w-content mx-auto px-4 py-4 flex items-center justify-between">
        <Link
          href="/digest/today"
          className="font-serif text-lg font-semibold text-ink no-underline hover:text-ink"
        >
          Insight
        </Link>
        <div className="flex gap-6">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`text-sm no-underline transition-colors duration-150 ${
                isActive(item.href)
                  ? "text-ink font-medium"
                  : "text-ink-faint hover:text-ink-light"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Update `frontend/src/app/layout.tsx` to include Nav**

Add the Nav component inside `<body>`:

```tsx
// frontend/src/app/layout.tsx
import type { Metadata } from "next";
import { Source_Serif_4, Inter, JetBrains_Mono } from "next/font/google";
import Nav from "@/components/Nav";
import "./globals.css";

const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Insight",
  description: "Personal Knowledge Digest",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${sourceSerif.variable} ${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body>
        <Nav />
        <main className="max-w-content mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Nav.tsx frontend/src/app/layout.tsx
git commit -m "feat: add Nav component with digest/search/timeline links"
```

---

### Task 3: API client utility

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/types.ts`

- [ ] **Step 1: Create `frontend/src/lib/types.ts`**

```ts
// frontend/src/lib/types.ts

export type Source = "chrome" | "youtube" | "x" | "threads" | "manual";

export interface Item {
  id: string;
  url: string;
  title: string;
  source: Source;
  status: string;
  created_at: string;
  summary: string | null;
  tags: string[] | null;
  cluster_id: number | null;
  processed_at: string | null;
}

export interface ItemList {
  items: Item[];
  total: number;
}

export interface DigestClusterItem {
  id: string;
  title: string;
  url: string;
  source: Source;
  summary: string;
}

export interface DigestCluster {
  label: string;
  insight: string;
  items: DigestClusterItem[];
}

export interface DigestConnection {
  between: [string, string];
  insight: string;
}

export interface DigestMeta {
  item_count: number;
  cluster_count: number;
  estimated_read_minutes: number;
}

export interface DigestContent {
  clusters: DigestCluster[];
  connections: DigestConnection[];
  meta: DigestMeta;
}

export interface Digest {
  id: number;
  date: string;
  content: DigestContent;
  item_count: number;
  created_at: string;
}

export interface Cluster {
  id: number;
  label: string;
  item_count: number;
  created_at: string;
}
```

- [ ] **Step 2: Create `frontend/src/lib/api.ts`**

```ts
// frontend/src/lib/api.ts

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(response.status, `API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// --- Digest ---

import type { Digest, ItemList } from "./types";

export async function getDigest(date: string): Promise<Digest> {
  return fetchApi<Digest>(`/api/digest/${date}`);
}

export async function getDigestToday(): Promise<Digest> {
  return fetchApi<Digest>("/api/digest/today");
}

// --- Items / Search ---

export async function searchItems(query: string): Promise<ItemList> {
  const encoded = encodeURIComponent(query);
  return fetchApi<ItemList>(`/api/items?q=${encoded}&limit=20`);
}

export async function listItems(params?: {
  source?: string;
  limit?: number;
  offset?: number;
}): Promise<ItemList> {
  const searchParams = new URLSearchParams();
  if (params?.source) searchParams.set("source", params.source);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));
  const qs = searchParams.toString();
  return fetchApi<ItemList>(`/api/items${qs ? `?${qs}` : ""}`);
}

export { ApiError };
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/
git commit -m "feat: add API client utility with types for digest, items, and search"
```

---

### Task 4: Digest view page + DigestCluster + SourceBadge components

**Files:**
- Create: `frontend/src/components/SourceBadge.tsx`
- Create: `frontend/src/components/DigestCluster.tsx`
- Create: `frontend/src/components/DigestConnections.tsx`
- Create: `frontend/src/app/digest/[date]/page.tsx`

- [ ] **Step 1: Create `frontend/src/components/SourceBadge.tsx`**

```tsx
// frontend/src/components/SourceBadge.tsx
import type { Source } from "@/lib/types";

const sourceAbbrev: Record<Source, string> = {
  chrome: "bm",
  youtube: "yt",
  x: "x",
  threads: "th",
  manual: "mn",
};

interface SourceBadgeProps {
  source: Source;
}

export default function SourceBadge({ source }: SourceBadgeProps) {
  return <span className="source-badge">{sourceAbbrev[source]}</span>;
}
```

- [ ] **Step 2: Create `frontend/src/components/DigestCluster.tsx`**

```tsx
// frontend/src/components/DigestCluster.tsx
import type { DigestCluster as DigestClusterType } from "@/lib/types";
import SourceBadge from "./SourceBadge";

interface DigestClusterProps {
  cluster: DigestClusterType;
}

export default function DigestCluster({ cluster }: DigestClusterProps) {
  return (
    <section className="mb-12">
      <h2 className="mb-3">{cluster.label}</h2>
      <p className="prose-insight mb-6">{cluster.insight}</p>
      <ul className="space-y-2">
        {cluster.items.map((item) => (
          <li key={item.id} className="flex items-baseline gap-3">
            <SourceBadge source={item.source} />
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm hover:underline"
            >
              {item.title}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 3: Create `frontend/src/components/DigestConnections.tsx`**

```tsx
// frontend/src/components/DigestConnections.tsx
import type { DigestConnection } from "@/lib/types";

interface DigestConnectionsProps {
  connections: DigestConnection[];
}

export default function DigestConnections({
  connections,
}: DigestConnectionsProps) {
  if (!connections || connections.length === 0) return null;

  return (
    <section className="mt-16 pt-8 border-t border-stone-200">
      <h2 className="text-ink-light text-base font-sans font-normal mb-6">
        Connections
      </h2>
      <div className="space-y-6">
        {connections.map((conn, i) => (
          <div key={i}>
            <p className="text-xs text-ink-faint font-sans mb-1">
              {conn.between[0]} &harr; {conn.between[1]}
            </p>
            <p className="prose-insight text-sm">{conn.insight}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Create `frontend/src/app/digest/[date]/page.tsx`**

```tsx
// frontend/src/app/digest/[date]/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getDigest, getDigestToday, ApiError } from "@/lib/api";
import type { Digest } from "@/lib/types";
import DigestCluster from "@/components/DigestCluster";
import DigestConnections from "@/components/DigestConnections";

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function getAdjacentDate(dateStr: string, direction: "prev" | "next"): string {
  const date = new Date(dateStr);
  date.setDate(date.getDate() + (direction === "next" ? 1 : -1));
  return date.toISOString().split("T")[0];
}

export default function DigestPage() {
  const params = useParams();
  const router = useRouter();
  const dateParam = params.date as string;

  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);

    const fetchDigest =
      dateParam === "today" ? getDigestToday() : getDigest(dateParam);

    fetchDigest
      .then((data) => {
        setDigest(data);
        setLoading(false);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setError("No digest available for this date.");
        } else {
          setError("Failed to load digest. Is the backend running?");
        }
        setLoading(false);
      });
  }, [dateParam]);

  if (loading) {
    return (
      <div className="py-16 text-center text-ink-faint text-sm">
        Loading...
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-16 text-center">
        <p className="text-ink-light text-sm">{error}</p>
        {dateParam !== "today" && (
          <button
            onClick={() => router.push("/digest/today")}
            className="mt-4 text-sm text-accent hover:text-accent-hover"
          >
            Go to today
          </button>
        )}
      </div>
    );
  }

  if (!digest) return null;

  const { content } = digest;
  const displayDate =
    dateParam === "today" ? digest.date : dateParam;

  return (
    <article>
      {/* Date header */}
      <header className="mb-12">
        <div className="flex items-center justify-between mb-2">
          <button
            onClick={() =>
              router.push(`/digest/${getAdjacentDate(displayDate, "prev")}`)
            }
            className="text-ink-faint hover:text-ink-light text-sm transition-colors"
          >
            &larr; prev
          </button>
          <button
            onClick={() =>
              router.push(`/digest/${getAdjacentDate(displayDate, "next")}`)
            }
            className="text-ink-faint hover:text-ink-light text-sm transition-colors"
          >
            next &rarr;
          </button>
        </div>
        <h1>{formatDate(displayDate)}</h1>
        <p className="text-ink-faint text-sm mt-1">
          {content.meta.item_count} items &middot;{" "}
          {content.meta.cluster_count} clusters &middot;{" "}
          {content.meta.estimated_read_minutes} min read
        </p>
      </header>

      {/* Clusters */}
      {content.clusters.map((cluster, i) => (
        <DigestCluster key={i} cluster={cluster} />
      ))}

      {/* Cross-cluster connections */}
      <DigestConnections connections={content.connections} />
    </article>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ frontend/src/app/digest/
git commit -m "feat: add digest view with DigestCluster, SourceBadge, and date navigation"
```

---

### Task 5: Search page + SearchBar component

**Files:**
- Create: `frontend/src/components/SearchBar.tsx`
- Create: `frontend/src/app/search/page.tsx`

- [ ] **Step 1: Create `frontend/src/components/SearchBar.tsx`**

```tsx
// frontend/src/components/SearchBar.tsx
"use client";

import { useState, useCallback } from "react";

interface SearchBarProps {
  onSearch: (query: string) => void;
  initialQuery?: string;
}

export default function SearchBar({ onSearch, initialQuery = "" }: SearchBarProps) {
  const [query, setQuery] = useState(initialQuery);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = query.trim();
      if (trimmed) {
        onSearch(trimmed);
      }
    },
    [query, onSearch],
  );

  return (
    <form onSubmit={handleSubmit} className="mb-12">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search your knowledge..."
        className="input-underline"
        autoFocus
      />
    </form>
  );
}
```

- [ ] **Step 2: Create `frontend/src/app/search/page.tsx`**

```tsx
// frontend/src/app/search/page.tsx
"use client";

import { useState } from "react";
import { searchItems } from "@/lib/api";
import type { Item } from "@/lib/types";
import SearchBar from "@/components/SearchBar";
import SourceBadge from "@/components/SourceBadge";

export default function SearchPage() {
  const [results, setResults] = useState<Item[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (query: string) => {
    setLoading(true);
    setError(null);
    setHasSearched(true);

    try {
      const data = await searchItems(query);
      setResults(data.items);
    } catch {
      setError("Search failed. Is the backend running?");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <SearchBar onSearch={handleSearch} />

      {loading && (
        <p className="text-ink-faint text-sm text-center py-8">Searching...</p>
      )}

      {error && (
        <p className="text-ink-light text-sm text-center py-8">{error}</p>
      )}

      {hasSearched && !loading && !error && results.length === 0 && (
        <p className="text-ink-faint text-sm text-center py-8">
          No results found.
        </p>
      )}

      {results.length > 0 && (
        <ul className="space-y-6">
          {results.map((item) => (
            <li key={item.id}>
              <div className="flex items-baseline gap-3 mb-1">
                <SourceBadge source={item.source} />
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-base font-sans hover:underline"
                >
                  {item.title}
                </a>
              </div>
              {item.summary && (
                <p className="text-sm text-ink-light ml-8 leading-relaxed">
                  {item.summary}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SearchBar.tsx frontend/src/app/search/
git commit -m "feat: add search page with SearchBar and vector similarity results"
```

---

### Task 6: Timeline page

**Files:**
- Create: `frontend/src/app/timeline/page.tsx`

- [ ] **Step 1: Create `frontend/src/app/timeline/page.tsx`**

```tsx
// frontend/src/app/timeline/page.tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { listItems } from "@/lib/api";
import type { Item, Source } from "@/lib/types";
import SourceBadge from "@/components/SourceBadge";

const sourceFilters: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "chrome", label: "Bookmarks" },
  { value: "youtube", label: "YouTube" },
  { value: "x", label: "X" },
  { value: "threads", label: "Threads" },
  { value: "manual", label: "Manual" },
];

function groupByDate(items: Item[]): Map<string, Item[]> {
  const groups = new Map<string, Item[]>();
  for (const item of items) {
    const dateKey = new Date(item.created_at).toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
    const existing = groups.get(dateKey) || [];
    existing.push(item);
    groups.set(dateKey, existing);
  }
  return groups;
}

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function TimelinePage() {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState("");
  const [hasMore, setHasMore] = useState(true);

  const PAGE_SIZE = 50;

  const fetchItems = useCallback(
    async (offset: number, append: boolean) => {
      setLoading(true);
      setError(null);

      try {
        const data = await listItems({
          source: sourceFilter || undefined,
          limit: PAGE_SIZE,
          offset,
        });

        if (append) {
          setItems((prev) => [...prev, ...data.items]);
        } else {
          setItems(data.items);
        }

        setHasMore(offset + data.items.length < data.total);
      } catch {
        setError("Failed to load items. Is the backend running?");
      } finally {
        setLoading(false);
      }
    },
    [sourceFilter],
  );

  useEffect(() => {
    fetchItems(0, false);
  }, [fetchItems]);

  const grouped = groupByDate(items);

  return (
    <div>
      {/* Source filter */}
      <div className="flex gap-4 mb-8 flex-wrap">
        {sourceFilters.map((filter) => (
          <button
            key={filter.value}
            onClick={() => setSourceFilter(filter.value)}
            className={`text-sm transition-colors duration-150 ${
              sourceFilter === filter.value
                ? "text-ink font-medium"
                : "text-ink-faint hover:text-ink-light"
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {error && (
        <p className="text-ink-light text-sm text-center py-8">{error}</p>
      )}

      {/* Timeline grouped by day */}
      {Array.from(grouped.entries()).map(([dateLabel, dayItems]) => (
        <section key={dateLabel} className="mb-10">
          <h2 className="text-sm text-ink-faint font-sans font-normal mb-3">
            {dateLabel}
          </h2>
          <ul className="space-y-2">
            {dayItems.map((item) => (
              <li key={item.id} className="flex items-baseline gap-3">
                <span className="text-xs text-ink-faint font-mono w-16 shrink-0">
                  {formatTime(item.created_at)}
                </span>
                <SourceBadge source={item.source} />
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm hover:underline"
                >
                  {item.title}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {/* Load more */}
      {!loading && hasMore && items.length > 0 && (
        <div className="text-center py-8">
          <button
            onClick={() => fetchItems(items.length, true)}
            className="text-sm text-ink-faint hover:text-ink-light transition-colors"
          >
            Load more
          </button>
        </div>
      )}

      {loading && (
        <p className="text-ink-faint text-sm text-center py-8">Loading...</p>
      )}

      {!loading && items.length === 0 && !error && (
        <p className="text-ink-faint text-sm text-center py-8">
          No items yet.
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/timeline/
git commit -m "feat: add timeline page with source filtering and day grouping"
```

---

### Task 7: Root page redirect to /digest/today

**Files:**
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Replace `frontend/src/app/page.tsx`**

```tsx
// frontend/src/app/page.tsx
import { redirect } from "next/navigation";

export default function Home() {
  redirect("/digest/today");
}
```

- [ ] **Step 2: Verify — visiting `http://localhost:3000` redirects to `/digest/today`**

```bash
cd /Users/andy/Workspace/Startup/Insight/frontend
npm run dev
```

Visit `http://localhost:3000` — should redirect to `/digest/today`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat: redirect root page to /digest/today"
```

---

### Task 8: CORS configuration on FastAPI backend

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add CORS middleware to `backend/app/main.py`**

Add the following after the `app = FastAPI(...)` line:

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.items import router as items_router
from app.routers.digest import router as digest_router
from app.routers.clusters import router as clusters_router

app = FastAPI(title="Insight", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(items_router)
app.include_router(digest_router)
app.include_router(clusters_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 2: Verify CORS headers**

Start the backend and test with curl:

```bash
cd /Users/andy/Workspace/Startup/Insight/backend
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
curl -I -X OPTIONS http://localhost:8000/api/items \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET"
```

Expected: Response should include `access-control-allow-origin: http://localhost:3000`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: add CORS middleware allowing Next.js frontend at localhost:3000"
```

---

## Phase 5 Completion Checklist

- [ ] Next.js 14 project scaffolded with App Router, TypeScript, and Tailwind
- [ ] Typography system configured: Source Serif 4 (serif), Inter (sans), JetBrains Mono (mono)
- [ ] Content-first layout with 640px max-width and generous whitespace
- [ ] Nav component with Digest / Search / Timeline links, active state highlighting
- [ ] API client utility (`lib/api.ts`) with typed fetch wrapper for all backend endpoints
- [ ] TypeScript types (`lib/types.ts`) matching the backend Pydantic schemas and digest JSONB structure
- [ ] Digest view at `/digest/[date]` with date navigation (prev/next), cluster display, and cross-cluster connections
- [ ] SourceBadge component rendering tiny monospace abbreviations (bm, yt, x, th, mn)
- [ ] DigestCluster component with cluster label, insight paragraph (serif), and item links
- [ ] Search page at `/search` with underline-style input and similarity-ranked results
- [ ] Timeline page at `/timeline` with chronological day grouping and source filter buttons
- [ ] Root `/` redirects to `/digest/today`
- [ ] CORS configured on FastAPI backend for `localhost:3000`
- [ ] Frontend runs at `http://localhost:3000` and communicates with backend at `http://localhost:8000`
- [ ] No boxes, cards, or borders — typography and spacing only
