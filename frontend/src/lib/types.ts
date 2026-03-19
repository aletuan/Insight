export type Source = "chrome" | "youtube" | "x" | "threads" | "manual";

export interface Item {
  id: string;
  url: string;
  title: string;
  source: Source;
  status: string;
  created_at: string;
  summary: string | null;
  summary_vi?: string | null;
  tags: string[] | null;
  tags_vi?: string[] | null;
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
  summary_vi?: string;
}

export interface DigestCluster {
  label: string;
  label_vi?: string;
  insight: string;
  insight_vi?: string;
  items: DigestClusterItem[];
}

export interface DigestConnection {
  between: [string, string];
  insight: string;
  insight_vi?: string;
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
  label_vi?: string;
  item_count: number;
  created_at: string;
}
