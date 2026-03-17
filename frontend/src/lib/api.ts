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
