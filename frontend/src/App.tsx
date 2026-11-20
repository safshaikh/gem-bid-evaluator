import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { UploadWizard } from './components/UploadWizard';
import { VerdictMatrix } from './components/VerdictMatrix';
import { EvidenceDrawer } from './components/EvidenceDrawer';
import { SpeakingOrdersList } from './components/SpeakingOrdersList';
import { AtcLegalityReview } from './components/AtcLegalityReview';
import { checkHealth, getMatrixCsvUrl, getPdfReportUrl, loadDemoTender } from './api';
import { Criterion, CriterionResult, EvaluationResult, OfficerOverride } from './types';
import { Download, FileText, LayoutGrid, Scale, FileSpreadsheet, RefreshCw } from 'lucide-react';

export const App: React.FC = () => {
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [activeTab, setActiveTab] = useState<'matrix' | 'speaking_orders' | 'atc' | 'new_upload'>('matrix');
  const [selectedCell, setSelectedCell] = useState<{
    criterion: Criterion;
    bidderName: string;
    result?: CriterionResult;
    override?: OfficerOverride;
  } | null>(null);

  // Auto-load demo on initial load so user/judge immediately sees working system!
  useEffect(() => {
    checkHealth()
      .then(() => {
        loadDemoTender()
          .then((res) => setEvaluation(res.evaluation))
          .catch(() => {});
      })
      .catch(() => {});
  }, []);

  const handleEvaluationComplete = (result: EvaluationResult) => {
    setEvaluation(result);
    setActiveTab('matrix');
  };

  const handleOverrideSaved = (updated: EvaluationResult) => {
    setEvaluation(updated);
    // Update selected cell override if open
    if (selectedCell) {
      const newOverride = updated.overrides.find(
        (o) => o.criterion_id === selectedCell.criterion.id && o.bidder_name === selectedCell.bidderName
      );
      setSelectedCell((prev) => (prev ? { ...prev, override: newOverride } : null));
    }
  };

  const biddersList = Array.from(new Set(evaluation?.results.map((r) => r.bidder_name) || []));

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <Navbar tenderId={evaluation?.tender_id} cached={evaluation?.cached} degraded={evaluation?.degraded} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Navigation & Action Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between pb-2 border-b border-slate-200 gap-4">
          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={() => setActiveTab('matrix')}
              className={`inline-flex items-center px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'matrix'
                  ? 'bg-slate-900 text-white shadow-sm'
                  : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
              }`}
            >
              <LayoutGrid className="w-4 h-4 mr-1.5" />
              Verdict Matrix
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('speaking_orders')}
              className={`inline-flex items-center px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'speaking_orders'
                  ? 'bg-slate-900 text-white shadow-sm'
                  : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
              }`}
            >
              <Scale className="w-4 h-4 mr-1.5" />
              Speaking Orders
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('atc')}
              className={`inline-flex items-center px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'atc'
                  ? 'bg-slate-900 text-white shadow-sm'
                  : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
              }`}
            >
              <FileText className="w-4 h-4 mr-1.5" />
              ATC Legality Review
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('new_upload')}
              className={`inline-flex items-center px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'new_upload'
                  ? 'bg-slate-900 text-white shadow-sm'
                  : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
              }`}
            >
              <RefreshCw className="w-4 h-4 mr-1.5" />
              Evaluate New Tender
            </button>
          </div>

          {evaluation && (
            <div className="flex items-center space-x-2">
              <a
                href={getMatrixCsvUrl(evaluation.tender_id)}
                download
                className="inline-flex items-center px-3.5 py-2 rounded-lg text-xs font-semibold bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 shadow-2xs"
              >
                <FileSpreadsheet className="w-4 h-4 mr-1.5 text-emerald-600" />
                Download CSV Matrix
              </a>

              <a
                href={getPdfReportUrl(evaluation.tender_id)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center px-3.5 py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm"
              >
                <Download className="w-4 h-4 mr-1.5" />
                Executive PDF Report
              </a>
            </div>
          )}
        </div>

        {/* Tab Content */}
        {activeTab === 'new_upload' && (
          <UploadWizard onEvaluationComplete={handleEvaluationComplete} />
        )}

        {activeTab === 'matrix' && evaluation && (
          <VerdictMatrix
            criteria={evaluation.criteria}
            results={evaluation.results}
            overrides={evaluation.overrides}
            bidders={biddersList}
            onSelectCell={(criterion, bidderName, result, override) => {
              setSelectedCell({ criterion, bidderName, result, override });
            }}
          />
        )}

        {activeTab === 'speaking_orders' && evaluation && (
          <SpeakingOrdersList results={evaluation.results} />
        )}

        {activeTab === 'atc' && evaluation && (
          <AtcLegalityReview flags={evaluation.atc_flags} voidList={evaluation.void_list} />
        )}

        {!evaluation && activeTab !== 'new_upload' && (
          <UploadWizard onEvaluationComplete={handleEvaluationComplete} />
        )}
      </main>

      {/* Slide-over Evidence & Override Drawer */}
      {selectedCell && evaluation && (
        <EvidenceDrawer
          tenderId={evaluation.tender_id}
          criterion={selectedCell.criterion}
          bidderName={selectedCell.bidderName}
          result={selectedCell.result}
          override={selectedCell.override}
          onClose={() => setSelectedCell(null)}
          onOverrideSaved={handleOverrideSaved}
        />
      )}
    </div>
  );
};
export default App;
