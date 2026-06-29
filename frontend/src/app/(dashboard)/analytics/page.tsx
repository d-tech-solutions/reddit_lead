'use client';

import { useEffect, useState } from 'react';
import { useLeadStore } from '@/stores/useLeadStore';
import { apiRequest } from '@/lib/api';
import { BarChart, PieChart, TrendingUp, Award, DollarSign, Calendar, ChevronRight } from 'lucide-react';

export default function AnalyticsPage() {
  const { leads, setLeads } = useLeadStore();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchLeads = async () => {
      setLoading(true);
      try {
        const data = await apiRequest('/leads?only_relevant=true');
        setLeads(data);
      } catch (err) {
        console.error('Failed to fetch analytics leads:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchLeads();
  }, [setLeads]);

  // Calculations for charts
  const totalLeads = leads.length;
  const highIntentLeads = leads.filter(l => (l.analysis?.score || 0) >= 80).length;
  const crmStatusCounts = leads.reduce((acc: any, l) => {
    const status = l.analysis?.status || 'New';
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, { 'New': 0, 'Replied': 0, 'Interested': 0, 'Won': 0, 'Lost': 0 });

  const conversionRate = totalLeads > 0 
    ? Math.round((crmStatusCounts['Won'] / totalLeads) * 100) 
    : 0;

  // Subreddit distribution count
  const subredditCounts = leads.reduce((acc: any, l) => {
    acc[l.subreddit] = (acc[l.subreddit] || 0) + 1;
    return acc;
  }, {});

  const subredditsSorted = Object.entries(subredditCounts)
    .sort((a: any, b: any) => b[1] - a[1])
    .slice(0, 5);

  const maxSubredditCount = subredditsSorted.length > 0 ? Math.max(...subredditsSorted.map(s => s[1] as number)) : 1;

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Title Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white tracking-tight">Personal Analytics</h1>
        <p className="text-slate-400 text-sm mt-1">
          Review matching metrics, conversion parameters, and your target platform engagement distributions
        </p>
      </div>

      {loading ? (
        <div className="flex-1 flex justify-center items-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary"></div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Key Metrics grids */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="glass-card rounded-2xl p-5 text-center">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Total Scored Leads</span>
              <h3 className="text-3xl font-extrabold text-white mt-1.5">{totalLeads}</h3>
            </div>
            
            <div className="glass-card rounded-2xl p-5 text-center">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">High Intent Leads</span>
              <h3 className="text-3xl font-extrabold text-accent-secondary mt-1.5">{highIntentLeads}</h3>
            </div>

            <div className="glass-card rounded-2xl p-5 text-center">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Conversion Rate</span>
              <h3 className="text-3xl font-extrabold text-accent-success mt-1.5">{conversionRate}%</h3>
            </div>

            <div className="glass-card rounded-2xl p-5 text-center">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Deals Closed</span>
              <h3 className="text-3xl font-extrabold text-white mt-1.5">{crmStatusCounts['Won']}</h3>
            </div>
          </div>

          {/* SVG Charts section */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            
            {/* Visual Chart 1: Subreddit Lead Distribution (SVG Bar Chart) */}
            <div className="glass-panel rounded-2xl p-6 flex flex-col">
              <h3 className="text-sm font-bold text-white mb-6 uppercase tracking-wider">Top Source Subreddits</h3>
              
              {subredditsSorted.length === 0 ? (
                <div className="flex-1 flex items-center justify-center text-xs text-slate-600">No data available</div>
              ) : (
                <div className="space-y-4 flex-1 flex flex-col justify-center">
                  {subredditsSorted.map(([sub, count]: any) => {
                    const widthPct = Math.max(10, Math.min(100, (count / maxSubredditCount) * 100));
                    return (
                      <div key={sub} className="space-y-1.5">
                        <div className="flex justify-between items-center text-xs">
                          <span className="font-mono text-slate-300">r/{sub}</span>
                          <span className="font-bold text-white">{count} leads</span>
                        </div>
                        <div className="w-full h-3 bg-white/5 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-gradient-to-r from-accent-primary to-accent-secondary rounded-full transition-all duration-1000" 
                            style={{ width: `${widthPct}%` }}
                          ></div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Visual Chart 2: CRM Conversion Funnel (Visual Stacked Rings) */}
            <div className="glass-panel rounded-2xl p-6 flex flex-col items-center">
              <h3 className="text-sm font-bold text-white mb-6 uppercase tracking-wider self-start">CRM Funnel Performance</h3>
              
              <div className="flex-1 flex flex-col sm:flex-row items-center gap-8 justify-center py-4 w-full">
                
                {/* SVG Progress Circle */}
                <div className="relative w-36 h-36 flex items-center justify-center shrink-0">
                  <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                    {/* Background circle */}
                    <circle 
                      cx="50" cy="50" r="40" 
                      className="stroke-white/5 fill-transparent" 
                      strokeWidth="8"
                    />
                    {/* Foreground conversion path circle */}
                    <circle 
                      cx="50" cy="50" r="40" 
                      className="stroke-accent-success fill-transparent transition-all duration-1000 ease-out" 
                      strokeWidth="8"
                      strokeDasharray={`${2 * Math.PI * 40}`}
                      strokeDashoffset={`${2 * Math.PI * 40 * (1 - conversionRate / 100)}`}
                      strokeLinecap="round"
                    />
                  </svg>
                  <div className="absolute text-center">
                    <span className="text-2xl font-extrabold text-white">{conversionRate}%</span>
                    <span className="text-[10px] text-slate-500 uppercase tracking-wider block font-semibold mt-0.5">Win Rate</span>
                  </div>
                </div>

                {/* Funnel distribution indices */}
                <div className="flex-1 space-y-3 w-full sm:max-w-xs">
                  {Object.entries(crmStatusCounts).map(([status, count]: any) => (
                    <div key={status} className="flex justify-between items-center text-xs">
                      <span className="text-slate-400 font-medium flex items-center gap-2">
                        <span className={`w-2.5 h-2.5 rounded-full ${
                          status === 'New' ? 'bg-accent-secondary' :
                          status === 'Replied' ? 'bg-accent-primary' :
                          status === 'Interested' ? 'bg-accent-warning' :
                          status === 'Won' ? 'bg-accent-success' : 'bg-accent-danger'
                        }`}></span>
                        {status}
                      </span>
                      <span className="font-mono font-bold text-white">{count}</span>
                    </div>
                  ))}
                </div>

              </div>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
