"use client";

import Script from "next/script";
import { useEffect, useState } from "react";

const STORAGE_KEY = "shortsflow-platform-language";
const GOOGLE_TRANSLATE_ELEMENT_ID = "shortsflow-google-translate";

type GoogleTranslateWindow = Window & {
  googleTranslateElementInit?: () => void;
  google?: {
    translate?: {
      TranslateElement?: new (options: Record<string, unknown>, elementId: string) => void;
    };
  };
};

const languages = [
  { code: "pt", label: "Português do Brasil" },
  { code: "en", label: "Inglês" },
  { code: "es", label: "Espanhol" },
  { code: "fr", label: "Francês" },
  { code: "de", label: "Alemão" },
  { code: "it", label: "Italiano" },
  { code: "ja", label: "Japonês" },
  { code: "ko", label: "Coreano" },
  { code: "zh-CN", label: "Chinês simplificado" },
  { code: "zh-TW", label: "Chinês tradicional" },
  { code: "ar", label: "Árabe" },
  { code: "hi", label: "Hindi" },
  { code: "ru", label: "Russo" },
  { code: "nl", label: "Holandês" },
  { code: "pl", label: "Polonês" },
  { code: "tr", label: "Turco" },
  { code: "id", label: "Indonésio" },
  { code: "vi", label: "Vietnamita" },
  { code: "th", label: "Tailandês" },
  { code: "uk", label: "Ucraniano" },
  { code: "fa", label: "Persa" },
  { code: "iw", label: "Hebraico" },
  { code: "el", label: "Grego" },
  { code: "sv", label: "Sueco" },
  { code: "no", label: "Norueguês" },
  { code: "da", label: "Dinamarquês" },
  { code: "fi", label: "Finlandês" },
  { code: "cs", label: "Tcheco" },
  { code: "ro", label: "Romeno" },
  { code: "hu", label: "Húngaro" },
  { code: "bg", label: "Búlgaro" },
  { code: "hr", label: "Croata" },
  { code: "sk", label: "Eslovaco" },
  { code: "sl", label: "Esloveno" },
  { code: "sr", label: "Sérvio" },
  { code: "ms", label: "Malaio" },
  { code: "fil", label: "Filipino" },
  { code: "bn", label: "Bengali" },
  { code: "ur", label: "Urdu" },
  { code: "ta", label: "Tâmil" },
  { code: "te", label: "Telugu" },
  { code: "mr", label: "Marata" },
  { code: "gu", label: "Gujarati" },
  { code: "kn", label: "Canarês" },
  { code: "ml", label: "Malaiala" },
  { code: "pa", label: "Panjabi" },
  { code: "sw", label: "Suaíli" },
  { code: "af", label: "Africâner" },
  { code: "sq", label: "Albanês" },
  { code: "am", label: "Amárico" },
  { code: "hy", label: "Armênio" },
  { code: "az", label: "Azerbaijano" },
  { code: "eu", label: "Basco" },
  { code: "be", label: "Bielorrusso" },
  { code: "bs", label: "Bósnio" },
  { code: "ca", label: "Catalão" },
  { code: "ceb", label: "Cebuano" },
  { code: "co", label: "Córsico" },
  { code: "eo", label: "Esperanto" },
  { code: "et", label: "Estoniano" },
  { code: "fy", label: "Frísio" },
  { code: "gl", label: "Galego" },
  { code: "ka", label: "Georgiano" },
  { code: "ha", label: "Hauçá" },
  { code: "haw", label: "Havaiano" },
  { code: "ht", label: "Crioulo haitiano" },
  { code: "hmn", label: "Hmong" },
  { code: "ig", label: "Igbo" },
  { code: "ga", label: "Irlandês" },
  { code: "jw", label: "Javanês" },
  { code: "kk", label: "Cazaque" },
  { code: "km", label: "Khmer" },
  { code: "ku", label: "Curdo" },
  { code: "ky", label: "Quirguiz" },
  { code: "lo", label: "Lao" },
  { code: "la", label: "Latim" },
  { code: "lv", label: "Letão" },
  { code: "lt", label: "Lituano" },
  { code: "lb", label: "Luxemburguês" },
  { code: "mk", label: "Macedônio" },
  { code: "mg", label: "Malgaxe" },
  { code: "mt", label: "Maltês" },
  { code: "mi", label: "Maori" },
  { code: "mn", label: "Mongol" },
  { code: "my", label: "Birmanês" },
  { code: "ne", label: "Nepalês" },
  { code: "ps", label: "Pashto" },
  { code: "qu", label: "Quéchua" },
  { code: "sm", label: "Samoano" },
  { code: "gd", label: "Gaélico escocês" },
  { code: "sn", label: "Shona" },
  { code: "sd", label: "Sindi" },
  { code: "si", label: "Cingalês" },
  { code: "so", label: "Somali" },
  { code: "su", label: "Sundanês" },
  { code: "tg", label: "Tadjique" },
  { code: "ti", label: "Tigrínia" },
  { code: "tk", label: "Turcomeno" },
  { code: "uz", label: "Uzbeque" },
  { code: "cy", label: "Galês" },
  { code: "xh", label: "Xhosa" },
  { code: "yi", label: "Iídiche" },
  { code: "yo", label: "Iorubá" },
  { code: "zu", label: "Zulu" },
];

