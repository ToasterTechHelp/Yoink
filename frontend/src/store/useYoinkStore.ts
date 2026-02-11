import { create } from "zustand";
import type { User } from "@supabase/supabase-js";
import type { ComponentData } from "@/lib/api";

export interface SupabaseJob {
  id: string;
  user_id: string;
  created_at: string;
  status: string;
  title: string;
  total_pages: number;
  total_components: number;
  results: { components: ComponentData[] } | null;
  storage_path: string | null;
}

interface YoinkState {
  // Auth
  user: User | null;
  setUser: (user: User | null) => void;

  // Active processing job (guest or user)
  activeJobId: string | null;
  activeJobStatus: "idle" | "uploading" | "queued" | "processing" | "completed" | "failed";
  activeJobProgress: { current: number; total: number };
  activeJobError: string | null;
  setActiveJob: (jobId: string | null) => void;
  updateJobStatus: (
    status: YoinkState["activeJobStatus"],
    progress?: { current: number; total: number },
    error?: string | null
  ) => void;
  resetActiveJob: () => void;

  // Guest result (ephemeral)
  guestResult: {
    jobId: string;
    sourceFile: string;
    totalPages: number;
    totalComponents: number;
    components: ComponentData[];
  } | null;
  setGuestResult: (result: YoinkState["guestResult"]) => void;

  // User jobs (from Supabase)
  userJobs: SupabaseJob[];
  slotsUsed: number;
  setUserJobs: (jobs: SupabaseJob[]) => void;
}

export const useYoinkStore = create<YoinkState>((set) => ({
  // Auth
  user: null,
  setUser: (user) => set({ user }),

  // Active job
  activeJobId: null,
  activeJobStatus: "idle",
  activeJobProgress: { current: 0, total: 0 },
  activeJobError: null,
  setActiveJob: (jobId) =>
    set({
      activeJobId: jobId,
      activeJobStatus: jobId ? "uploading" : "idle",
      activeJobProgress: { current: 0, total: 0 },
      activeJobError: null,
    }),
  updateJobStatus: (status, progress, error) =>
    set((state) => ({
      activeJobStatus: status,
      activeJobProgress: progress ?? state.activeJobProgress,
      activeJobError: error ?? state.activeJobError,
    })),
  resetActiveJob: () =>
    set({
      activeJobId: null,
      activeJobStatus: "idle",
      activeJobProgress: { current: 0, total: 0 },
      activeJobError: null,
    }),

  // Guest result
  guestResult: null,
  setGuestResult: (result) => set({ guestResult: result }),

  // User jobs
  userJobs: [],
  slotsUsed: 0,
  setUserJobs: (jobs) => set({ userJobs: jobs, slotsUsed: jobs.length }),
}));
