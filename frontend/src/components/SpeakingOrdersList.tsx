import React, { useState } from 'react';
import { Copy, Check, AlertOctagon, Scale } from 'lucide-react';
import { CriterionResult } from '../types';

interface SpeakingOrdersListProps {
  results: CriterionResult[];
}

export const SpeakingOrdersList: React.FC<SpeakingOrdersListProps> = ({ results }) => {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const failResults = results.filter((r) => r.verdict === 'FAIL' && r.speaking_order_line);

  const handleCopy = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2500);
  };

  if (failResults.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
        <Scale className="w-10 h-10 text-emerald-500 mx-auto mb-2" />
        <h3 className="text-base font-bold text-slate-800">No Rejection Orders Generated</h3>
        <p className="text-xs text-slate-500 mt-1">
          All evaluated criteria for submitted bidders either passed or remain under officer review.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
      <div className="flex items-center justify-between pb-4 border-b border-slate-200">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center">
            <AlertOctagon className="w-5 h-5 mr-2 text-rose-600" />
            Statutory Draft Speaking Orders for Bid Rejections
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Pre-formatted legal rejection text citing the exact tender clause, source page, and verified deficiency for official GeM portal rejection orders.
          </p>
        </div>
        <span className="text-xs font-bold text-rose-700 bg-rose-50 border border-rose-200 px-2.5 py-1 rounded-full">
          {failResults.length} Rejection(s)
        </span>
      </div>

      <div className="space-y-3">
        {failResults.map((item, idx) => (
          <div key={idx} className="p-4 rounded-lg bg-rose-50/60 border border-rose-200 flex flex-col md:flex-row md:items-start justify-between gap-4">
            <div className="space-y-2 flex-1">
              <div className="flex items-center space-x-2">
                <span className="text-xs font-bold text-slate-900">{item.bidder_name}</span>
                <span className="text-xs text-slate-400">&bull;</span>
                <span className="text-xs font-mono text-slate-600 bg-white px-2 py-0.5 rounded border border-rose-200">
                  {item.criterion_id}
                </span>
              </div>
              <p className="text-xs font-mono text-slate-900 leading-relaxed bg-white p-3 rounded border border-rose-200 shadow-2xs">
                {item.speaking_order_line}
              </p>
            </div>

            <button
              type="button"
              onClick={() => handleCopy(item.speaking_order_line!, idx)}
              className="inline-flex items-center px-3 py-2 rounded-md text-xs font-semibold text-rose-800 bg-white border border-rose-300 hover:bg-rose-100 transition-colors shadow-2xs flex-shrink-0"
            >
              {copiedIndex === idx ? (
                <>
                  <Check className="w-3.5 h-3.5 mr-1.5 text-emerald-600" />
                  <span className="text-emerald-700 font-bold">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 mr-1.5 text-rose-600" />
                  <span>Copy Speaking Order</span>
                </>
              )}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
