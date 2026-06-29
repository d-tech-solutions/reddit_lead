'use client';

import { useEffect, useState } from 'react';
import { apiRequest } from '@/lib/api';
import { Users, Database, Sparkles, TrendingUp, DollarSign, RefreshCw } from 'lucide-react';

interface AdminStats {
  total_users: number;
  total_posts_collected: number;
  total_lead_matches: number;
  average_match_score: number;
  estimated_llm_cost: number;
  subreddit_distribution: Record<string, number>;
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchStats = async () => {
    setLoading(true);
    try {
      const data = await apiRequest('/admin/stats');
      setStats(data);
    } catch (err) {
      console.error('Failed to retrieve admin stats:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  if (loading || !stats) {
    return (
      <div className="flex-1 flex justify-center items-center">
        <RefreshCw className="w-8 h-8 text-accent-warning animate-spin" />
      </div>
    );
  }

  const maxSubredditCount = Object.keys(stats.subreddit_distribution).length > 0
    ? Math.max(...Object.values(stats.subreddit_distribution))
    : 1;

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Title Header */}
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Superadmin Dashboard</h1>
          <p className="text-slate-400 text-sm mt-1">
            Global system usage statistics, active subreddit tracking, and API resource telemetry
          </p>
        </div>
        <button
          onClick={fetchStats}
          className="p-2.5 bg-white/5 hover:bg-white/10 border border-white/5 text-slate-300 hover:text-white rounded-xl transition-all cursor-pointer"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Stats Grids */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
        <div className="glass-card rounded-2xl p-5 flex items-center justify-between border-t-2 border-t-accent-primary">
          <div>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Total Platform Users</span>
            <h3 className="text-2xl font-bold text-white mt-1">{stats.total_users}</h3>
          </div>
          <div className="p-3 bg-accent-primary/10 rounded-xl text-accent-primary">
            <Users className="w-5 h-5" />
          </div>
        </div>

        <div className="glass-card rounded-2xl p-5 flex items-center justify-between border-t-2 border-t-accent-secondary">
          <div>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Raw Posts Gathered</span>
            <h3 className="text-2xl font-bold text-white mt-1">{stats.total_posts_collected}</h3>
          </div>
          <div className="p-3 bg-accent-secondary/10 rounded-xl text-accent-secondary">
            <Database className="w-5 h-5" />
          </div>
        </div>

        <div className="glass-card rounded-2xl p-5 flex items-center justify-between border-t-2 border-t-accent-success">
          <div>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Qualified Lead Matches</span>
            <h3 className="text-2xl font-bold text-white mt-1">{stats.total_lead_matches}</h3>
          </div>
          <div className="p-3 bg-accent-success/10 rounded-xl text-accent-success">
            <Sparkles className="w-5 h-5" />
          </div>
        </div>

        <div className="glass-card rounded-2xl p-5 flex items-center justify-between border-t-2 border-t-accent-warning">
          <div>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Est. OpenAI Cost</span>
            <h3 className="text-2xl font-bold text-accent-warning mt-1">${stats.estimated_llm_cost}</h3>
          </div>
          <div className="p-3 bg-accent-warning/10 rounded-xl text-accent-warning">
            <DollarSign className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Subreddit Distribution lists */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel rounded-2xl p-6 flex flex-col">
          <h3 className="text-sm font-bold text-white mb-6 uppercase tracking-wider">Subreddit Post Telemetry</h3>
          
          <div className="space-y-4 flex-grow flex flex-col justify-center">
            {Object.entries(stats.subreddit_distribution).map(([subreddit, count]) => {
              const pct = (count / maxSubredditCount) * 100;
              return (
                <div key={subreddit} className="space-y-1.5">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-mono text-slate-300">r/{subreddit}</span>
                    <span className="font-bold text-white">{count} posts</span>
                  </div>
                  <div className="w-full h-3 bg-white/5 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-accent-primary to-accent-secondary rounded-full transition-all duration-1000" 
                      style={{ width: `${pct}%` }}
                    ></div>
                  </div>
                </div>
              );
            })}
            
            {Object.keys(stats.subreddit_distribution).length === 0 && (
              <div className="text-center text-slate-500 py-10 text-xs">No posts collected yet</div>
            )}
          </div>
        </div>
        
        {/* Additional Admin Overview Guide */}
        <div className="glass-panel rounded-2xl p-6 flex flex-col justify-center">
          <h3 className="text-sm font-bold text-white mb-4 uppercase tracking-wider">Platform Administration Guide</h3>
          <p className="text-slate-400 text-xs leading-relaxed mb-4">
            Use this panel to coordinate the collection cycle of LeadRadar AI. The system runs an RSS Atom feed polling script across monitored subreddits, saves posts, and qualifiers them.
          </p>
          <div className="space-y-2 text-xs">
            <div className="p-3 bg-white/5 rounded-xl border border-white/5 flex items-center justify-between">
              <span className="text-slate-300">Monitored Subreddits count</span>
              <span className="font-mono text-white font-semibold">{Object.keys(stats.subreddit_distribution).length}</span>
            </div>
            <div className="p-3 bg-white/5 rounded-xl border border-white/5 flex items-center justify-between">
              <span className="text-slate-300">System Match Rate</span>
              <span className="font-mono text-accent-success font-semibold">
                {stats.total_posts_collected > 0
                  ? `${Math.round((stats.total_lead_matches / stats.total_posts_collected) * 100)}%`
                  : '0%'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
