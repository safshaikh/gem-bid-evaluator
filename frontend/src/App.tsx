import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { UploadWizard } from './components/UploadWizard';
import { VerdictMatrix } from './components/VerdictMatrix';
import { EvidenceDrawer } from './components/EvidenceDrawer';
import { SpeakingOrdersList } from './components/SpeakingOrdersList';
import { AtcLegalityReview } from './components/AtcLegalityReview';
import { PastTendersSelector } from './components/PastTendersSelector';
import { AuditTrailModal } from './components/AuditTrailModal';
import { LoginModal } from './components/LoginModal';
import {
  applyUpdates,
  checkHealth,
  checkUpdates,
  evaluateTender,
  fetchConfig,
  fetchTender,
  getMatrixCsvUrl,
  getPdfReportUrl,
  loadDemoTender,
  publishNextCorrigendum,
} from './api';
import {
  CorrigendumUpdate,
  Criterion,
  CriterionResult,
  EvaluationResult,
  OfficerOverride,
  TenderDetails,
} from './types';
import {
  Download,
  FileText,
  LayoutGrid,
  Scale,
  FileSpreadsheet,
  RefreshCw,
  ShieldCheck,
  AlertTriangle,
  GitPullRequest,
  Sparkles,
  Loader2,
} from 'lucide-react';

