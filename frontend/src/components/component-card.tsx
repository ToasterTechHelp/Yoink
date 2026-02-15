"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ComponentData } from "@/lib/api";

interface ComponentCardProps {
  component: ComponentData;
}

export function ComponentCard({ component }: ComponentCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      const res = await fetch(component.url, { 
        mode: 'cors',
        cache: 'no-store' 
      });
      const blob = await res.blob();
      await navigator.clipboard.write([
        new ClipboardItem({ [blob.type]: blob }),
      ]);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Clipboard copy failed:", error);
      window.open(component.url, "_blank");
    }
  };

  const isText = component.category === "text";

  return (
    <div className="relative w-fit max-w-sm overflow-hidden rounded-xl border bg-card">
      {/* Image — draggable with real src for iPad native drag */}
      <div className="relative flex justify-center p-2">
        <img
          src={component.url}
          alt={`${component.category} component`}
          className="w-full object-contain"
          draggable
          style={{ pointerEvents: "auto" }}
        />
        <Button
          variant="secondary"
          size="icon"
          className="absolute right-2 top-2 h-8 w-8"
          onClick={handleCopy}
        >
          {copied ? (
            <Check className="h-4 w-4 text-green-500" />
          ) : (
            <Copy className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* Label */}
      <div className="px-3 py-2">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {component.category}
        </span>
      </div>
    </div>
  );
}
