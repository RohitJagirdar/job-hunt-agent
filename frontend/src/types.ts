export type Region = "India" | "Japan" | "Singapore";
export type Status = "Wishlist" | "Applied" | "Interviewing" | "Archived";
export type SourceType = "greenhouse" | "lever" | "rss";

export interface Job {
  id: number;
  role_title: string;
  company: string;
  region: Region;
  location: string;
  status: Status;
  match_score: number;
  match_summary: string;
  matched_skills: string[];
  skill_gaps: string[];
  resume_outreach_pitch: string;
  hiring_manager_hints: string;
  outreach_pitch: string;
  description: string;
  source_url: string;
  posted_at: string | null;
  source_type: string;
  created_at: string;
  updated_at: string;
}

export interface ResumeProfile {
  profile_summary: string;
  skills: string[];
  years_experience: number | null;
  seniority: string;
  target_roles: string[];
  achievement_highlights: string[];
}

export interface AgentSettings {
  interval_minutes: number;
  minimum_match_score: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: string;
  last_message: string;
  llm_configured: boolean;
  llm_providers: string[];
  notion_configured: boolean;
  brave_configured: boolean;
}

export interface AgentSource {
  id: number;
  name: string;
  source_type: SourceType;
  url: string;
  region: Region;
  enabled: boolean;
}

export interface AgentRun {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  found_count: number;
  qualified_count: number;
  saved_count: number;
  synced_count: number;
  errors: string[];
}

export interface AgentRunResult {
  run_id: number;
  status: string;
  found_count: number;
  qualified_count: number;
  saved_count: number;
  synced_count: number;
  message: string;
  errors: string[];
}

export interface LinkedInImportResult {
  qualified: boolean;
  job: Job | null;
  match_score: number;
  message: string;
}

export interface JobInput {
  role_title: string;
  company: string;
  region: Region;
  location: string;
  status: Status;
  match_score: number;
  hiring_manager_hints: string;
  outreach_pitch: string;
  description: string;
  source_url: string;
  posted_at: string | null;
}
