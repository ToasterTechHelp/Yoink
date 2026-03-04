"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Dropzone } from "@/components/dropzone";
import { FeatureCards } from "@/components/feature-cards";
import { SensitivitySlider, PRESET_KEYS } from "@/components/sensitivity-slider";
import { ProcessingOverlay } from "@/components/processing-overlay";
import { JobCard } from "@/components/job-card";
import { RenameUploadDialog } from "@/components/rename-upload-dialog";
import { Badge } from "@/components/ui/badge";
import { createClient } from "@/lib/supabase/client";
import { uploadFile, pollJobStatus, getJobResult, deleteJob } from "@/lib/api";
import { useYoinkStore } from "@/store/useYoinkStore";
import type { GuestResult } from "@/lib/api";
import type { SupabaseJob } from "@/store/useYoinkStore";

export default function Home() {
  const router = useRouter();
  const supabase = useMemo(() => createClient(), []);
  const user = useYoinkStore((s) => s.user);
  const userJobs = useYoinkStore((s) => s.userJobs);
  const slotsUsed = useYoinkStore((s) => s.slotsUsed);
  const setUserJobs = useYoinkStore((s) => s.setUserJobs);
  const setActiveJob = useYoinkStore((s) => s.setActiveJob);
  const updateJobStatus = useYoinkStore((s) => s.updateJobStatus);
  const resetActiveJob = useYoinkStore((s) => s.resetActiveJob);
  const setGuestResult = useYoinkStore((s) => s.setGuestResult);
  const activeJobStatus = useYoinkStore((s) => s.activeJobStatus);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [sensitivityStep, setSensitivityStep] = useState(2);
  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<SupabaseJob | null>(null);

  const getAccessToken = useCallback(async (): Promise<string | undefined> => {
    if (!supabase) return undefined;
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token;
  }, [supabase]);

  // Fetch user jobs from Supabase
  useEffect(() => {
    if (!user || !supabase) {
      setUserJobs([]);
      return;
    }

    const fetchJobs = async () => {
      const { data, error } = await supabase
        .from("jobs")
        .select("*")
        .order("created_at", { ascending: false });

      if (!error && data) {
        setUserJobs(data as SupabaseJob[]);
      }
    };

    fetchJobs();
  }, [user, supabase, setUserJobs]);

  // Poll active job
  const startPolling = useCallback(
    (jobId: string) => {
      if (pollRef.current) clearInterval(pollRef.current);

      pollRef.current = setInterval(async () => {
        try {
          const status = await pollJobStatus(jobId);

          if (status.status === "processing") {
            updateJobStatus("processing", {
              current: status.progress.current_page,
              total: status.progress.total_pages,
            });
          } else if (status.status === "completed") {
            if (pollRef.current) clearInterval(pollRef.current);
            updateJobStatus("completed");

            // Fetch result
            const result = await getJobResult(jobId);

            if ("components" in result) {
              // Guest result — store in Zustand and navigate
              setGuestResult({
                jobId,
                sourceFile: result.source_file,
                totalPages: result.total_pages,
                totalComponents: result.total_components,
                components: (result as GuestResult).components,
              });
              router.push(`/jobs/${jobId}?guest=true`);
            } else {
              // User result — refresh job list and navigate
              if (supabase) {
                const { data } = await supabase
                  .from("jobs")
                  .select("*")
                  .order("created_at", { ascending: false });
                if (data) setUserJobs(data as SupabaseJob[]);
              }
              router.push(`/jobs/${jobId}`);
            }

            resetActiveJob();
          } else if (status.status === "failed") {
            if (pollRef.current) clearInterval(pollRef.current);
            updateJobStatus("failed", undefined, status.error || "Extraction failed");
          }
        } catch {
          // Polling error — keep trying
        }
      }, 1500);
    },
    [updateJobStatus, resetActiveJob, setGuestResult, setUserJobs, supabase, router]
  );

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleFileSelected = useCallback(
    async (file: File) => {
      try {
        setActiveJob("pending");
        updateJobStatus("uploading");

        // Get token if authenticated
        let token: string | undefined;
        if (user) {
          token = await getAccessToken();
        }

        const { job_id } = await uploadFile(file, token, PRESET_KEYS[sensitivityStep]);
        setSensitivityStep(2);
        setActiveJob(job_id);
        updateJobStatus("queued");
        startPolling(job_id);
      } catch (err: any) {
        toast.error(err.message || "Upload failed");
        resetActiveJob();
      }
    },
    [user, getAccessToken, setActiveJob, updateJobStatus, resetActiveJob, startPolling, sensitivityStep]
  );

  const handleDismissProcessing = useCallback(async () => {
    // Stop polling
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    // Reset overlay state
    resetActiveJob();
    // Refresh job list so the "processing" row appears in Recent Uploads
    if (supabase) {
      const { data } = await supabase
        .from("jobs")
        .select("*")
        .order("created_at", { ascending: false });
      if (data) setUserJobs(data as SupabaseJob[]);
    }
  }, [resetActiveJob, supabase, setUserJobs]);

  const handleOpenJob = (jobId: string) => {
    const job = userJobs.find((j) => j.id === jobId);
    if (!job) {
      router.push(`/jobs/${jobId}`);
      return;
    }

    if (job.status === "completed") {
      router.push(`/jobs/${jobId}`);
    } else if (job.status === "processing") {
      // Resume watching the in-flight job — strip UUID hyphens for API compat
      const hexId = jobId.replace(/-/g, "");
      setActiveJob(hexId);
      updateJobStatus("processing");
      startPolling(hexId);
    } else if (job.status === "failed") {
      toast.error("This extraction failed. You can delete it and try again.");
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    try {
      const token = await getAccessToken();
      if (!token) {
        throw new Error("Authentication required");
      }
      await deleteJob(jobId, token);
      setUserJobs(userJobs.filter((j) => j.id !== jobId));
      toast.success("Job deleted");
    } catch (err: any) {
      toast.error(err.message || "Failed to delete job");
    }
  };

  const handleOpenRenameDialog = (job: SupabaseJob) => {
    setRenameTarget(job);
    setRenameDialogOpen(true);
  };

  const closeRenameDialog = () => {
    setRenameDialogOpen(false);
    setRenameTarget(null);
  };

  const handleRenamed = (jobId: string, title: string) => {
    setUserJobs(
      userJobs.map((job) =>
        job.id === jobId
          ? {
              ...job,
              title,
            }
          : job
      )
    );
  };

  const isProcessing =
    activeJobStatus !== "idle" && activeJobStatus !== "failed" && activeJobStatus !== "completed";

  return (
    <>
      <ProcessingOverlay
        canDismiss={!!user}
        onDismiss={handleDismissProcessing}
      />

      <div className="container mx-auto max-w-lg px-4 py-8">
        {/* Hero */}
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold">Extract PDF Components</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Drag and drop your lecture notes here to automatically extract
            diagrams and text for your digital notebook.
          </p>
        </div>

        {/* Dropzone */}
        <div className="mb-4">
          <Dropzone
            onFileSelected={handleFileSelected}
            disabled={isProcessing || (!!user && slotsUsed >= 5)}
          />
        </div>

        {/* Sensitivity Slider */}
        <div className="mb-8">
          <SensitivitySlider
            value={sensitivityStep}
            onChange={setSensitivityStep}
            disabled={isProcessing}
          />
        </div>

        {/* Feature Cards */}
        <div className="mb-10">
          <FeatureCards />
        </div>

        {/* Recent Uploads */}
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Recent Uploads</h2>
            {user && (
              <Badge variant="outline" className="text-xs">
                {slotsUsed}/5
              </Badge>
            )}
          </div>

          {user ? (
            userJobs.length > 0 ? (
              <div className="space-y-2">
                {userJobs.map((job) => (
                  <JobCard
                    key={job.id}
                    job={job}
                    onOpen={handleOpenJob}
                    onRename={handleOpenRenameDialog}
                    onDelete={handleDeleteJob}
                  />
                ))}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No uploads yet. Drop a file above to get started.
              </p>
            )
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Log in to view upload history.
            </p>
          )}
        </div>

        {/* Footer */}
        <footer className="mt-12 pb-6 text-center text-xs text-muted-foreground">
          Built with love and magic
        </footer>
      </div>

      <RenameUploadDialog
        open={renameDialogOpen}
        job={renameTarget}
        onClose={closeRenameDialog}
        onRenamed={handleRenamed}
        getAccessToken={getAccessToken}
      />
    </>
  );
}
