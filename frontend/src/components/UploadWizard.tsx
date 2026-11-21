import React, { useState, useEffect } from 'react';
import {
  Upload,
  ArrowUp,
  ArrowDown,
  Trash2,
  Plus,
  Sparkles,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Database,
  Info,
  FileCheck2,
} from 'lucide-react';
import {
  uploadTenderDocuments,
  addBidderPack,
  evaluateTender,
  loadDemoTender,
  fetchSources,
  ingestFromSource,
} from '../api';
import { EvaluationResult, IngestedDocument, IngestionSource } from '../types';

interface UploadWizardProps {
  onEvaluationComplete: (res: EvaluationResult) => void;
}

interface BidderInput {
  id: string;
  name: string;
  files: File[];
}

export const UploadWizard: React.FC<UploadWizardProps> = ({ onEvaluationComplete }) => {
  const [sources, setSources] = useState<IngestionSource[]>([
    { name: 'demo', display_name: 'Demo GeM Source', kind: 'demo', description: 'Curated test tenders in data/mock_gem/' },
    { name: 'local', display_name: 'Local Folder Source', kind: 'local', description: 'Folder packs in data/gem_inbox/' },
  ]);
  const [selectedSource, setSelectedSource] = useState('demo');
  const [bidIdInput, setBidIdInput] = useState('GEM/2026/B/DEMO0001');
  const [ingestedTender, setIngestedTender] = useState<{
    tender_id: string;
    bid_id: string;
    documents: IngestedDocument[];
    total_pages: number;
    is_duplicate?: boolean;
  } | null>(null);
  const [ingestSuccessMsg, setIngestSuccessMsg] = useState<string | null>(null);

  const [tenderFiles, setTenderFiles] = useState<File[]>([]);
  const [bidders, setBidders] = useState<BidderInput[]>([
    { id: '1', name: 'Alpha Solutions Pvt Ltd', files: [] }
  ]);
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSources()
      .then((srcs) => {
        if (srcs && srcs.length > 0) setSources(srcs);
      })
      .catch(() => {});
  }, []);

  // Fetch packet from registered source
  const handleFetchFromSource = async () => {
    if (!bidIdInput.trim()) {
      setError('Please enter a valid Bid ID (e.g. GEM/2026/B/DEMO0001).');
      return;
    }
    try {
      setError(null);
      setLoading(true);
      setLoadingStage(`Fetching Bid ${bidIdInput.trim()} from ${selectedSource}...`);
      const res = await ingestFromSource(selectedSource, bidIdInput.trim());
      setIngestedTender(res);
      setIngestSuccessMsg(
        res.is_duplicate
          ? `Existing tender loaded! Retrieved stored Bid ${res.bid_id} with ${res.documents.length} verified documents.`
          : `Successfully ingested Bid ${res.bid_id} with ${res.documents.length} documents in sorted chronological order.`
      );
    } catch (err: any) {
      setError(err.message || 'Failed to ingest from source.');
      setIngestedTender(null);
    } finally {
      setLoading(false);
      setLoadingStage('');
    }
  };

  // Add tender PDFs
  const handleTenderFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setTenderFiles(prev => [...prev, ...Array.from(e.target.files || [])]);
    }
  };

  const moveTenderFile = (index: number, direction: 'up' | 'down') => {
    const target = direction === 'up' ? index - 1 : index + 1;
    if (target < 0 || target >= tenderFiles.length) return;
    const updated = [...tenderFiles];
    const temp = updated[index];
    updated[index] = updated[target];
    updated[target] = temp;
    setTenderFiles(updated);
  };

  const removeTenderFile = (index: number) => {
    setTenderFiles(prev => prev.filter((_, i) => i !== index));
  };

  // Bidder management
  const updateBidderName = (id: string, name: string) => {
    setBidders(prev => prev.map(b => (b.id === id ? { ...b, name } : b)));
  };

  const handleBidderFilesChange = (id: string, e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const added = Array.from(e.target.files);
      setBidders(prev => prev.map(b => (b.id === id ? { ...b, files: [...b.files, ...added] } : b)));
    }
  };

  const removeBidder = (id: string) => {
    setBidders(prev => prev.filter(b => b.id !== id));
  };

  const addBidderField = () => {
    setBidders(prev => [
      ...prev,
      { id: Date.now().toString(), name: `Bidder ${prev.length + 1}`, files: [] }
    ]);
  };

  // Run full evaluation pipeline
  const handleEvaluate = async () => {
    try {
      setError(null);
      setLoading(true);

      let targetTenderId = ingestedTender?.tender_id;

      if (!targetTenderId) {
        if (tenderFiles.length === 0) {
          setError('Please upload at least one tender document (main bid PDF) or fetch from GeM source.');
          setLoading(false);
          return;
        }
        setLoadingStage('Step 1/3: Ingesting tender documents and extracting PDF text layers...');
        const tenderResp = await uploadTenderDocuments(tenderFiles);
        targetTenderId = tenderResp.tender_id;
      }

      const validBidders = bidders.filter(b => b.name.trim() && b.files.length > 0);
      if (validBidders.length > 0) {
        setLoadingStage('Step 2/3: Uploading bidder evidence packs...');
        for (const b of validBidders) {
          await addBidderPack(targetTenderId, b.name, b.files);
        }
      }

      setLoadingStage('Step 3/3: Running deterministic rules engine & quote verification...');
      const result = await evaluateTender(targetTenderId);
      onEvaluationComplete(result);
    } catch (err: any) {
      setError(err.message || 'An error occurred during evaluation.');
    } finally {
      setLoading(false);
      setLoadingStage('');
    }
  };

  // Quick 1-click demo load
  const handleLoadDemo = async () => {
    try {
      setError(null);
      setLoading(true);
      setLoadingStage('Loading IIT Kanpur hero corrigendum & synthetic bidder packs...');
      const res = await loadDemoTender();
      onEvaluationComplete(res.evaluation);
    } catch (err: any) {
      setError(err.message || 'Failed to load demo fixtures.');
    } finally {
      setLoading(false);
      setLoadingStage('');
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-8">
      {/* Top Banner & 1-Click Demo */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-slate-200 gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Tender Evaluation Workbench</h2>
          <p className="text-sm text-slate-500 mt-1">
            Fetch tender packs directly from mock/local GeM sources, or upload PDF files manually in date order.
          </p>
        </div>
        <button
          type="button"
          onClick={handleLoadDemo}
          disabled={loading}
          className="inline-flex items-center justify-center px-4 py-2.5 rounded-lg text-sm font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 hover:border-indigo-300 transition-colors shadow-sm disabled:opacity-50"
        >
          <Sparkles className="w-4 h-4 mr-2 text-indigo-600" />
          Load Demo Case (IIT Kanpur)
        </button>
      </div>

      {/* GeM Pluggable Ingestion Bar */}
      <div className="p-4 rounded-xl border border-indigo-100 bg-indigo-50/40 space-y-3">
        <div className="flex items-center space-x-2 text-sm font-bold text-slate-900">
          <Database className="w-4 h-4 text-indigo-600" />
          <span>Ingest from GeM Source</span>
        </div>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div className="w-full sm:w-56">
            <select
              value={selectedSource}
              onChange={(e) => setSelectedSource(e.target.value)}
              disabled={loading}
              className="w-full px-3 py-2 text-xs font-medium rounded-lg border border-slate-300 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {sources.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.display_name} ({s.kind})
                </option>
              ))}
            </select>
          </div>

          <div className="flex-1">
            <input
              type="text"
              value={bidIdInput}
              onChange={(e) => setBidIdInput(e.target.value)}
              placeholder="e.g. GEM/2026/B/DEMO0001"
              disabled={loading}
              className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-slate-300 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <button
            type="button"
            onClick={handleFetchFromSource}
            disabled={loading}
            className="px-4 py-2 rounded-lg text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center justify-center space-x-1.5 shadow-2xs whitespace-nowrap"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileCheck2 className="w-3.5 h-3.5" />}
            <span>Fetch Tender Pack</span>
          </button>
        </div>

        <div className="flex items-center text-xs text-slate-500 italic">
          <Info className="w-3.5 h-3.5 mr-1 text-slate-400 shrink-0" />
          <span>Demo data, not connected to the live GeM portal. Pluggable ingestion reads local and mock manifests with cryptographic hash verification.</span>
        </div>

        {ingestSuccessMsg && (
          <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 space-y-1">
            <p className="font-semibold flex items-center">
              <CheckCircle2 className="w-3.5 h-3.5 mr-1 text-emerald-600" />
              {ingestSuccessMsg}
            </p>
            {ingestedTender && (
              <div className="mt-2 space-y-1">
                <p className="font-medium text-emerald-900">Documents in chronological order:</p>
                <ul className="list-disc list-inside space-y-0.5 text-slate-700 font-mono text-[11px]">
                  {ingestedTender.documents.map((d, i) => (
                    <li key={i}>
                      <span className="font-semibold text-slate-900">{d.name}</span>
                      <span className="text-slate-500 ml-1">
                        [{d.kind === 'main' ? 'Main Notice' : 'Corrigendum'}]
                        {d.published_at ? ` (${d.published_at.slice(0, 10)})` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-red-800 text-sm flex items-start space-x-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Evaluation Error</p>
            <p>{error}</p>
          </div>
        </div>
      )}

      {/* Step 1: Manual Tender Documents (Optional if fetched from source) */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-900 flex items-center">
              <span className="h-6 w-6 rounded-full bg-slate-900 text-white text-xs flex items-center justify-center mr-2">1</span>
              Tender Notice &amp; Corrigenda Documents (Manual Upload)
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {ingestedTender
                ? 'Tender packet already loaded above. You can optionally add supplementary files here or proceed directly to evaluation.'
                : 'Order matters! Latest corrigendum supersedes earlier criteria via the chronological resolver.'}
            </p>
          </div>
          <label className="cursor-pointer inline-flex items-center px-3 py-1.5 rounded-md text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-300 transition-colors">
            <Upload className="w-3.5 h-3.5 mr-1.5" />
            Add Tender PDF
            <input type="file" multiple accept=".pdf" className="hidden" onChange={handleTenderFilesChange} />
          </label>
        </div>

        {tenderFiles.length === 0 ? (
          <div className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center text-slate-400 text-sm">
            {ingestedTender
              ? `Using ${ingestedTender.documents.length} verified documents from fetched Bid ${ingestedTender.bid_id}.`
              : 'No tender PDFs uploaded. Click "Fetch Tender Pack" above or "Add Tender PDF" for manual upload.'}
          </div>
        ) : (
          <ul className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden bg-slate-50/50">
            {tenderFiles.map((file, idx) => (
              <li key={idx} className="p-3 flex items-center justify-between bg-white text-sm hover:bg-slate-50">
                <div className="flex items-center space-x-3 min-w-0">
                  <span className="font-mono text-xs text-slate-400 w-6 text-center font-bold">#{idx + 1}</span>
                  <span className="font-medium text-slate-800 truncate">{file.name}</span>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    title="Move up"
                    onClick={() => moveTenderFile(idx, 'up')}
                    disabled={idx === 0}
                    className="p-1 rounded text-slate-400 hover:text-slate-600 disabled:opacity-30"
                  >
                    <ArrowUp className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    title="Move down"
                    onClick={() => moveTenderFile(idx, 'down')}
                    disabled={idx === tenderFiles.length - 1}
                    className="p-1 rounded text-slate-400 hover:text-slate-600 disabled:opacity-30"
                  >
                    <ArrowDown className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    title="Remove file"
                    onClick={() => removeTenderFile(idx)}
                    className="p-1 rounded text-slate-400 hover:text-red-600"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Step 2: Bidder Evidence Packs */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-900 flex items-center">
              <span className="h-6 w-6 rounded-full bg-slate-900 text-white text-xs flex items-center justify-center mr-2">2</span>
              Bidder Submission Packs
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Add bidder evidence documents (e.g. audited balance sheet, OEM authorization, certifications).
            </p>
          </div>
          <button
            type="button"
            onClick={addBidderField}
            className="inline-flex items-center px-3 py-1.5 rounded-md text-xs font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 transition-colors"
          >
            <Plus className="w-3.5 h-3.5 mr-1" />
            Add Bidder
          </button>
        </div>

        <div className="space-y-3">
          {bidders.map((bidder, idx) => (
            <div key={bidder.id} className="p-4 rounded-lg border border-slate-200 bg-slate-50 space-y-3">
              <div className="flex items-center space-x-3">
                <span className="font-mono text-xs font-bold text-slate-500">#{idx + 1}</span>
                <input
                  type="text"
                  value={bidder.name}
                  onChange={(e) => updateBidderName(bidder.id, e.target.value)}
                  placeholder="Bidder Legal Entity Name"
                  className="flex-1 px-3 py-1.5 rounded-md border border-slate-300 text-sm font-semibold text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <label className="cursor-pointer inline-flex items-center px-3 py-1.5 rounded-md text-xs font-medium text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 transition-colors">
                  <Upload className="w-3.5 h-3.5 mr-1.5" />
                  Attach Evidence PDFs ({bidder.files.length})
                  <input
                    type="file"
                    multiple
                    accept=".pdf"
                    className="hidden"
                    onChange={(e) => handleBidderFilesChange(bidder.id, e)}
                  />
                </label>

                {bidders.length > 1 && (
                  <button
                    type="button"
                    title="Remove bidder"
                    onClick={() => removeBidder(bidder.id)}
                    className="p-2 text-slate-400 hover:text-red-600"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Execution Button & Status */}
      <div className="pt-4 border-t border-slate-200 flex flex-col items-center space-y-3">
        {loading && (
          <div className="flex items-center space-x-2 text-sm text-indigo-700 font-medium animate-pulse">
            <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
            <span>{loadingStage}</span>
          </div>
        )}

        <button
          type="button"
          onClick={handleEvaluate}
          disabled={loading}
          className="w-full md:w-auto px-8 py-3 rounded-lg text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 shadow-md transition-all disabled:opacity-50 flex items-center justify-center space-x-2"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Evaluating Bids...</span>
            </>
          ) : (
            <>
              <CheckCircle2 className="w-4 h-4" />
              <span>Execute BidParakh Evaluation Pipeline</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};

