import React from 'react';
import { ShieldCheck, Cpu } from 'lucide-react';

interface NavbarProps {
  tenderId?: string | null;
  cached?: boolean;
  degraded?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({ tenderId, cached, degraded }) => {
  return (
    <header className="bg-slate-900 border-b border-slate-800 text-white sticky top-0 z-30 shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="h-10 w-10 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-inner font-bold text-xl tracking-wider">
            BP
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-lg font-bold tracking-tight text-white">BidParakh</h1>
            </div>
            <p className="text-xs text-slate-400">
              Officer-Side Bid Evaluation: <span className="text-indigo-400 font-medium">AI reads, code decides</span>
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3 text-xs">
          {tenderId && (
            <div className="hidden md:flex items-center bg-slate-800 text-slate-300 px-3 py-1.5 rounded-md border border-slate-700">
              <span className="text-slate-400 mr-1.5 font-mono">Tender:</span>
              <span className="font-semibold text-slate-200">{tenderId.slice(0, 10)}...</span>
            </div>
          )}

          {cached && (
            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
              <ShieldCheck className="w-3.5 h-3.5 mr-1" />
              Replay Cached (SHA-256)
            </span>
          )}

          {degraded && (
            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-950 text-amber-300 border border-amber-800">
              <Cpu className="w-3.5 h-3.5 mr-1" />
              Degraded Mode
            </span>
          )}
        </div>
      </div>
    </header>
  );
};
