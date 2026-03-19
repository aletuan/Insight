"use client";

import { useEffect, useState, useCallback } from "react";
import { listItems } from "@/lib/api";
import type { Item } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import SourceBadge from "@/components/SourceBadge";
import type { TranslationKeys } from "@/lib/i18n";

const sourceFilters: { value: string; labelKey: TranslationKeys }[] = [
  { value: "", labelKey: "timelineAll" },
  { value: "chrome", labelKey: "timelineBookmarks" },
  { value: "youtube", labelKey: "timelineYouTube" },
  { value: "x", labelKey: "timelineX" },
  { value: "threads", labelKey: "timelineThreads" },
  { value: "manual", labelKey: "timelineManual" },
];

export default function TimelinePage() {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState("");
  const [hasMore, setHasMore] = useState(true);
  const { t, dateLocale } = useI18n();

  const PAGE_SIZE = 50;

  const groupByDate = (items: Item[]): Map<string, Item[]> => {
    const groups = new Map<string, Item[]>();
    for (const item of items) {
      const dateKey = new Date(item.created_at).toLocaleDateString(dateLocale, {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
      const existing = groups.get(dateKey) || [];
      existing.push(item);
      groups.set(dateKey, existing);
    }
    return groups;
  };

  const formatTime = (dateStr: string): string => {
    return new Date(dateStr).toLocaleTimeString(dateLocale, {
      hour: "numeric",
      minute: "2-digit",
    });
  };

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
        setError(t("timelineError"));
      } finally {
        setLoading(false);
      }
    },
    [sourceFilter, t],
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
            {t(filter.labelKey)}
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
            {t("timelineLoadMore")}
          </button>
        </div>
      )}

      {loading && (
        <p className="text-ink-faint text-sm text-center py-8">{t("loading")}</p>
      )}

      {!loading && items.length === 0 && !error && (
        <p className="text-ink-faint text-sm text-center py-8">
          {t("timelineNoItems")}
        </p>
      )}
    </div>
  );
}
