'use client';

import { useEffect, useState } from 'react';
import { useLeadStore, Lead } from '@/stores/useLeadStore';
import { apiRequest } from '@/lib/api';
import { Bookmark, Clock, ArrowUpRight, AlertCircle } from 'lucide-react';
import Link from 'next/link';

export default function SavedPage() {
  const { leads, setLeads } = useLeadStore();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchSavedLeads = async () => {
      setLoading(true);
      try {
        const data = await apiRequest('/leads?saved_only=true');
        setLeads(data);
      } catch (err) {
        console.error('Failed to load saved leads:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchSavedLeads();
  }, [setLeads]);

  const savedLeads = leads.filter((l) => l.analysis?.saved);

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Title Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
          Bookmarks <span className="text-xs px-2 py-0.5 bg-accent-warning/20 text-accent-warning rounded-full font-mono font-bold">{savedLeads.length} saved</span>
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Access your saved high-value opportunities for future outreach and notes log
        </p>
      </div>

      {loading ? (
        <div className="flex-1 flex justify-center items-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary"></div>
        </div>
      ) : savedLeads.length === 0 ? (
        <div className="flex-1 glass-panel rounded-2xl p-12 text-center flex flex-col items-center justify-center my-6">
          <Bookmark className="w-12 h-12 text-slate-600 mb-4 opacity-40" />
          <h2 className="text-lg font-bold text-white">No bookmarked leads</h2>
          <p className="text-slate-500 text-xs max-w-xs mt-1">
            Browse your Inbox and click the bookmark icon on any qualified lead to save it here.
          </p>
        </div>
      ) : (
        /* Saved List Grid */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {savedLeads.map((lead) => {
            const score = lead.analysis?.score || 0;
            return (
              <div 
                key={lead.id}
                className="glass-card rounded-2xl p-5 flex flex-col gap-4 border border-white/5 shadow-lg relative overflow-hidden"
              >
                {/* Score and Subreddit Header */}
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400 font-mono">r/{lead.subreddit}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                    score >= 80 ? 'bg-accent-success/15 text-accent-success' : 'bg-accent-warning/15 text-accent-warning'
                  }`}>
                    {score} Points
                  </span>
                </div>

                <div className="flex-1">
                  <h3 className="text-sm font-bold text-white leading-snug line-clamp-2">{lead.title}</h3>
                  <p className="text-xs text-slate-400 mt-2 line-clamp-3 leading-relaxed">
                    {lead.analysis?.summary}
                  </p>
                </div>

                {/* Card footer redirecting to home with active lead state */}
                <div className="pt-4 border-t border-white/5 flex justify-between items-center mt-2">
                  <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
                    <Clock className="w-3.5 h-3.5" />
                    {new Date(lead.created_utc).toLocaleDateString()}
                  </div>
                  
                  <Link
                    href="/"
                    className="text-xs text-accent-primary hover:text-white font-bold flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    View Details
                    <ArrowUpRight className="w-3.5 h-3.5" />
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
