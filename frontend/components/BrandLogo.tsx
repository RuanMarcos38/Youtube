"use client";

import { useState } from "react";

type BrandLogoProps = {
  size?: "sm" | "md" | "lg";
  className?: string;
  markOnly?: boolean;
};

const imageSize = {
  sm: "h-10",
  md: "h-12",
  lg: "h-14",
};

const markSize = {
  sm: "h-10 w-10",
  md: "h-12 w-12",
  lg: "h-14 w-14",
};

function YoutubeMark({ size = "md" }: { size?: BrandLogoProps["size"] }) {
  return (
    <span className={`grid ${markSize[size || "md"]} shrink-0 place-items-center rounded-xl bg-[#ff0000] text-white shadow-sm`}>
      <svg viewBox="0 0 24 24" className="h-1/2 w-1/2" aria-hidden="true">
        <path fill="currentColor" d="m10 8 6 4-6 4V8Z" />
      </svg>
    </span>
  );
}

export default function BrandLogo({ size = "md", className = "", markOnly = false }: BrandLogoProps) {
  const [failed, setFailed] = useState(false);

  if (!failed && !markOnly) {
    return (
      <img
        src="/Logo.png"
        alt="ShortsFlow AI"
        translate="no"
        onError={() => setFailed(true)}
        className={`notranslate ${imageSize[size]} w-auto max-w-full object-contain ${className}`}
      />
    );
  }

  return (
    <span className={`notranslate inline-flex min-w-0 items-center gap-3 ${className}`} aria-label="ShortsFlow AI" translate="no">
      <YoutubeMark size={size} />
      {!markOnly && (
        <span className="min-w-0 leading-none">
          <span className="block whitespace-nowrap text-base font-semibold text-[#111]">ShortsFlow AI</span>
          <span className="mt-1 block whitespace-nowrap text-[10px] font-semibold uppercase text-[#777]">Automação de Shorts</span>
        </span>
      )}
    </span>
  );
}
