"use client";

import { useEffect, useState } from "react";
import Lottie from "lottie-react";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { useYoinkStore } from "@/store/useYoinkStore";

interface ProcessingOverlayProps {
  canDismiss?: boolean;
  onDismiss?: () => void;
}

export function ProcessingOverlay({ canDismiss, onDismiss }: ProcessingOverlayProps) {
  const status = useYoinkStore((s) => s.activeJobStatus);
  const progress = useYoinkStore((s) => s.activeJobProgress);
  const error = useYoinkStore((s) => s.activeJobError);

  const [animationData, setAnimationData] = useState<object | null>(null);

  useEffect(() => {
    fetch("/animations/processing.json")
      .then((res) => res.json())
      .then(setAnimationData)
      .catch(() => setAnimationData(null));
  }, []);

  if (status === "idle" || status === "completed") return null;

  const percent =
    progress.total > 0
      ? Math.round((progress.current / progress.total) * 100)
      : 0;

  const showDismissButton =
    canDismiss && (status === "queued" || status === "processing");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="mx-4 w-full max-w-sm rounded-2xl border bg-card p-6 shadow-lg">
        {status === "failed" ? (
          <div className="text-center">
            <p className="font-semibold text-destructive">Extraction Failed</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {error || "An unexpected error occurred."}
            </p>
            {onDismiss && (
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={onDismiss}
              >
                Dismiss
              </Button>
            )}
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3">
              {animationData ? (
                <Lottie animationData={animationData} loop autoplay className="h-16 w-16 shrink-0" />
              ) : (
                <div className="h-16 w-16 shrink-0" />
              )}
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
            {showDismissButton && (
              <Button
                variant="outline"
                size="sm"
                className="mt-4 w-full"
                onClick={onDismiss}
              >
                Continue in background
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
