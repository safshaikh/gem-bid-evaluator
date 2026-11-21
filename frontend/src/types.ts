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
