"use client";

import type { DigestConnection } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

interface DigestConnectionsProps {
  connections: DigestConnection[];
}

export default function DigestConnections({
  connections,
}: DigestConnectionsProps) {
  const { t, locale } = useI18n();

  if (!connections || connections.length === 0) return null;

  return (
    <section className="mt-16 pt-8 border-t border-stone-200">
      <h2 className="text-ink-light text-base font-sans font-normal mb-6">
        {t("digestConnections")}
      </h2>
      <div className="space-y-6">
        {connections.map((conn, i) => (
          <div key={i}>
            <p className="text-xs text-ink-faint font-sans mb-1">
              {conn.between[0]} &harr; {conn.between[1]}
            </p>
            <p className="prose-insight text-sm">
              {locale === "vi" && conn.insight_vi ? conn.insight_vi : conn.insight}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
