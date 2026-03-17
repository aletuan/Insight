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
