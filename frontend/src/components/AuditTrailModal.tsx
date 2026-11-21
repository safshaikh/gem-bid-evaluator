import React, { useEffect, useState } from 'react';
import { X, ShieldAlert, CheckCircle, RefreshCw, Lock } from 'lucide-react';
import { AuditLogRow, AuditVerifyResult } from '../types';
import { fetchTenderAudit, verifyAuditChain } from '../api';

interface AuditTrailModalProps {
  tenderId: string;
  isOpen: boolean;
  onClose: () => void;
}

export const AuditTrailModal: React.FC<AuditTrailModalProps> = ({
  tenderId,
  isOpen,
  onClose,
}) => {
  const [logs, setLogs] = useState<AuditLogRow[]>([]);
  const [verifyResult, setVerifyResult] = useState<AuditVerifyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);

  const loadLogs = async () => {
    try {
      setLoading(true);
      const data = await fetchTenderAudit(tenderId);
      setLogs(data);
    } catch {
      setLogs([]);
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async () => {
    try {
      setVerifying(true);
      const res = await verifyAuditChain();
      setVerifyResult(res);
    } catch {
      setVerifyResult({
        ok: false,
        rows_checked: 0,
        first_broken_id: null,
        reason: 'Verification network request failed',
      });
    } finally {
      setVerifying(false);
    }
  };

  useEffect(() => {
    if (isOpen && tenderId) {
      loadLogs();
      handleVerify();
    }
  }, [isOpen, tenderId]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-3xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="p-5 bg-slate-900 text-white flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-indigo-500/20 rounded-lg border border-indigo-400/30">
              <Lock className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <h2 className="text-base font-bold">Tamper-Evident Audit Trail</h2>
              <p className="text-xs text-slate-400">
                Cryptographic hash-chained event records for Tender #{tenderId.slice(0, 8)}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Verification Status Banner */}
        <div className="p-4 bg-slate-50 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center space-x-2">
            {verifyResult?.ok ? (
              <div className="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-100 text-emerald-900 border border-emerald-300">
                <CheckCircle className="w-4 h-4 mr-1.5 text-emerald-600" />
                Chain intact ({verifyResult.rows_checked} entries verified)
              </div>
            ) : verifyResult ? (
              <div className="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-100 text-rose-900 border border-rose-300">
                <ShieldAlert className="w-4 h-4 mr-1.5 text-rose-600" />
                Broken at entry {verifyResult.first_broken_id || 'unknown'} ({verifyResult.reason})
              </div>
            ) : (
              <div className="text-xs text-slate-500">Checking cryptographic integrity...</div>
            )}
          </div>

          <button
            type="button"
            onClick={handleVerify}
            disabled={verifying}
            className="inline-flex items-center px-3.5 py-1.5 rounded-lg border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-xs focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 text-indigo-600 ${verifying ? 'animate-spin' : ''}`} />
            Verify Integrity
          </button>
        </div>

        {/* Event Logs List */}
        <div className="max-h-96 overflow-y-auto p-5 divide-y divide-slate-100">
          {loading ? (
            <div className="py-12 text-center text-xs text-slate-400">Loading audit log entries...</div>
          ) : logs.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-400 italic">
              No audit events recorded for this tender.
            </div>
          ) : (
            logs.map((row) => (
              <div key={row.id} className="py-3.5 first:pt-0 last:pb-0 space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-xs font-bold text-slate-900 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                      #{row.id}
                    </span>
                    <span className="text-xs font-bold text-indigo-700 uppercase tracking-wider">
                      {row.action.replace('_', ' ')}
                    </span>
                    <span className="text-slate-400">&bull;</span>
                    <span className="text-xs text-slate-600">by <b>{row.actor}</b></span>
                  </div>
                  <span className="text-[11px] text-slate-400">
                    {new Date(row.ts).toLocaleString()}
                  </span>
                </div>

                {/* Payload snippet */}
                <div className="p-2 rounded bg-slate-50 border border-slate-200 text-xs font-mono text-slate-700 overflow-x-auto">
                  {row.payload_json}
                </div>

                {/* Hashes */}
                <div className="flex items-center space-x-4 text-[10px] font-mono text-slate-400">
                  <div className="truncate max-w-xs">
                    Prev: {row.prev_hash.slice(0, 16)}...
                  </div>
                  <div className="truncate max-w-xs text-indigo-600">
                    Row: {row.row_hash.slice(0, 16)}...
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-slate-900 text-white rounded-lg text-xs font-semibold hover:bg-slate-800 transition-colors shadow-xs"
          >
            Close Audit Trail
          </button>
        </div>
      </div>
    </div>
  );
};
