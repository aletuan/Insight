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
