"use client";

import { createContext, useContext, useState, useEffect, useCallback } from "react";
import React from "react";
import en from "./en";
import vi from "./vi";
import type { TranslationKeys } from "./en";

export type Locale = "en" | "vi";

const translations = { en, vi } as const;

interface I18nContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKeys) => string;
  dateLocale: string;
}

const I18nContext = createContext<I18nContextType>({
  locale: "en",
  setLocale: () => {},
  t: (key) => en[key],
  dateLocale: "en-US",
});

const STORAGE_KEY = "insight-locale";

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "vi" || stored === "en") {
      setLocaleState(stored);
      document.documentElement.lang = stored;
    }
  }, []);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    localStorage.setItem(STORAGE_KEY, newLocale);
    document.documentElement.lang = newLocale;
  }, []);

  const t = useCallback(
    (key: TranslationKeys): string => translations[locale][key],
    [locale],
  );

  const dateLocale = locale === "vi" ? "vi-VN" : "en-US";

  return React.createElement(
    I18nContext.Provider,
    { value: { locale, setLocale, t, dateLocale } },
    children,
  );
}

export function useI18n() {
  return useContext(I18nContext);
}

export type { TranslationKeys };
