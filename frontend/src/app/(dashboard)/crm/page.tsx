'use client';

import { useEffect, useState } from 'react';
import { useLeadStore, Lead } from '@/stores/useLeadStore';
import { apiRequest } from '@/lib/api';
import { ChevronRight, ArrowRight, Shield, Award, CheckCircle } from 'lucide-react';

export default function CRMPage() {
  const { leads, setLeads, updateLeadStatus } = useLeadStore();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchLeads = async () => {
      setLoading(true);
      try {
        const data = await apiRequest('/leads?only_relevant=true');
        setLeads(data);
      } catch (err) {
        console.error('Failed to load CRM leads:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchLeads();
  }, [setLeads]);

  const stages: ('New' | 'Replied' | 'Interested' | 'Won' | 'Lost')[] = [
    'New',
    'Replied',
    'Interested',
    'Won',
    'Lost'
  ];

  const handleMoveStage = async (leadId: number, nextStage: string) => {
    try {
      await apiRequest(`/leads/${leadId}/status`, {
        method: 'PATCH',
        json: { status: nextStage }
      });
      updateLeadStatus(leadId, nextStage as any);
    } catch (err) {
      console.error('Failed to update stage:', err);
    }
  };

  const getStageColor = (stage: string) => {
    switch (stage) {
      case 'New': return 'border-t-accent-secondary';
      case 'Replied': return 'border-t-accent-primary';
      case 'Interested': return 'border-t-accent-warning';
      case 'Won': return 'border-t-accent-success';
      case 'Lost': return 'border-t-accent-danger';
      default: return 'border-t-slate-500';
    }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Title Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white tracking-tight">CRM Pipeline Board</h1>
        <p className="text-slate-400 text-sm mt-1">
          Track the outreach status of your qualified opportunities from introduction to project win
        </p>
      </div>

      {loading ? (
        <div className="flex-1 flex justify-center items-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary"></div>
        </div>
      ) : (
        /* Columns Kanban view */
        <div className="flex-1 grid grid-cols-1 md:grid-cols-5 gap-4 items-stretch min-h-[500px]">
          {stages.map((stage) => {
            const stageLeads = leads.filter((l) => l.analysis?.status === stage);
            return (
              <div 
                key={stage}
                className="glass-panel rounded-2xl p-4 flex flex-col gap-4 border-t-4 min-h-[400px]"
                style={{ borderTopColor: `var(--color-accent-${stage.toLowerCase() === 'new' ? 'secondary' : stage.toLowerCase() === 'replied' ? 'primary' : stage.toLowerCase() === 'interested' ? 'warning' : stage.toLowerCase() === 'won' ? 'success' : 'danger'})` }}
              >
                {/* Column header */}
                <div className="flex justify-between items-center">
                  <h3 className="font-bold text-white text-sm">{stage}</h3>
                  <span className="text-xs px-2 py-0.5 bg-white/5 text-slate-400 rounded-full font-mono">
                    {stageLeads.length}
                  </span>
                </div>

                {/* Column cards container */}
                <div className="flex-1 space-y-3 overflow-y-auto max-h-[500px] pr-1">
                  {stageLeads.map((lead) => {
                    const score = lead.analysis?.score || 0;
                    return (
                      <div 
                        key={lead.id}
                        className="bg-white/5 border border-white/5 rounded-xl p-3 shadow-md hover:border-white/10 transition-all flex flex-col gap-2"
                      >
                        <div className="flex justify-between items-center gap-1.5">
                          <span className="text-[9px] px-1.5 py-0.5 bg-white/5 text-slate-400 rounded font-semibold truncate">
                            r/{lead.subreddit}
                          </span>
                          <span className={`text-[9px] font-bold ${
                            score >= 80 ? 'text-accent-success' : 'text-accent-warning'
                          }`}>
                            {score} pts
                          </span>
                        </div>
                        
                        <h4 className="text-xs font-bold text-white leading-normal line-clamp-2">{lead.title}</h4>
                        
                        {/* Interactive Move buttons */}
                        <div className="flex justify-between items-center pt-2.5 border-t border-white/5 mt-1">
                          <span className="text-[9px] text-slate-400 truncate max-w-[60%]">
                            {lead.analysis?.recommended_service || 'Service'}
                          </span>
                          
                          {/* Next stage flow arrow picker */}
                          <div className="flex gap-1">
                            {stage !== 'Won' && stage !== 'Lost' && (
                              <button
                                onClick={() => handleMoveStage(lead.id, stages[stages.indexOf(stage) + 1])}
                                className="p-1 hover:bg-white/10 rounded text-slate-300 hover:text-white cursor-pointer"
                                title="Move Forward"
                              >
                                <ChevronRight className="w-3.5 h-3.5" />
                              </button>
                            )}
                            {stage === 'Interested' && (
                              <button
                                onClick={() => handleMoveStage(lead.id, 'Won')}
                                className="p-1 bg-accent-success/10 hover:bg-accent-success/20 rounded text-accent-success cursor-pointer"
                                title="Mark Won"
                              >
                                <CheckCircle className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  
                  {stageLeads.length === 0 && (
                    <div className="h-24 flex items-center justify-center border border-dashed border-white/5 rounded-xl text-xs text-slate-600">
                      Empty
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
