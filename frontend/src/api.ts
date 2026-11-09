import type {
  AgentRun,
  AgentRunResult,
  AgentSettings,
  AgentSource,
  Job,
  JobInput,
  LinkedInImportResult,
  Region,
  ResumeProfile,
  SourceType,
  Status,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function getJobs(region: string, status: Status | "All statuses"): Promise<Job[]> {
  const params = new URLSearchParams();
  if (region !== "All regions") params.set("region", region);
  if (status !== "All statuses") params.set("status", status);
  return request(`/jobs${params.size ? `?${params.toString()}` : ""}`);
}

export const seedJobs = () => request<Job[]>("/jobs/seed", { method: "POST" });
export const createJob = (job: JobInput) =>
  request<Job>("/jobs", { method: "POST", body: JSON.stringify(job) });
export const updateJobStatus = (id: number, status: Status) =>
  request<Job>(`/jobs/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
export const deleteJob = (id: number) => request<void>(`/jobs/${id}`, { method: "DELETE" });
export const syncJob = (id: number) =>
  request<{ synced: number; message: string }>(`/jobs/${id}/sync`, { method: "POST" });
export const getProfile = () => request<ResumeProfile | null>("/profile");
export const deleteProfile = () => request<void>("/profile", { method: "DELETE" });
export const refreshRecommendations = () =>
  request<{ updated: number; message: string }>("/recommendations", { method: "POST" });
export const getAgentSettings = () => request<AgentSettings>("/agent/settings");
export const getAgentSources = () => request<AgentSource[]>("/agent/sources");
export const getAgentRuns = () => request<AgentRun[]>("/agent/runs");
export const runAgent = () => request<AgentRunResult>("/agent/run", { method: "POST" });
export const saveAgentSettings = (intervalMinutes: number, minimumMatchScore: number) =>
  request<AgentSettings>("/agent/settings", {
    method: "PUT",
    body: JSON.stringify({ interval_minutes: intervalMinutes, minimum_match_score: minimumMatchScore }),
  });
export const addAgentSource = (source: { name: string; source_type: SourceType; url: string; region: Region }) =>
  request<AgentSource>("/agent/sources", { method: "POST", body: JSON.stringify(source) });
export const deleteAgentSource = (id: number) =>
  request<void>(`/agent/sources/${id}`, { method: "DELETE" });
export const importLinkedInJob = (job: {
  role_title: string;
  company: string;
  region: Region;
  location: string;
  description: string;
  source_url: string;
  posted_at: string | null;
}) =>
  request<LinkedInImportResult>("/agent/linkedin", {
    method: "POST",
    body: JSON.stringify(job),
  });

export async function uploadResume(file: File, consent: boolean): Promise<ResumeProfile> {
  const form = new FormData();
  form.set("file", file);
  form.set("consent_to_ai", String(consent));
  const response = await fetch(`${API_URL}/profile/resume`, { method: "POST", body: form });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Resume analysis failed (${response.status})`);
  }
  return (await response.json()) as ResumeProfile;
}

export function parseDescription(description: string) {
  return request<{
    role_title: string;
    company: string;
    region: Job["region"];
    match_score: number;
    hiring_manager_hints: string;
    outreach_pitch: string;
  }>("/parse", { method: "POST", body: JSON.stringify({ description }) });
}