export const App: React.FC = () => {
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [tenderDetails, setTenderDetails] = useState<TenderDetails | null>(null);
  const [newCorrigenda, setNewCorrigenda] = useState<CorrigendumUpdate[]>([]);
  const [isCheckingUpdates, setIsCheckingUpdates] = useState(false);
  const [isApplyingUpdates, setIsApplyingUpdates] = useState(false);
  const [activeTab, setActiveTab] = useState<'matrix' | 'speaking_orders' | 'atc' | 'new_upload'>('matrix');
  const [selectedCell, setSelectedCell] = useState<{
    criterion: Criterion;
    bidderName: string;
    result?: CriterionResult;
    override?: OfficerOverride;
  } | null>(null);
  const [isAuditModalOpen, setIsAuditModalOpen] = useState(false);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);

  // Check auth and auto-load initial demo case
  useEffect(() => {
    fetchConfig()
      .then((cfg) => {
        if (cfg.auth_enabled && !localStorage.getItem('bidparakh_jwt')) {
          setIsLoginModalOpen(true);
        }
      })
      .catch(() => {});

    checkHealth()
      .then(() => {
        loadDemoTender()
          .then((res) => {
            setEvaluation(res.evaluation);
            loadDetails(res.evaluation.tender_id);
          })
          .catch(() => {});
      })
      .catch(() => {});
  }, []);

  const loadDetails = async (tenderId: string) => {
    try {
      const details = await fetchTender(tenderId);
      setTenderDetails(details);
      if (details.source_name) {
        // Automatically check for updates
        const updateCheck = await checkUpdates(tenderId);
        if (updateCheck.updates_available) {
          setNewCorrigenda(updateCheck.new_corrigenda);
        } else {
          setNewCorrigenda([]);
        }
      }
    } catch (err) {
      console.error('Failed fetching tender details:', err);
    }
  };

  const handleEvaluationComplete = (result: EvaluationResult) => {
    setEvaluation(result);
    loadDetails(result.tender_id);
    setActiveTab('matrix');
  };

  const handleSelectPastTender = async (tenderId: string) => {
    try {
      const data = await fetchTender(tenderId);
      setTenderDetails(data);
      if (data.evaluation) {
        setEvaluation(data.evaluation);
        setActiveTab('matrix');
      }
      if (data.source_name) {
        const updateCheck = await checkUpdates(tenderId);
        if (updateCheck.updates_available) {
          setNewCorrigenda(updateCheck.new_corrigenda);
        } else {
          setNewCorrigenda([]);
        }
      }
    } catch (err) {
      console.error('Failed loading past tender:', err);
    }
  };

  const handleManualCheckUpdates = async () => {
    if (!evaluation?.tender_id) return;
    try {
      setIsCheckingUpdates(true);
      const updateCheck = await checkUpdates(evaluation.tender_id);
      if (updateCheck.updates_available) {
        setNewCorrigenda(updateCheck.new_corrigenda);
      } else {
        setNewCorrigenda([]);
        alert('Tender is up to date with its source. No newer corrigenda detected.');
      }
    } catch (err: any) {
      alert(`Check failed: ${err.message}`);
    } finally {
      setIsCheckingUpdates(false);
    }
  };

  const handleApplyUpdates = async () => {
    if (!evaluation?.tender_id) return;
    try {
      setIsApplyingUpdates(true);
      await applyUpdates(evaluation.tender_id);
      // Re-run evaluation on updated document set
      const reEvaluated = await evaluateTender(evaluation.tender_id);
      setEvaluation(reEvaluated);
      setNewCorrigenda([]);
      await loadDetails(evaluation.tender_id);
    } catch (err: any) {
      alert(`Apply failed: ${err.message}`);
    } finally {
      setIsApplyingUpdates(false);
    }
  };

  const handleSimulateCorrigendum = async () => {
    if (!tenderDetails?.source_bid_id) return;
    try {
      const res = await publishNextCorrigendum(tenderDetails.source_bid_id);
      if (res.published) {
        await handleManualCheckUpdates();
      } else {
        alert(res.reason || 'No more unpublished corrigenda in mock repository.');
      }
    } catch (err: any) {
      alert(`Simulation failed: ${err.message}`);
    }
  };

  const handleOverrideSaved = (updated: EvaluationResult) => {
    setEvaluation(updated);
    if (selectedCell) {
      const newOverride = updated.overrides.find(
        (o) => o.criterion_id === selectedCell.criterion.id && o.bidder_name === selectedCell.bidderName
      );
      setSelectedCell((prev) => (prev ? { ...prev, override: newOverride } : null));
    }
  };

  const biddersList = Array.from(new Set(evaluation?.results.map((r) => r.bidder_name) || []));
  const isStale = tenderDetails?.status === 'stale';

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <Navbar tenderId={evaluation?.tender_id} cached={evaluation?.cached} degraded={evaluation?.degraded} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Workspace Toolbar: Past Tenders & Quick Actions */}
        <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center space-x-3">
            <PastTendersSelector
              currentTenderId={evaluation?.tender_id || null}
              onSelectTender={handleSelectPastTender}
              onNewTender={() => setActiveTab('new_upload')}
            />
          </div>

          <div className="flex items-center space-x-2">
            {tenderDetails?.source_name && (
              <>
                <button
                  type="button"
                  onClick={handleManualCheckUpdates}
                  disabled={isCheckingUpdates}
                  className="inline-flex items-center px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 text-xs font-semibold hover:bg-slate-100 transition-colors shadow-2xs disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 mr-1.5 text-slate-600 ${isCheckingUpdates ? 'animate-spin' : ''}`} />
                  Check for Updates
                </button>

                {tenderDetails.source_name === 'demo' && (
                  <button
                    type="button"
                    onClick={handleSimulateCorrigendum}
                    className="inline-flex items-center px-3 py-1.5 rounded-lg border border-amber-200 bg-amber-50 text-amber-800 text-xs font-semibold hover:bg-amber-100 transition-colors shadow-2xs"
                    title="Simulate publication of Corrigendum 3 on mock GeM portal"
                  >
                    <Sparkles className="w-3.5 h-3.5 mr-1.5 text-amber-600" />
                    Simulate Corrigendum
                  </button>
                )}
              </>
            )}

            {evaluation?.tender_id && (
              <button
                type="button"
                onClick={() => setIsAuditModalOpen(true)}
                className="inline-flex items-center px-3 py-1.5 rounded-lg border border-indigo-200 bg-indigo-50/70 text-indigo-700 text-xs font-semibold hover:bg-indigo-100 transition-colors shadow-2xs"
              >
                <ShieldCheck className="w-3.5 h-3.5 mr-1.5 text-indigo-600" />
                Audit Trail &amp; Hash Chain
              </button>
            )}
          </div>
        </div>

        {/* Updates Available Banner */}
        {newCorrigenda.length > 0 && (
          <div className="p-4 rounded-xl border border-amber-200 bg-amber-50 text-amber-900 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-fade-in">
            <div className="flex items-start sm:items-center space-x-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5 sm:mt-0" />
              <div>
                <p className="text-sm font-bold">New corrigendum available on GeM source</p>
                <p className="text-xs text-amber-800">
                  {newCorrigenda.map((c) => c.name).join(', ')} detected in source manifest. Apply updates and re-evaluate criteria?
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-2 shrink-0">
              <button
                type="button"
                onClick={handleApplyUpdates}
                disabled={isApplyingUpdates}
                className="px-3.5 py-1.5 rounded-lg text-xs font-bold text-white bg-amber-700 hover:bg-amber-800 transition-colors shadow-2xs flex items-center space-x-1 disabled:opacity-50"
              >
                {isApplyingUpdates ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <GitPullRequest className="w-3.5 h-3.5" />
                )}
                <span>Apply &amp; Re-evaluate</span>
              </button>
              <button
                type="button"
                onClick={() => setNewCorrigenda([])}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold text-amber-800 hover:bg-amber-100 transition-colors"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Navigation & Action Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between pb-2 border-b border-slate-200 gap-4">
          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={() => setActiveTab('matrix')}
              className={`inline-flex items-center px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'matrix'
                  ? 'bg-slate-900 text-white shadow-xs'
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
                  ? 'bg-slate-900 text-white shadow-xs'
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
                  ? 'bg-slate-900 text-white shadow-xs'
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
                  ? 'bg-slate-900 text-white shadow-xs'
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
                className="inline-flex items-center px-3.5 py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 shadow-xs"
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
            isStale={isStale}
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

      {/* Tamper-Evident Audit Trail Modal */}
      {evaluation?.tender_id && (
        <AuditTrailModal
          tenderId={evaluation.tender_id}
          isOpen={isAuditModalOpen}
          onClose={() => setIsAuditModalOpen(false)}
        />
      )}

      {/* Optional Auth Login Modal */}
      <LoginModal
        isOpen={isLoginModalOpen}
        onSuccess={() => setIsLoginModalOpen(false)}
      />
    </div>
  );
};

export default App;
