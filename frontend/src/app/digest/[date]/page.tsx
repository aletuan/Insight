"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getDigest, getDigestToday, ApiError } from "@/lib/api";
import type { Digest } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import DigestCluster from "@/components/DigestCluster";
import DigestConnections from "@/components/DigestConnections";

function getAdjacentDate(dateStr: string, direction: "prev" | "next"): string {
  const date = new Date(dateStr);
  date.setDate(date.getDate() + (direction === "next" ? 1 : -1));
  return date.toISOString().split("T")[0];
}

export default function DigestPage() {
  const params = useParams();
  const router = useRouter();
  const dateParam = params.date as string;
  const { t, dateLocale } = useI18n();

  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    return date.toLocaleDateString(dateLocale, {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  };

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
          setError(t("digestNoDigest"));
        } else {
          setError(t("digestErrorLoad"));
        }
        setLoading(false);
      });
  }, [dateParam, t]);

  if (loading) {
    return (
      <div className="py-16 text-center text-ink-faint text-sm">
        {t("loading")}
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
            {t("digestGoToday")}
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
            &larr; {t("digestPrev")}
          </button>
          <button
            onClick={() =>
              router.push(`/digest/${getAdjacentDate(displayDate, "next")}`)
            }
            className="text-ink-faint hover:text-ink-light text-sm transition-colors"
          >
            {t("digestNext")} &rarr;
          </button>
        </div>
        <h1>{formatDate(displayDate)}</h1>
        <p className="text-ink-faint text-sm mt-1">
          {content.meta.item_count} {t("digestItems")} &middot;{" "}
          {content.meta.cluster_count} {t("digestClusters")} &middot;{" "}
          {content.meta.estimated_read_minutes} {t("digestMinRead")}
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
