"use client";

import { useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { useYoinkStore } from "@/store/useYoinkStore";

export function ProcessingOverlay() {
  const status = useYoinkStore((s) => s.activeJobStatus);
  const progress = useYoinkStore((s) => s.activeJobProgress);
  const error = useYoinkStore((s) => s.activeJobError);

  if (status === "idle" || status === "completed") return null;

  const percent =
    progress.total > 0
      ? Math.round((progress.current / progress.total) * 100)
      : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="mx-4 w-full max-w-sm rounded-2xl border bg-card p-6 shadow-lg">
        {status === "failed" ? (
          <div className="text-center">
            <p className="font-semibold text-destructive">Extraction Failed</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {error || "An unexpected error occurred."}
            </p>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3">
              <Loader2 className="h-5 w-5 animate-spin text-orange-500" />
              <div className="flex-1">
                <p className="text-sm font-medium">
                  {status === "uploading" && "Uploading..."}
                  {status === "queued" && "Queued..."}
                  {status === "processing" && "Extracting components..."}
                </p>
                {status === "processing" && progress.total > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Page {progress.current} of {progress.total}
                  </p>
                )}
              </div>
            </div>
            {status === "processing" && progress.total > 0 && (
              <Progress value={percent} className="mt-3" />
            )}
          </>
        )}
      </div>
    </div>
  );
}
