const STORAGE_KEY = "yoink_guest_jobs";
const MAX_ENTRIES = 20;
const MAX_AGE_MS = 12 * 60 * 60 * 1000; // 12 hours

export interface GuestJob {
  id: string;
  title: string;
  created_at: string;
  source_type: string;
  total_pages: number;
  total_components: number;
  status: "completed";
  categories: string[];
}

export function getGuestJobs(): GuestJob[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const now = Date.now();
    const fresh = parsed.filter(
      (j: GuestJob) => now - new Date(j.created_at).getTime() < MAX_AGE_MS
    );
    // Write back pruned list if any were removed
    if (fresh.length < parsed.length) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(fresh));
    }
    return fresh;
  } catch {
    return [];
  }
}

export function saveGuestJob(job: GuestJob): void {
  try {
    const jobs = getGuestJobs().filter((j) => j.id !== job.id);
    jobs.unshift(job);
    if (jobs.length > MAX_ENTRIES) jobs.length = MAX_ENTRIES;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs));
  } catch {
    // Non-critical — guest history is best-effort
  }
}

export function removeGuestJob(jobId: string): void {
  try {
    const jobs = getGuestJobs().filter((j) => j.id !== jobId);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs));
  } catch {
    // Non-critical
  }
}
