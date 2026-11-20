import React from 'react';
import { CheckCircle, XCircle, AlertCircle, ShieldAlert, ArrowRight } from 'lucide-react';
import { Criterion, CriterionResult, OfficerOverride, Verdict } from '../types';

interface VerdictMatrixProps {
  criteria: Criterion[];
  results: CriterionResult[];
  overrides: OfficerOverride[];
  bidders: string[];
  onSelectCell: (criterion: Criterion, bidderName: string, result?: CriterionResult, override?: OfficerOverride) => void;
}

export const VerdictMatrix: React.FC<VerdictMatrixProps> = ({
  criteria,
  results,
  overrides,
  bidders,
  onSelectCell,
}) => {
  // Build fast lookups
  const resultMap = new Map<string, CriterionResult>();
  results.forEach(r => resultMap.set(`${r.criterion_id}:${r.bidder_name}`, r));

  const overrideMap = new Map<string, OfficerOverride>();
  overrides.forEach(o => overrideMap.set(`${o.criterion_id}:${o.bidder_name}`, o));

  const renderBadge = (verdict: Verdict) => {
    switch (verdict) {
      case 'PASS':
        return (
          <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle className="w-3.5 h-3.5 mr-1 text-emerald-600" aria-hidden="true" />
            <span>PASS</span>
          </span>
        );
      case 'FAIL':
        return (
          <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300">
            <XCircle className="w-3.5 h-3.5 mr-1 text-rose-600" aria-hidden="true" />
            <span>FAIL</span>
          </span>
        );
      case 'REVIEW':
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300">
            <AlertCircle className="w-3.5 h-3.5 mr-1 text-amber-600" aria-hidden="true" />
            <span>REVIEW</span>
          </span>
        );
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
      <div className="p-4 bg-slate-50 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-bold text-slate-900">Bidder Eligibility &amp; Compliance Matrix</h3>
          <p className="text-xs text-slate-500">
            Click any cell to inspect cited quotes, page numbers, and statutory rule evaluation logic.
          </p>
        </div>
        <div className="flex items-center space-x-3 text-xs">
          <span className="flex items-center text-emerald-700 font-medium">
            <CheckCircle className="w-3.5 h-3.5 mr-1 text-emerald-600" /> PASS
          </span>
          <span className="flex items-center text-rose-700 font-medium">
            <XCircle className="w-3.5 h-3.5 mr-1 text-rose-600" /> FAIL
          </span>
          <span className="flex items-center text-amber-700 font-medium">
            <AlertCircle className="w-3.5 h-3.5 mr-1 text-amber-600" /> REVIEW
          </span>
          <span className="flex items-center text-purple-700 font-medium">
            <ShieldAlert className="w-3.5 h-3.5 mr-1 text-purple-600" /> OVERRIDDEN
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-100 text-slate-700">
            <tr>
              <th scope="col" className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider w-1/3">
                Evaluation Criterion
              </th>
              {bidders.map((bName) => (
                <th key={bName} scope="col" className="px-4 py-3 text-center font-bold text-xs uppercase tracking-wider">
                  {bName}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 bg-white">
            {criteria.map((crit) => (
              <tr key={crit.id} className="hover:bg-slate-50/80 transition-colors">
                <td className="px-4 py-3.5">
                  <div className="font-semibold text-slate-900 leading-snug">{crit.title}</div>
                  <div className="text-xs text-slate-500 mt-0.5 flex items-center space-x-2">
                    <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded text-[11px] text-slate-600 border border-slate-200">
                      {crit.id}
                    </span>
                    <span>&bull;</span>
                    <span>Rule: {crit.rule_type}</span>
                    {crit.threshold !== undefined && crit.threshold !== null && (
                      <>
                        <span>&bull;</span>
                        <span className="font-medium text-slate-700">
                          Threshold: {crit.threshold} {crit.unit || ''}
                        </span>
                      </>
                    )}
                  </div>
                  {crit.supersedes && crit.supersedes.length > 0 && (
                    <div className="mt-1 text-[11px] text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200 inline-block">
                      Supersedes older criteria from corrigendum
                    </div>
                  )}
                </td>

                {bidders.map((bName) => {
                  const key = `${crit.id}:${bName}`;
                  const result = resultMap.get(key);
                  const override = overrideMap.get(key);
                  const effectiveVerdict = override ? override.new_verdict : result ? result.verdict : 'REVIEW';

                  return (
                    <td
                      key={key}
                      tabIndex={0}
                      role="button"
                      aria-label={`View evidence for ${crit.title} - ${bName}: verdict ${effectiveVerdict}`}
                      onClick={() => onSelectCell(crit, bName, result, override)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          onSelectCell(crit, bName, result, override);
                        }
                      }}
                      className="px-4 py-3.5 text-center cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-indigo-50/50 hover:bg-slate-100/80 transition-all select-none"
                    >
                      <div className="flex flex-col items-center justify-center space-y-1">
                        {renderBadge(effectiveVerdict)}

                        {override && (
                          <div className="inline-flex items-center text-[10px] font-bold text-purple-700 bg-purple-50 px-1.5 py-0.5 rounded border border-purple-300">
                            <ShieldAlert className="w-3 h-3 mr-1" />
                            Overridden ({override.old_verdict})
                          </div>
                        )}

                        <span className="text-[10px] text-slate-400 group-hover:text-indigo-600 flex items-center">
                          inspect evidence <ArrowRight className="w-2.5 h-2.5 ml-0.5" />
                        </span>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
