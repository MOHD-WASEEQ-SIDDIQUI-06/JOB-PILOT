export type JobAnalysis = {
  id: string;
  title: string;
  company: string;
  location: string;
  match_score: number;
  matching_skills: string[];
  missing_skills: string[];
  recommendation: string;
  explanation: string;
};

export type JobCandidate = {
  job_title: string;
  location: string;
  skills: string[];
  experience: string;
  resume_text?: string;
};

export type JobOpportunity = {
  id: string;
  title: string;
  company: string;
  location: string;
  description: string;
  url: string;
  source: string;
};

export type AnalyzeJobsPayload = {
  candidate: JobCandidate;
  jobs: JobOpportunity[];
};

export type JobDiscoveryResult = {
  id: string;
  title: string;
  company: string;
  location: string;
  description: string;
  url: string;
  source: string;
};

export type PreparationPackage = {
  job_id: string;
  match_score: number;
  why_match: string[];
  missing_skills: string[];
  resume_bullet_suggestions: string[];
  cover_letter_draft: string;
  requires_human_review: boolean;
  review_status: 'pending' | 'approved' | 'rejected';
  reviewed_at: string | null;
  application_status: 'not_submitted';
};

export type WorkflowState = {
  workflow_id: string;
  status: string;
  discovered_jobs: JobDiscoveryResult[];
  analyzed_jobs: JobAnalysis[];
  ranked_jobs: JobAnalysis[];
  strong_matches: JobAnalysis[];
  preparation_packages: PreparationPackage[];
  requires_human_review: boolean;
};

export type ReviewDecision = 'approve' | 'reject';
