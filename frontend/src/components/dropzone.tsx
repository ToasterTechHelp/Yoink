"use client";

import { useCallback, useState } from "react";
import { FileUp, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useYoinkStore } from "@/store/useYoinkStore";

interface DropzoneProps {
  onFilesSelected: (files: File[]) => void;
  disabled?: boolean;
}

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "image/png",
  "image/jpeg",
];

const IMAGE_TYPES = ["image/png", "image/jpeg"];

function collectValidFiles(fileList: FileList): File[] {
  const all = Array.from(fileList).filter((f) => ACCEPTED_TYPES.includes(f.type));
  if (all.length === 0) return [];
  // If any non-image file is present, only take the first file
  const hasNonImage = all.some((f) => !IMAGE_TYPES.includes(f.type));
  if (hasNonImage) return [all[0]];
  return all;
}

export function Dropzone({ onFilesSelected, disabled }: DropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const activeJobStatus = useYoinkStore((s) => s.activeJobStatus);
  const isProcessing = activeJobStatus !== "idle" && activeJobStatus !== "failed";

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (disabled || isProcessing) return;

      const files = collectValidFiles(e.dataTransfer.files);
      if (files.length > 0) {
        onFilesSelected(files);
      }
    },
    [onFilesSelected, disabled, isProcessing]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (!e.target.files || e.target.files.length === 0) return;
      const files = collectValidFiles(e.target.files);
      if (files.length > 0) {
        onFilesSelected(files);
      }
      e.target.value = "";
    },
    [onFilesSelected]
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
          multiple
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
      <p className="text-xs text-muted-foreground/60">Select multiple images at once, or a single PDF. PDFs over 100 pages will be limited to the first 100.</p>
    </div>
  );
}
