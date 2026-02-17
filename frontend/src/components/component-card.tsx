"use client";

import { useRef, useState, type DragEvent } from "react";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ComponentData } from "@/lib/api";

interface ComponentCardProps {
  component: ComponentData;
}

const TRANSPARENT_PNG_DATA_URL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+lmV0AAAAASUVORK5CYII=";

export function ComponentCard({ component }: ComponentCardProps) {
  const [copied, setCopied] = useState(false);
  const [dragPaneKey, setDragPaneKey] = useState(0);
  const visualImageRef = useRef<HTMLImageElement | null>(null);

  const handleCopy = () => {
    const imgPromise = fetch(component.url, {
      mode: "cors",
      cache: "no-store",
    }).then(async (response) => {
      if (!response.ok) throw new Error("Network error");
      const blob = await response.blob();
      return new Blob([blob], { type: "image/png" });
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
        window.open(component.url, "_blank");
      });
  };

  const handleGlassPaneDragStart = (event: DragEvent<HTMLImageElement>) => {
    const dt = event.dataTransfer;
    dt.effectAllowed = "copy";
    dt.setData("text/plain", component.url);
    dt.setData("text/uri-list", component.url);
    dt.setData("text/html", `<img src="${component.url}" alt="component image">`);

    if (!visualImageRef.current) return;
    const preview = visualImageRef.current;
    dt.setDragImage(preview, preview.width / 2, preview.height / 2);
  };

  const handleGlassPaneDragEnd = () => {
    window.getSelection()?.removeAllRanges();
    // Remount the glass pane to avoid Safari leaving it in a sticky post-drag state.
    setDragPaneKey((value) => value + 1);
  };

  return (
    <div className="relative w-fit max-w-sm overflow-hidden rounded-xl border bg-card">
      <div className="relative flex justify-center p-2">
        <div className="relative w-full">
          <img
            ref={visualImageRef}
            src={component.url}
            alt={`${component.category} component`}
            className="w-full object-contain pointer-events-none"
            draggable={false}
          />
          <img
            key={dragPaneKey}
            src={TRANSPARENT_PNG_DATA_URL}
            alt=""
            aria-hidden="true"
            draggable
            onDragStart={handleGlassPaneDragStart}
            onDragEnd={handleGlassPaneDragEnd}
            onContextMenu={(event) => event.preventDefault()}
            className="absolute inset-0 h-full w-full object-cover opacity-0 [-webkit-touch-callout:none] [-webkit-user-drag:element]"
          />
        </div>
      </div>

      <div className="flex items-center justify-between px-3 py-2">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {component.category}
        </span>
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
  );
}
