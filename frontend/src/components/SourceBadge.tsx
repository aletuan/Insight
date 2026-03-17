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
