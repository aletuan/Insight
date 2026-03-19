"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import LanguageSwitcher from "./LanguageSwitcher";
import type { TranslationKeys } from "@/lib/i18n";

const navItems: { href: string; labelKey: TranslationKeys }[] = [
  { href: "/digest/today", labelKey: "navDigest" },
  { href: "/search", labelKey: "navSearch" },
  { href: "/timeline", labelKey: "navTimeline" },
];

export default function Nav() {
  const pathname = usePathname();
  const { t } = useI18n();

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
          {t("appName")}
        </Link>
        <div className="flex items-center gap-6">
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
              {t(item.labelKey)}
            </Link>
          ))}
          <LanguageSwitcher />
        </div>
      </div>
    </nav>
  );
}
