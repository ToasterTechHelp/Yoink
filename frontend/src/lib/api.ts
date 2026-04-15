const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function buildTransparentRenderUrl(src: string): string {
  const encodedSrc = encodeURIComponent(src);
  return `${API_URL}/api/v1/render/transparent.png?src=${encodedSrc}`;
}

export interface JobStatus {
  job_id: string;
  status: "queued" | "processing" | "completed" | "failed";
  filename: string;
  progress: { current_page: number; total_pages: number };
  error: string | null;
  created_at: string;
}

export interface ComponentData {
  id: number;
  page_number: number;
  category: string;
  original_label: string;
  confidence: number;
  bbox: number[];
  url: string;
}

export interface GuestResult {
  source_file: string;
  total_pages: number;
  total_components: number;
  components: ComponentData[];
  source_type?: "pdf" | "images";
}

export async function uploadFile(
  files: File | File[],
  token?: string,
  sensitivity?: string
): Promise<{ job_id: string; status: string }> {
  const formData = new FormData();
  const fileList = Array.isArray(files) ? files : [files];
  for (const file of fileList) {
    formData.append("files", file);
  }
  if (sensitivity) {
    formData.append("sensitivity", sensitivity);
  }

  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}/api/v1/extract`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Upload failed");
  }

  return res.json();
}

export async function pollJobStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${API_URL}/api/v1/jobs/${jobId}`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to get job status");
  }
  return res.json();
}

export async function getGuestJobResult(
  jobId: string
): Promise<GuestResult> {
  const res = await fetch(`${API_URL}/api/v1/jobs/${jobId}/result`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to get result");
  }
  return res.json();
}

export async function submitFeedback(
  jobId: string,
  type: "bug" | "content_violation",
  message?: string
): Promise<void> {
  const res = await fetch(`${API_URL}/api/v1/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, type, message }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to submit feedback");
  }
}
