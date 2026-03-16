/**
 * TypeScript types for the QA comparison system.
 * PDF is the single source of truth — only deviations where the website
 * is missing or alters PDF content are reported.
 */

// ─── Job lifecycle ───────────────────────────────────

export type JobStatus = "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED";

// ─── QA issue types ──────────────────────────────────

export type QAIssueType =
  | "extra_whitespace"
  | "currency_mismatch"
  | "missing_word"
  | "missing_paragraph";

export type QASeverity = "must_fix" | "minor";

export type QAFilterOption = "ALL" | QAIssueType;

// ─── Location info ───────────────────────────────────

export interface PDFLocation {
  page?: number;
  paragraph?: number;
  column?: string;
}

export interface WebLocation {
  section?: string;
  selector?: string;
}

// ─── Base issue (fields common to all issue types) ───

interface BaseIssue {
  id: string;
  severity: QASeverity;
  title: string;
  explanation: string;
  pdf_location: PDFLocation;
  web_location: WebLocation;
}

// ─── Typed issue interfaces (one per check) ──────────

export interface ExtraWhitespaceIssue extends BaseIssue {
  type: "extra_whitespace";
  space_count: number; // how many consecutive spaces found
  context_before: string; // web text immediately before the spaces
  context_after: string; // web text immediately after the spaces
}

export interface CurrencyMismatchIssue extends BaseIssue {
  type: "currency_mismatch";
  pdf_symbol: string; // exact prefix from PDF  e.g. "H"
  web_symbol: string; // exact prefix from site e.g. "Rs."
  numeric_value: string; // the number, commas stripped e.g. "1630.58"
  unit: string; // e.g. "Crores" or ""
  context_before: string; // web text before the figure
  context_after: string; // web text after the figure
}

export interface MissingWordIssue extends BaseIssue {
  type: "missing_word";
  missing_tokens: string[]; // words present in PDF, absent from web
  context_before: string; // up to 6 words before the missing group
  context_after: string; // up to 6 words after the missing group
}

export interface MissingParagraphIssue extends BaseIssue {
  type: "missing_paragraph";
  paragraph_text: string; // full paragraph text from PDF
}

// ─── Discriminated union — use this everywhere ───────

export type QAIssue =
  | ExtraWhitespaceIssue
  | CurrencyMismatchIssue
  | MissingWordIssue
  | MissingParagraphIssue;

// ─── QA summary ──────────────────────────────────────

export interface QASummary {
  must_fix: number;
  minor: number;
  extra_whitespace_count: number;
  currency_mismatch_count: number;
  missing_word_count: number;
  missing_paragraph_count: number;
}

// ─── Full job response ───────────────────────────────

export interface JobResponse {
  status: JobStatus;
  progress: number;
  message?: string;
  error?: string;

  // QA report fields (present when status === 'COMPLETE')
  brand?: string;
  pdf_source?: string;
  web_source?: string;
  run_date?: string;
  overall?: "needs_fixing" | "minor_issues" | "all_clear";
  summary?: QASummary;
  issues?: QAIssue[];
}

// ─── Job creation response ───────────────────────────

export interface JobCreatedResponse {
  job_id: string;
  poll_url: string;
}

// ─── Crop coordinates ────────────────────────────────

export interface CropCoordinates {
  /** 0.0–1.0, fraction of page height from top */
  top: number;
  /** 0.0–1.0, fraction of page height from top */
  bottom: number;
  /** 0.0–1.0, fraction of page width from left */
  left: number;
  /** 0.0–1.0, fraction of page width from left */
  right: number;
}

// ─── Frontend process request ────────────────────────

export interface ProcessRequest {
  url: string;
  crop_top: number;
  crop_bottom: number;
  crop_left: number;
  crop_right: number;
  page_range_start: number;
  page_range_end: number;
}
