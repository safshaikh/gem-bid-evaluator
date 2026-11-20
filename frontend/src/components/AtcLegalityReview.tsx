import React from 'react';
import { AlertTriangle, CheckCircle, ShieldX } from 'lucide-react';
import { AtcFlag, VoidListItem } from '../types';

interface AtcLegalityReviewProps {
  flags: AtcFlag[];
  voidList: VoidListItem[];
}

export const AtcLegalityReview: React.FC<AtcLegalityReviewProps> = ({ flags, voidList }) => {
  return (
    <div className="space-y-6">
      {/* ATC Review Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="p-4 bg-slate-50 border-b border-slate-200">
          <h3 className="text-base font-bold text-slate-900">Buyer Added Additional Terms &amp; Conditions (ATC) Legality Review</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Automated scrutiny against GeM&rsquo;s 14 standard null-and-void Disclaimer categories. Flagged terms cannot be enforced against bidders.
          </p>
        </div>

        {flags.length === 0 ? (
          <div className="p-6 text-center text-slate-400 text-sm">No custom ATC clauses detected in the tender notice.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-xs">
              <thead className="bg-slate-100 text-slate-700">
                <tr>
                  <th scope="col" className="px-4 py-2.5 text-left font-bold uppercase">Buyer ATC Condition</th>
                  <th scope="col" className="px-4 py-2.5 text-center font-bold uppercase w-28">Void Category #</th>
                  <th scope="col" className="px-4 py-2.5 text-center font-bold uppercase w-28">Legal Status</th>
                  <th scope="col" className="px-4 py-2.5 text-left font-bold uppercase w-2/5">Findings &amp; Scrutiny</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white">
                {flags.map((flag, idx) => (
                  <tr key={idx} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-slate-800 leading-snug">
                      &ldquo;{flag.clause_text}&rdquo;
                    </td>
                    <td className="px-4 py-3 text-center font-mono font-bold text-slate-700">
                      {flag.matched_void_index ? `#${flag.matched_void_index}` : '—'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {flag.verdict === 'FLAG' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-300">
                          <ShieldX className="w-3 h-3 mr-1 text-rose-600" /> FLAG
                        </span>
                      ) : flag.verdict === 'REVIEW' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                          <AlertTriangle className="w-3 h-3 mr-1 text-amber-600" /> REVIEW
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                          <CheckCircle className="w-3 h-3 mr-1 text-emerald-600" /> CLEAR
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-600 leading-relaxed">
                      {flag.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* GeM Disclaimer Categories Reference */}
      {voidList.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-3">
          <h4 className="text-sm font-bold text-slate-900">GeM Disclaimer Standard Null-and-Void Categories (Reference)</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
            {voidList.map((v) => (
              <div key={v.index} className="p-2.5 rounded bg-slate-50 border border-slate-200 flex items-start space-x-2">
                <span className="font-mono font-bold text-indigo-700 w-5 flex-shrink-0">#{v.index}</span>
                <span className="text-slate-700">{v.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
