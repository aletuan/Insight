"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/digest/today", label: "Digest" },
  { href: "/search", label: "Search" },
  { href: "/timeline", label: "Timeline" },
];

export default function Nav() {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/digest/today") {
      return pathname.startsWith("/digest");
    }
    return pathname.startsWith(href);
  };

  return (
    <nav className="w-full border-b border-stone-200">
      <div className="max-w-content mx-auto px-4 py-4 flex items-center justify-between">
        <Link
          href="/digest/today"
          className="font-serif text-lg font-semibold text-ink no-underline hover:text-ink"
        >
          Insight
        </Link>
        <div className="flex gap-6">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`text-sm no-underline transition-colors duration-150 ${
                isActive(item.href)
                  ? "text-ink font-medium"
                  : "text-ink-faint hover:text-ink-light"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
