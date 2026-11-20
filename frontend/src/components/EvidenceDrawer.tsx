import React, { useState } from 'react';
import { X, ShieldAlert, CheckCircle, FileText, Scale, Loader2, UserCheck, AlertTriangle } from 'lucide-react';
import { Criterion, CriterionResult, OfficerOverride, Verdict } from '../types';
import { submitOverride } from '../api';

interface EvidenceDrawerProps {
  tenderId: string;
  criterion: Criterion;
  bidderName: string;
  result?: CriterionResult;
  override?: OfficerOverride;
  onClose: () => void;
  onOverrideSaved: (updatedEvaluation: any) => void;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({
  tenderId,
  criterion,
  bidderName,
  result,
  override,
  onClose,
  onOverrideSaved,
}) => {
  const currentVerdict: Verdict = override ? override.new_verdict : result ? result.verdict : 'REVIEW';
  const [selectedVerdict, setSelectedVerdict] = useState<Verdict>(currentVerdict);
  const [justification, setJustification] = useState<string>('');
  const [officerName, setOfficerName] = useState<string>('Senior Procurement Officer');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const charCount = justification.trim().length;
  const isJustificationValid = charCount >= 20;

  const handleSubmitOverride = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isJustificationValid) {
      setError('Statutory justification must be at least 20 characters long.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const updated = await submitOverride(
        tenderId,
        criterion.id,
        bidderName,
        selectedVerdict,
        justification.trim(),
        officerName.trim()
      );
      onOverrideSaved(updated);
      setJustification('');
    } catch (err: any) {
      setError(err.message || 'Failed to submit override');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden" aria-labelledby="slide-over-title" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity" onClick={onClose} />

      <div className="pointer-events-none fixed inset-y-0 right-0 flex max-w-full pl-10">
        <div className="pointer-events-auto w-screen max-w-xl bg-white shadow-2xl flex flex-col">
          {/* Header */}
          <div className="px-6 py-5 bg-slate-900 text-white flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold leading-6" id="slide-over-title">
                Evidence Inspection &amp; Statutory Scrutiny
              </h2>
              <p className="text-xs text-slate-300 mt-1 font-mono">
                Bidder: <span className="font-semibold text-white">{bidderName}</span>
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md text-slate-400 hover:text-white p-1.5 focus:outline-none focus:ring-2 focus:ring-white"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 text-sm">
            {/* Criterion Card */}
            <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-900 text-base">{criterion.title}</span>
                <span className="text-xs font-mono bg-slate-200 px-2 py-0.5 rounded text-slate-700">
                  {criterion.id}
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Rule Evaluation Type: <b className="text-slate-800">{criterion.rule_type}</b>
                {criterion.threshold !== undefined && criterion.threshold !== null && (
                  <> &bull; Threshold: <b className="text-slate-800">{criterion.threshold} {criterion.unit || ''}</b></>
                )}
              </p>
              <div className="pt-2 border-t border-slate-200/60 text-xs text-slate-600 space-y-1">
                <div>
                  <b>Tender Source:</b> {criterion.source_doc} (Page {criterion.source_page})
                </div>
                <div className="italic text-slate-500 bg-white p-2 rounded border border-slate-200/80">
                  &ldquo;{criterion.source_quote}&rdquo;
                </div>
              </div>
            </div>

            {/* Verdict & Rule Engine Finding */}
            <div className="p-4 rounded-lg border border-slate-200 space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-800 flex items-center">
                  <Scale className="w-4 h-4 mr-1.5 text-indigo-600" />
                  Deterministic Python Rule Verdict
                </span>
                <span className={`px-2.5 py-1 rounded text-xs font-bold ${
                  result?.verdict === 'PASS'
                    ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                    : result?.verdict === 'FAIL'
                    ? 'bg-rose-100 text-rose-800 border border-rose-300'
                    : 'bg-amber-100 text-amber-800 border border-amber-300'
                }`}>
                  {result?.verdict || 'REVIEW'}
                </span>
              </div>
              <p className="text-xs text-slate-700 leading-relaxed bg-slate-50 p-2.5 rounded border border-slate-100">
                {result?.reason || 'No verified evidence provided.'}
              </p>
            </div>

            {/* Cited Bidder Evidence */}
            <div className="p-4 rounded-lg bg-white border border-slate-200 space-y-2">
              <span className="font-bold text-slate-800 text-xs uppercase tracking-wider flex items-center">
                <FileText className="w-4 h-4 mr-1.5 text-slate-600" />
                Bidder Document Evidence Quote
              </span>
              {result?.evidence_quote ? (
                <div className="space-y-2">
                  <div className="p-3 bg-indigo-50/50 rounded-lg border border-indigo-100 text-xs font-mono text-indigo-950">
                    &ldquo;{result.evidence_quote}&rdquo;
                  </div>
                  <div className="text-xs text-slate-500 flex items-center space-x-3">
                    <span>Cited Page: <b>Page {result.evidence_page || 1}</b></span>
                    <span>&bull;</span>
                    <span className="text-emerald-700 font-semibold flex items-center">
                      <CheckCircle className="w-3.5 h-3.5 mr-1" /> Verified against PDF text layer
                    </span>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-slate-400 italic">No direct textual quote was cited by the bidder submission.</p>
              )}
            </div>

            {/* Speaking Order (If FAIL) */}
            {result?.speaking_order_line && (
              <div className="p-4 rounded-lg bg-rose-50 border border-rose-200 space-y-1.5">
                <span className="text-xs font-bold text-rose-900 uppercase tracking-wider flex items-center">
                  <AlertTriangle className="w-4 h-4 mr-1.5 text-rose-600" />
                  Statutory Rejection Speaking Order Line
                </span>
                <p className="text-xs font-mono text-rose-950 leading-relaxed bg-white/70 p-2.5 rounded border border-rose-200">
                  {result.speaking_order_line}
                </p>
              </div>
            )}

            {/* Active Override Notice */}
            {override && (
              <div className="p-4 rounded-lg bg-purple-50 border border-purple-200 space-y-2">
                <div className="flex items-center justify-between text-xs font-bold text-purple-900">
                  <span className="flex items-center">
                    <ShieldAlert className="w-4 h-4 mr-1.5 text-purple-600" />
                    Recorded Officer Override
                  </span>
                  <span>{override.old_verdict} &rarr; {override.new_verdict}</span>
                </div>
                <p className="text-xs text-purple-950 italic">&ldquo;{override.justification}&rdquo;</p>
                <p className="text-[11px] text-purple-700">
                  Logged by: <b>{override.officer_name}</b> on {override.timestamp.slice(0, 19).replace('T', ' ')} UTC
                </p>
              </div>
            )}

            {/* Officer Override Form */}
            <form onSubmit={handleSubmitOverride} className="p-5 rounded-xl bg-slate-900 text-white space-y-4">
              <div className="border-b border-slate-800 pb-3">
                <h4 className="text-sm font-bold flex items-center">
                  <UserCheck className="w-4 h-4 mr-2 text-indigo-400" />
                  Statutory Procurement Officer Override
                </h4>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  The original rule verdict is preserved in the audit log. Overriding requires legal justification.
                </p>
              </div>

              {error && (
                <div className="p-2.5 rounded bg-rose-950 border border-rose-800 text-rose-300 text-xs">
                  {error}
                </div>
              )}

              <div className="space-y-1">
                <label className="block text-xs font-semibold text-slate-300">Set New Verdict:</label>
                <div className="grid grid-cols-3 gap-2">
                  {(['PASS', 'REVIEW', 'FAIL'] as Verdict[]).map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setSelectedVerdict(v)}
                      className={`py-2 text-xs font-bold rounded-lg border transition-all ${
                        selectedVerdict === v
                          ? v === 'PASS'
                            ? 'bg-emerald-600 border-emerald-400 text-white'
                            : v === 'FAIL'
                            ? 'bg-rose-600 border-rose-400 text-white'
                            : 'bg-amber-600 border-amber-400 text-white'
                          : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
                      }`}
                    >
                      {v}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-semibold text-slate-300">Officer Full Name / Designation:</label>
                <input
                  type="text"
                  value={officerName}
                  onChange={(e) => setOfficerName(e.target.value)}
                  className="w-full text-xs bg-slate-800 border border-slate-700 rounded-md p-2 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  required
                />
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <label className="font-semibold text-slate-300">Statutory Legal Justification (Min 20 chars):</label>
                  <span className={`font-mono text-[11px] ${isJustificationValid ? 'text-emerald-400' : 'text-slate-400'}`}>
                    {charCount} / 20 chars
                  </span>
                </div>
                <textarea
                  rows={3}
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                  placeholder="e.g. Verified original physical chartered accountant certificate produced during the technical committee scrutiny meeting."
                  className="w-full text-xs bg-slate-800 border border-slate-700 rounded-md p-2.5 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={loading || !isJustificationValid}
                className="w-full py-2.5 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-bold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Recording Statutory Override...</span>
                  </>
                ) : (
                  <span>Submit Officer Statutory Override</span>
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};
