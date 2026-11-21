import React, { useEffect, useState } from 'react';
import { History, ChevronDown, CheckCircle2, Clock, ShieldAlert, RefreshCw } from 'lucide-react';
import { TenderSummary } from '../types';
import { fetchTenders } from '../api';

interface PastTendersSelectorProps {
  currentTenderId: string | null;
  onSelectTender: (tenderId: string) => void;
  onNewTender: () => void;
}

export const PastTendersSelector: React.FC<PastTendersSelectorProps> = ({
  currentTenderId,
  onSelectTender,
  onNewTender,
}) => {
  const [tenders, setTenders] = useState<TenderSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  const loadList = async () => {
    try {
      setLoading(true);
      const list = await fetchTenders();
      setTenders(list);
    } catch {
      // Fallback if empty or offline
      setTenders([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadList();
  }, [currentTenderId]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'evaluated':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-600" /> Evaluated
          </span>
        );
      case 'overridden':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-100 text-purple-800 border border-purple-200">
            <ShieldAlert className="w-3 h-3 mr-1 text-purple-600" /> Overridden
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            <Clock className="w-3 h-3 mr-1 text-slate-500" /> In Progress
          </span>
        );
    }
  };

  return (
    <div className="relative inline-block text-left">
      <div className="flex items-center space-x-2">
        <button
          type="button"
          onClick={() => {
            setIsOpen(!isOpen);
            if (!isOpen) loadList();
          }}
          className="inline-flex items-center justify-between px-3.5 py-1.5 rounded-lg border border-slate-300 bg-white shadow-xs text-xs font-semibold text-slate-700 hover:bg-slate-50 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
          aria-haspopup="true"
          aria-expanded={isOpen}
        >
          <History className="w-4 h-4 mr-2 text-indigo-600" />
          <span>
            {currentTenderId
              ? `Tender: ${currentTenderId.slice(0, 8)}...`
              : 'Past Evaluated Tenders'}
          </span>
          <ChevronDown className="w-3.5 h-3.5 ml-2 text-slate-400" />
        </button>

        {currentTenderId && (
          <button
            type="button"
            onClick={onNewTender}
            className="px-3 py-1.5 rounded-lg border border-indigo-200 bg-indigo-50 text-indigo-700 text-xs font-semibold hover:bg-indigo-100 transition-colors"
          >
            + New Evaluation
          </button>
        )}
      </div>

      {isOpen && (
        <div
          className="origin-top-right absolute right-0 mt-2 w-96 rounded-xl shadow-xl bg-white border border-slate-200 divide-y divide-slate-100 z-50 focus:outline-hidden animate-in fade-in zoom-in-95 duration-100"
          role="menu"
        >
          <div className="p-3 bg-slate-50 flex items-center justify-between">
            <div className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center">
              <History className="w-3.5 h-3.5 mr-1.5 text-indigo-600" />
              Tender Evaluation History
            </div>
            <button
              onClick={loadList}
              className="text-slate-400 hover:text-slate-600 p-1 rounded"
              title="Refresh list"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          <div className="max-h-72 overflow-y-auto divide-y divide-slate-100 p-1">
            {tenders.length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-400 italic">
                {loading ? 'Loading tenders...' : 'No past tenders recorded yet.'}
              </div>
            ) : (
              tenders.map((t) => (
                <div
                  key={t.tender_id}
                  onClick={() => {
                    onSelectTender(t.tender_id);
                    setIsOpen(false);
                  }}
                  className={`p-3 rounded-lg cursor-pointer transition-colors hover:bg-indigo-50/60 ${
                    currentTenderId === t.tender_id ? 'bg-indigo-50 border border-indigo-200' : ''
                  }`}
                  role="menuitem"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-bold text-slate-900">
                      #{t.tender_id.slice(0, 8)}
                    </span>
                    {getStatusBadge(t.status)}
                  </div>
                  <div className="text-xs text-slate-600 mt-1 truncate">
                    {t.title || 'Standard GeM Tender Pack'}
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 mt-1.5">
                    <span>{t.bidder_count} Bidder{t.bidder_count === 1 ? '' : 's'}</span>
                    <span>{new Date(t.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
