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