function writeTranslateCookie(value: string, expires: string) {
  const hostname = window.location.hostname;
  const domains = ["", hostname, hostname.split(".").length > 2 ? `.${hostname.split(".").slice(-2).join(".")}` : ""];
  domains.filter(Boolean).forEach((domain) => {
    document.cookie = [`googtrans=${value}`, "path=/", `domain=${domain}`, expires, "SameSite=Lax"].join("; ");
  });
  document.cookie = [`googtrans=${value}`, "path=/", expires, "SameSite=Lax"].join("; ");
}

function initializeGoogleTranslate() {
  const win = window as GoogleTranslateWindow;
  const container = document.getElementById(GOOGLE_TRANSLATE_ELEMENT_ID);
  if (!container) return;

  const TranslateElement = win.google?.translate?.TranslateElement;
  if (TranslateElement && !container.hasChildNodes()) {
    new TranslateElement({ pageLanguage: "pt", autoDisplay: false }, GOOGLE_TRANSLATE_ELEMENT_ID);
  }
}

function triggerGoogleCombo(code: string) {
  const combo = document.querySelector<HTMLSelectElement>(".goog-te-combo");
  if (!combo) return false;
  combo.value = code;
  combo.dispatchEvent(new Event("change"));
  return true;
}

function applyLanguage(code: string) {
  if (code === "pt") {
    writeTranslateCookie("", "expires=Thu, 01 Jan 1970 00:00:00 GMT");
    window.location.reload();
    return;
  }

  writeTranslateCookie(`/pt/${code}`, "max-age=31536000");
  initializeGoogleTranslate();
  if (triggerGoogleCombo(code)) return;

  window.setTimeout(() => {
    initializeGoogleTranslate();
    if (!triggerGoogleCombo(code)) window.location.reload();
  }, 900);
}

export function LanguageRuntime() {
  useEffect(() => {
    const win = window as GoogleTranslateWindow;
    win.googleTranslateElementInit = initializeGoogleTranslate;
    const saved = window.localStorage.getItem(STORAGE_KEY) || "pt";
    if (saved !== "pt") initializeGoogleTranslate();
  }, []);

  return (
    <>
      <div id={GOOGLE_TRANSLATE_ELEMENT_ID} aria-hidden="true" />
      <Script
        id="shortsflow-google-translate-script"
        src="https://translate.google.com/translate_a/element.js"
        strategy="afterInteractive"
        onReady={() => {
          initializeGoogleTranslate();
          const saved = window.localStorage.getItem(STORAGE_KEY) || "pt";
          if (saved !== "pt") window.setTimeout(() => triggerGoogleCombo(saved), 300);
        }}
      />
    </>
  );
}

export default function LanguageSelector() {
  const [language, setLanguage] = useState("pt");

  useEffect(() => {
    setLanguage(window.localStorage.getItem(STORAGE_KEY) || "pt");
  }, []);

  function changeLanguage(code: string) {
    setLanguage(code);
    window.localStorage.setItem(STORAGE_KEY, code);
    applyLanguage(code);
  }

  return (
    <div className="rounded-lg border border-[#e8e8e8] bg-[#f7f7f7] p-3">
      <label htmlFor="platform-language" className="text-xs font-medium text-[#222]">Idioma da plataforma</label>
      <select
        id="platform-language"
        value={language}
        onChange={(event) => changeLanguage(event.target.value)}
        className="mt-2 w-full rounded-lg border border-[#d8d8d8] bg-white px-3 py-2.5 text-sm outline-none focus:border-[#ff0000]"
      >
        {languages.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
      </select>
      <p className="mt-2 text-[11px] leading-5 text-[#666]">
        O português do Brasil é o idioma original. Outros idiomas usam tradução automática do Google Tradutor em toda a interface.
      </p>
    </div>
  );
}
