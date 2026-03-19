"use client";

import { useI18n } from "@/lib/i18n";

export default function LanguageSwitcher() {
  const { locale, setLocale } = useI18n();

  return (
    <button
      onClick={() => setLocale(locale === "en" ? "vi" : "en")}
      className="text-sm text-ink-faint hover:text-ink-light transition-colors duration-150"
      aria-label="Switch language"
    >
      {locale === "en" ? "VI" : "EN"}
    </button>
  );
}
