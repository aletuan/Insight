import type { DigestConnection } from "@/lib/types";

interface DigestConnectionsProps {
  connections: DigestConnection[];
}

export default function DigestConnections({
  connections,
}: DigestConnectionsProps) {
  if (!connections || connections.length === 0) return null;

  return (
    <section className="mt-16 pt-8 border-t border-stone-200">
      <h2 className="text-ink-light text-base font-sans font-normal mb-6">
        Connections
      </h2>
      <div className="space-y-6">
        {connections.map((conn, i) => (
          <div key={i}>
            <p className="text-xs text-ink-faint font-sans mb-1">
              {conn.between[0]} &harr; {conn.between[1]}
            </p>
            <p className="prose-insight text-sm">{conn.insight}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
