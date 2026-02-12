"use client";

import { useCallback, useState } from "react";
import { FileUp, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useYoinkStore } from "@/store/useYoinkStore";

interface DropzoneProps {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "image/png",
  "image/jpeg",
];

export function Dropzone({ onFileSelected, disabled }: DropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const activeJobStatus = useYoinkStore((s) => s.activeJobStatus);
  const isProcessing = activeJobStatus !== "idle" && activeJobStatus !== "failed";

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (disabled || isProcessing) return;

      const file = e.dataTransfer.files[0];
      if (file && ACCEPTED_TYPES.includes(file.type)) {
        onFileSelected(file);
      }
    },
    [onFileSelected, disabled, isProcessing]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        onFileSelected(file);
      }
      e.target.value = "";
    },
    [onFileSelected]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled && !isProcessing) setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      className={`
        relative flex flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed p-8 transition-all
        ${
          isDragging
            ? "border-orange-500 bg-orange-50"
            : "border-muted-foreground/25 bg-gradient-to-b from-orange-500/5 to-red-500/5"
        }
        ${disabled || isProcessing ? "pointer-events-none opacity-50" : "cursor-pointer hover:border-orange-500/50"}
      `}
    >
      <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-gradient-to-br from-orange-500 to-red-500 text-white">
        <FileText className="h-7 w-7" />
      </div>

      <label className="cursor-pointer">
        <input
          type="file"
          className="hidden"
          accept=".pdf,.ppt,.pptx,.png,.jpg,.jpeg"
          onChange={handleFileInput}
          disabled={disabled || isProcessing}
        />
        <Button
          variant="outline"
          className="pointer-events-none gap-2"
          tabIndex={-1}
        >
          <FileUp className="h-4 w-4" />
          CHOOSE FILES
        </Button>
      </label>

      <p className="text-sm text-muted-foreground">or drop files here</p>
      <p className="text-xs text-muted-foreground/60">PDFs over 100 pages will be limited to the first 100.</p>
    </div>
  );
}
