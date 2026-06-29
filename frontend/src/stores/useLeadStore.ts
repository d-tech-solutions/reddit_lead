import { create } from 'zustand';

export interface LeadAnalysisData {
  relevant: boolean;
  score: number;
  industry: string | null;
  urgency: 'Low' | 'Medium' | 'High' | null;
  intent: string | null;
  estimated_budget: string | null;
  recommended_service: string | null;
  summary: string | null;
  suggested_reply: string | null;
  match_reasoning: string[] | null;
  status: 'New' | 'Replied' | 'Interested' | 'Won' | 'Lost';
  saved: boolean;
  notes: { text: string; timestamp: string }[] | null;
  analyzed_at: string;
}

export interface Lead {
  id: number;
  reddit_id: string;
  title: string;
  content: string;
  author: string | null;
  subreddit: string;
  url: string | null;
  created_utc: string;
  collected_at: string;
  analysis: LeadAnalysisData | null;
}

interface LeadState {
  leads: Lead[];
  selectedLeadId: number | null;
  filters: {
    onlyRelevant: boolean;
    minScore: number;
    industry: string;
    statusFilter: string;
    savedOnly: boolean;
  };
  isLoading: boolean;
  error: string | null;
  setSelectedLeadId: (id: number | null) => void;
  setLeads: (leads: Lead[]) => void;
  updateLeadStatus: (leadId: number, status: LeadAnalysisData['status']) => void;
  toggleSavedLead: (leadId: number, saved: boolean) => void;
  addLeadNote: (leadId: number, note: { text: string; timestamp: string }) => void;
  setFilters: (newFilters: Partial<LeadState['filters']>) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useLeadStore = create<LeadState>((set) => ({
  leads: [],
  selectedLeadId: null,
  filters: {
    onlyRelevant: true,
    minScore: 0,
    industry: '',
    statusFilter: '',
    savedOnly: false
  },
  isLoading: false,
  error: null,
  setSelectedLeadId: (id) => set({ selectedLeadId: id }),
  setLeads: (leads) => set({ leads }),
  updateLeadStatus: (leadId, status) => set((state) => ({
    leads: state.leads.map((l) => 
      l.id === leadId && l.analysis 
        ? { ...l, analysis: { ...l.analysis, status } } 
        : l
    )
  })),
  toggleSavedLead: (leadId, saved) => set((state) => ({
    leads: state.leads.map((l) => 
      l.id === leadId && l.analysis 
        ? { ...l, analysis: { ...l.analysis, saved } } 
        : l
    )
  })),
  addLeadNote: (leadId, note) => set((state) => ({
    leads: state.leads.map((l) => 
      l.id === leadId && l.analysis 
        ? { 
            ...l, 
            analysis: { 
              ...l.analysis, 
              notes: [...(l.analysis.notes || []), note] 
            } 
          } 
        : l
    )
  })),
  setFilters: (newFilters) => set((state) => ({
    filters: { ...state.filters, ...newFilters }
  })),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error })
}));
