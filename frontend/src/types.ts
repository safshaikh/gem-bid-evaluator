export type Verdict = 'PASS' | 'FAIL' | 'REVIEW';

export interface Criterion {
  id: string;
  title: string;
  rule_type: string;
  threshold?: number | null;
  unit?: string | null;
  accepted_doc_types?: string[];
  source_doc: string;
  source_page: number;
  source_quote: string;
  supersedes?: string[];
}

export interface CriterionResult {
  bidder_name: string;
  criterion_id: string;
  verdict: Verdict;
  reason: string;
  evidence_page?: number | null;
  evidence_quote?: string | null;
  speaking_order_line?: string | null;
  bounding_box?: number[] | null;
  source_kind?: string | null;
}

export interface OfficerOverride {
  criterion_id: string;
  bidder_name: string;
  old_verdict: Verdict;
  new_verdict: Verdict;
  justification: string;
  officer_name: string;
  timestamp: string;
}

export interface AtcFlag {
  clause_quote: string;
  clause_text: string;
  matched_void_index?: number | null;
  reason: string;
  verdict: 'FLAG' | 'CLEAR' | 'REVIEW';
  void_quote: string;
}

export interface VoidListItem {
  index: number;
  source_page: number;
  source_quote: string;
  text: string;
}

export interface EvaluationResult {
  tender_id: string;
  cached: boolean;
  degraded: boolean;
  criteria: Criterion[];
  void_list: VoidListItem[];
  atc_flags: AtcFlag[];
  results: CriterionResult[];
  overrides: OfficerOverride[];
  warnings: string[];
}

export interface TenderSummary {
  tender_id: string;
  title: string;
  status: string;
  actor: string;
  created_at: string;
  updated_at: string;
  bidder_count: number;
  document_count: number;
}

export interface AuditLogRow {
  id: number;
  ts: string;
  actor: string;
  action: string;
  tender_id: string;
  payload_json: string;
  prev_hash: string;
  row_hash: string;
}

export interface AuditVerifyResult {
  ok: boolean;
  rows_checked: number;
  first_broken_id: number | null;
  reason: string | null;
}

export interface IngestionSource {
  name: string;
  display_name: string;
  kind: 'demo' | 'local' | 'http';
  description: string;
}

export interface IngestedDocument {
  name: string;
  published_at: string;
  kind: 'main' | 'corrigendum';
  sha256: string;
  order_index?: number;
}

export interface TenderDetails {
  tender_id: string;
  title: string;
  status: string;
  source_name?: string | null;
  source_bid_id?: string | null;
  created_at: string;
  documents: { filename?: string; name?: string; sha256?: string; order_index?: number; page_count?: number }[];
  bidders: { name: string; documents: { filename?: string; name?: string }[] }[];
  evaluation?: EvaluationResult | null;
  overrides: OfficerOverride[];
}

export interface CorrigendumUpdate {
  name: string;
  published_at: string;
  sequence: number;
  sha256: string;
}

export interface CheckUpdatesResponse {
  updates_available: boolean;
  reason?: string;
  new_corrigenda: CorrigendumUpdate[];
}

