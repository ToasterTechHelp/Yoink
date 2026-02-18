"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ComponentData } from "@/lib/api";

interface ComponentCardProps {
  component: ComponentData;
  imageUrl: string;
  isTransparent: boolean;
  onToggleTransparent: () => void;
}

export function ComponentCard({
  component,
  imageUrl,
  isTransparent,
  onToggleTransparent,
}: ComponentCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const imgPromise = fetch(imageUrl, {
      mode: "cors",
      cache: "no-store",
    }).then(async (response) => {
      if (!response.ok) throw new Error("Network error");
      const blob = await response.blob();
      return new Blob([blob], { type: blob.type || "image/png" });
    });

    const item = new ClipboardItem({ "image/png": imgPromise });
    navigator.clipboard
      .write([item])
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch((err) => {
        console.error("Clipboard write failed:", err);
        window.open(imageUrl, "_blank");
      });
  };

  return (
    <div className="relative w-fit max-w-sm overflow-hidden rounded-xl border bg-card">
      <div className="relative flex justify-center p-2">
        <img
          src={imageUrl}
          alt={`${component.category} component`}
          className="w-full object-contain [-webkit-touch-callout:none] [-webkit-user-drag:element]"
          draggable
          onContextMenu={(event) => event.preventDefault()}
        />
      </div>

      <div className="flex items-center justify-between px-3 py-2">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {component.category}
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[10px] font-medium text-muted-foreground hover:text-foreground"
            onClick={onToggleTransparent}
            aria-label={`Switch ${component.category} image mode`}
          >
            {isTransparent ? "Transparent" : "Original"}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
            onClick={handleCopy}
            aria-label="Copy component image"
          >
            {copied ? (
              <Check className="h-4 w-4 text-green-500" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
