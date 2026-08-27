"use client";

import { useState } from "react";

type BrandLogoProps = {
  size?: "sm" | "md" | "lg";
  className?: string;
  markOnly?: boolean;
};

const imageSize = {
  sm: "h-9 max-w-[150px]",
  md: "h-10 max-w-[176px]",
  lg: "h-12 max-w-[212px]",
};

const markSize = {
  sm: "h-9 w-9",
  md: "h-10 w-10",
  lg: "h-12 w-12",
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
        decoding="async"
        draggable={false}
        onError={() => setFailed(true)}
        className={`notranslate block ${imageSize[size]} w-auto object-contain ${className}`}
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
