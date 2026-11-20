import React, { useState } from 'react';
import { Upload, ArrowUp, ArrowDown, Trash2, Plus, Sparkles, CheckCircle2, Loader2, AlertCircle } from 'lucide-react';
import { uploadTenderDocuments, addBidderPack, evaluateTender, loadDemoTender } from '../api';
import { EvaluationResult } from '../types';

interface UploadWizardProps {
  onEvaluationComplete: (res: EvaluationResult) => void;
}

interface BidderInput {
  id: string;
  name: string;
  files: File[];
}

export const UploadWizard: React.FC<UploadWizardProps> = ({ onEvaluationComplete }) => {
  const [tenderFiles, setTenderFiles] = useState<File[]>([]);
  const [bidders, setBidders] = useState<BidderInput[]>([
    { id: '1', name: 'Alpha Solutions Pvt Ltd', files: [] }
  ]);
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState('');
  const [error, setError] = useState<string | null>(null);

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
    if (tenderFiles.length === 0) {
      setError('Please upload at least one tender document (main bid PDF).');
      return;
    }
    const validBidders = bidders.filter(b => b.name.trim() && b.files.length > 0);
    if (validBidders.length === 0) {
      setError('Please configure at least one bidder with an evidence PDF file.');
      return;
    }

    try {
      setError(null);
      setLoading(true);
      
      setLoadingStage('Step 1/3: Ingesting tender documents and extracting PDF text layers...');
      const tenderResp = await uploadTenderDocuments(tenderFiles);
      
      setLoadingStage('Step 2/3: Uploading bidder evidence packs...');
      for (const b of validBidders) {
        await addBidderPack(tenderResp.tender_id, b.name, b.files);
      }

      setLoadingStage('Step 3/3: Running deterministic rules engine & quote verification...');
      const result = await evaluateTender(tenderResp.tender_id);
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
            Upload the main tender notice and subsequent corrigenda in date order, followed by bidder submission packs.
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

      {error && (
        <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-red-800 text-sm flex items-start space-x-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Evaluation Error</p>
            <p>{error}</p>
          </div>
        </div>
      )}

      {/* Step 1: Tender Documents */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-900 flex items-center">
              <span className="h-6 w-6 rounded-full bg-slate-900 text-white text-xs flex items-center justify-center mr-2">1</span>
              Tender Notice &amp; Corrigenda Documents
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Order matters! Latest corrigendum supersedes earlier criteria via the chronological resolver.
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
            No tender PDFs uploaded. Click &ldquo;Add Tender PDF&rdquo; or load the demo case above.
          </div>
        ) : (
          <ul className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden bg-slate-50/50">
            {tenderFiles.map((file, idx) => (
              <li key={idx} className="p-3 flex items-center justify-between bg-white text-sm hover:bg-slate-50">
                <div className="flex items-center space-x-3 min-w-0">
                  <span className="font-mono text-xs text-slate-400 w-6 text-center font-bold">#{idx + 1}</span>
                  <span className="font-medium text-slate-800 truncate">{file.name}</span>
                  <span className="text-xs text-slate-400">({(file.size / 1024).toFixed(1)} KB)</span>
                  {idx === 0 && (
                    <span className="text-[10px] bg-blue-50 text-blue-700 px-2 py-0.5 rounded border border-blue-200">
                      Base Tender
                    </span>
                  )}
                  {idx > 0 && (
                    <span className="text-[10px] bg-purple-50 text-purple-700 px-2 py-0.5 rounded border border-purple-200">
                      Corrigendum #{idx}
                    </span>
                  )}
                </div>
                <div className="flex items-center space-x-1">
                  <button
                    type="button"
                    title="Move up"
                    disabled={idx === 0}
                    onClick={() => moveTenderFile(idx, 'up')}
                    className="p-1 text-slate-400 hover:text-slate-700 disabled:opacity-30"
                  >
                    <ArrowUp className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    title="Move down"
                    disabled={idx === tenderFiles.length - 1}
                    onClick={() => moveTenderFile(idx, 'down')}
                    className="p-1 text-slate-400 hover:text-slate-700 disabled:opacity-30"
                  >
                    <ArrowDown className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    title="Remove"
                    onClick={() => removeTenderFile(idx)}
                    className="p-1 text-red-400 hover:text-red-700 ml-2"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Step 2: Bidder Submission Packs */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-900 flex items-center">
              <span className="h-6 w-6 rounded-full bg-slate-900 text-white text-xs flex items-center justify-center mr-2">2</span>
              Bidder Technical Submission Packs
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Attach one or more supporting technical PDFs per bidder (turnover certificates, OEM authorization, order proofs).
            </p>
          </div>
          <button
            type="button"
            onClick={addBidderField}
            className="inline-flex items-center px-3 py-1.5 rounded-md text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-300 transition-colors"
          >
            <Plus className="w-3.5 h-3.5 mr-1.5" />
            Add Another Bidder
          </button>
        </div>

        <div className="space-y-3">
          {bidders.map((bidder, idx) => (
            <div key={bidder.id} className="p-4 border border-slate-200 rounded-lg bg-white flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex-1 space-y-1">
                <label className="block text-xs font-medium text-slate-600">Bidder #{idx + 1} Name</label>
                <input
                  type="text"
                  value={bidder.name}
                  onChange={(e) => updateBidderName(bidder.id, e.target.value)}
                  className="w-full text-sm font-semibold text-slate-800 border border-slate-300 rounded px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="e.g. Acme Technologies Pvt Ltd"
                />
              </div>

              <div className="flex items-center space-x-3">
                <label className="cursor-pointer inline-flex items-center px-3 py-2 rounded text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 transition-colors">
                  <Upload className="w-3.5 h-3.5 mr-1.5" />
                  {bidder.files.length > 0 ? `${bidder.files.length} PDF(s) attached` : 'Attach PDF(s)'}
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
