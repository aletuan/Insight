"use client";

import type { DigestCluster as DigestClusterType } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import SourceBadge from "./SourceBadge";

interface DigestClusterProps {
  cluster: DigestClusterType;
}

export default function DigestCluster({ cluster }: DigestClusterProps) {
  const { locale } = useI18n();

  const label = locale === "vi" && cluster.label_vi ? cluster.label_vi : cluster.label;
  const insight = locale === "vi" && cluster.insight_vi ? cluster.insight_vi : cluster.insight;

  return (
    <section className="mb-12">
      <h2 className="mb-3">{label}</h2>
      <p className="prose-insight mb-6">{insight}</p>
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
