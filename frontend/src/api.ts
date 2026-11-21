import { EvaluationResult, Verdict } from './types';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export async function checkHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

export async function uploadTenderDocuments(files: File[]) {
  const formData = new FormData();
  for (const f of files) {
    formData.append('files', f);
  }
  const res = await fetch(`${API_BASE}/tenders`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || 'Failed to upload tender documents');
  }
  return res.json() as Promise<{ tender_id: string; documents: string[]; total_pages: number }>;
}

export async function addBidderPack(tenderId: string, name: string, files: File[]) {
  const formData = new FormData();
  formData.append('name', name);
  for (const f of files) {
    formData.append('files', f);
  }
  const res = await fetch(`${API_BASE}/tenders/${tenderId}/bidders`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed adding bidder' }));
    throw new Error(err.detail || 'Failed adding bidder');
  }
  return res.json() as Promise<{ bidder_name: string; documents: string[] }>;
}

export async function evaluateTender(tenderId: string) {
  const res = await fetch(`${API_BASE}/tenders/${tenderId}/evaluate`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Evaluation failed' }));
    throw new Error(err.detail || 'Evaluation failed');
  }
  return res.json() as Promise<EvaluationResult>;
}

export async function loadDemoTender() {
  const res = await fetch(`${API_BASE}/tenders/demo`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Demo load failed' }));
    throw new Error(err.detail || 'Failed loading demo case');
  }
  return res.json() as Promise<{ tender_id: string; evaluation: EvaluationResult }>;
}

export async function submitOverride(
  tenderId: string,
  criterionId: string,
  bidderName: string,
  newVerdict: Verdict,
  justification: string,
  officerName = 'Procurement Officer'
) {
  const res = await fetch(`${API_BASE}/tenders/${tenderId}/override`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      criterion_id: criterionId,
      bidder_name: bidderName,
      new_verdict: newVerdict,
      justification,
      officer_name: officerName,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Override rejected' }));
    throw new Error(err.detail || 'Failed to submit override');
  }
  return res.json() as Promise<EvaluationResult>;
}

export function getMatrixCsvUrl(tenderId: string): string {
  return `${API_BASE}/tenders/${tenderId}/matrix.csv`;
}

export function getPdfReportUrl(tenderId: string): string {
  return `${API_BASE}/tenders/${tenderId}/export/pdf`;
}

export async function fetchConfig() {
  const res = await fetch(`${API_BASE}/config`);
  if (!res.ok) return { auth_enabled: false };
  return res.json() as Promise<{ auth_enabled: boolean }>;
}

export async function fetchTenders() {
  const token = localStorage.getItem('bidparakh_jwt');
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}/tenders`, { headers });
  if (!res.ok) throw new Error('Failed to fetch tenders');
  return res.json();
}

export async function fetchTender(tenderId: string) {
  const token = localStorage.getItem('bidparakh_jwt');
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}/tenders/${tenderId}`, { headers });
  if (!res.ok) throw new Error(`Failed to load tender ${tenderId}`);
  return res.json();
}

export async function fetchTenderAudit(tenderId: string) {
  const token = localStorage.getItem('bidparakh_jwt');
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}/tenders/${tenderId}/audit`, { headers });
  if (!res.ok) throw new Error('Failed to fetch audit trail');
  return res.json();
}

export async function verifyAuditChain() {
  const token = localStorage.getItem('bidparakh_jwt');
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}/audit/verify`, { headers });
  if (!res.ok) throw new Error('Audit verification failed');
  return res.json();
}

export async function loginUser(username: string, password: string) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Authentication failed' }));
    throw new Error(err.detail || 'Login failed');
  }
  return res.json() as Promise<{ access_token: string; token_type: string; role: string }>;
}
