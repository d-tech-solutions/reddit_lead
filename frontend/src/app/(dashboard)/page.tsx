'use client';

import { useState, useEffect, useRef } from 'react';
import { useOnboardingStore, ChatMessage } from '@/stores/useOnboardingStore';
import { useLeadStore, Lead } from '@/stores/useLeadStore';
import { apiRequest } from '@/lib/api';
import { 
  Send, 
  Inbox,
  Sparkles, 
  TrendingUp, 
  ExternalLink, 
  Copy, 
  Check, 
  Bookmark, 
  MessageSquare,
  Filter,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Briefcase,
  DollarSign,
  ChevronRight,
  RefreshCw,
  Plus
} from 'lucide-react';

export default function DashboardPage() {
  const { 
    status: onboardingStatus, 
    history: chatHistory, 
    question: nextQuestion, 
    confidence, 
    updateOnboarding, 
    resetOnboarding 
  } = useOnboardingStore();

  const { 
    leads, 
    selectedLeadId, 
    filters, 
    isLoading, 
    error,
    setLeads, 
    setSelectedLeadId, 
    updateLeadStatus, 
    toggleSavedLead, 
    addLeadNote, 
    setFilters, 
    setLoading, 
    setError 
  } = useLeadStore();

  // Chat UI states
  const [chatInput, setChatInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // CRM & detail UI states
  const [copied, setCopied] = useState(false);
  const [noteInput, setNoteInput] = useState('');
  const [isRefreshingLeads, setIsRefreshingLeads] = useState(false);

  const selectedLead = leads.find((l) => l.id === selectedLeadId);

  // Fetch leads when onboarding is completed
  useEffect(() => {
    if (onboardingStatus === 'completed') {
      fetchLeads();
    }
  }, [onboardingStatus, filters]);

  // Scroll chat history to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, isTyping]);

  const fetchLeads = async () => {
    setLoading(true);
    setError(null);
    try {
      const queryParams = new URLSearchParams();
      queryParams.set('only_relevant', String(filters.onlyRelevant));
      if (filters.minScore > 0) queryParams.set('min_score', String(filters.minScore));
      if (filters.industry) queryParams.set('industry', filters.industry);
      if (filters.statusFilter) queryParams.set('status_filter', filters.statusFilter);
      if (filters.savedOnly) queryParams.set('saved_only', 'true');

      const data = await apiRequest(`/leads?${queryParams.toString()}`);
      setLeads(data);
      if (data.length > 0 && !selectedLeadId) {
        setSelectedLeadId(data[0].id);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch leads');
    } finally {
      setLoading(false);
    }
  };

  const handleTriggerAnalysis = async () => {
    setIsRefreshingLeads(true);
    try {
      // First collect latest posts, then score
      await apiRequest('/collector/trigger', { method: 'POST' });
      await apiRequest('/leads/analyze', { method: 'POST', json: { limit: 15 } });
      await fetchLeads();
    } catch (err) {
      console.error('Trigger matching failed:', err);
    } finally {
      setIsRefreshingLeads(false);
    }
  };

  // Onboarding conversational flow actions
  const handleStartOnboarding = async () => {
    setIsTyping(true);
    try {
      const data = await apiRequest('/onboarding/start', { method: 'POST' });
      updateOnboarding({
        status: 'in_progress',
        history: [{ role: 'assistant', content: data.question }],
        question: data.question,
        questionCount: 1,
        confidence: 0.0
      });
    } catch (err) {
      console.error(err);
    } finally {
      setIsTyping(false);
    }
  };

  const handleSendChatResponse = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userText = chatInput.trim();
    setChatInput('');
    
    // Optimistic user update
    updateOnboarding({
      history: [...chatHistory, { role: 'user', content: userText }]
    });
    
    setIsTyping(true);
    try {
      const data = await apiRequest('/onboarding/respond', {
        method: 'POST',
        json: { response: userText }
      });
      
      if (data.status === 'completed') {
        updateOnboarding({
          status: 'completed',
          confidence: data.confidence,
          profile: data.profile,
          history: [...chatHistory, { role: 'user', content: userText }, { role: 'assistant', content: data.message }]
        });
      } else {
        updateOnboarding({
          confidence: data.confidence,
          question: data.question,
          history: [...chatHistory, { role: 'user', content: userText }, { role: 'assistant', content: data.question }]
        });
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsTyping(false);
    }
  };

  // CRM action handlers
  const handleStatusChange = async (newStatus: string) => {
    if (!selectedLead) return;
    try {
      await apiRequest(`/leads/${selectedLead.id}/status`, {
        method: 'PATCH',
        json: { status: newStatus }
      });
      updateLeadStatus(selectedLead.id, newStatus as any);
    } catch (err) {
      console.error(err);
    }
  };

  const handleToggleSave = async () => {
    if (!selectedLead || !selectedLead.analysis) return;
    const isSaved = selectedLead.analysis.saved;
    try {
      if (isSaved) {
        await apiRequest(`/leads/${selectedLead.id}/save`, { method: 'DELETE' });
        toggleSavedLead(selectedLead.id, false);
      } else {
        await apiRequest(`/leads/${selectedLead.id}/save`, { method: 'POST' });
        toggleSavedLead(selectedLead.id, true);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedLead || !noteInput.trim()) return;
    
    const text = noteInput.trim();
    setNoteInput('');
    try {
      const data = await apiRequest(`/leads/${selectedLead.id}/notes`, {
        method: 'POST',
        json: { text }
      });
      
      const newNote = data.notes[data.notes.length - 1];
      addLeadNote(selectedLead.id, newNote);
    } catch (err) {
      console.error(err);
    }
  };

  const copyToClipboard = () => {
    if (!selectedLead?.analysis?.suggested_reply) return;
    navigator.clipboard.writeText(selectedLead.analysis.suggested_reply);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // --- RENDERING ONBOARDING VIEW ---

  if (onboardingStatus !== 'completed') {
    return (
      <div className="flex-1 flex flex-col justify-center max-w-4xl mx-auto w-full pt-4 relative">
        <div className="absolute top-0 right-0 w-80 h-80 bg-accent-primary/5 rounded-full blur-3xl"></div>
        
        {/* Onboarding Chat Header */}
        <div className="mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-white/5 pb-6">
          <div>
            <span className="text-xs px-2.5 py-1 bg-accent-primary/10 text-accent-primary rounded-full font-semibold uppercase tracking-wider">
              Setup Conversation
            </span>
            <h1 className="text-2xl font-bold text-white mt-2">Personalize Your AI Researcher</h1>
            <p className="text-slate-400 text-sm mt-1">
              Answer the questions naturally. Our AI will formulate your specific Search Intent Profile.
            </p>
          </div>
          {onboardingStatus === 'in_progress' && (
            <div className="w-full sm:w-48 bg-white/5 border border-white/5 rounded-xl p-3">
              <div className="flex justify-between items-center text-xs font-semibold text-slate-400 mb-1.5">
                <span>Profile Confidence</span>
                <span className="text-accent-secondary">{Math.round(confidence * 100)}%</span>
              </div>
              <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-accent-secondary transition-all duration-500 ease-out" 
                  style={{ width: `${confidence * 100}%` }}
                ></div>
              </div>
            </div>
          )}
        </div>

        {/* Empty Onboarding Start Area */}
        {onboardingStatus === 'not_started' ? (
          <div className="flex-1 glass-panel rounded-2xl p-12 text-center flex flex-col items-center justify-center my-6">
            <div className="w-16 h-16 bg-accent-primary/15 border border-accent-primary/20 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-accent-primary/10">
              <Sparkles className="w-8 h-8 text-accent-primary" />
            </div>
            <h2 className="text-2xl font-extrabold text-white">Let's find your next client project</h2>
            <p className="text-slate-400 text-sm max-w-md mt-3 leading-relaxed">
              Skip traditional keyword queries. Introduce yourself, what you build, and what you exclude to customize your matching engine.
            </p>
            <button
              onClick={handleStartOnboarding}
              className="mt-8 px-8 py-3.5 bg-accent-primary hover:bg-accent-primary-hover text-white font-bold rounded-xl transition-all shadow-lg hover:shadow-accent-primary/20 flex items-center gap-2 cursor-pointer"
            >
              Start Setup Chat
              <ChevronRight className="w-4.5 h-4.5" />
            </button>
          </div>
        ) : (
          /* Active Chat Conversation Log */
          <div className="flex-1 flex flex-col glass-panel rounded-2xl overflow-hidden border border-white/5 shadow-2xl relative">
            <div className="flex-1 p-6 overflow-y-auto space-y-4 min-h-[400px] max-h-[500px]">
              {chatHistory.map((msg, index) => (
                <div 
                  key={index}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`max-w-[80%] rounded-2xl px-4.5 py-3 text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-accent-primary text-white'
                      : 'bg-white/5 border border-white/5 text-slate-100'
                  }`}>
                    {msg.content}
                  </div>
                </div>
              ))}
              {isTyping && (
                <div className="flex justify-start">
                  <div className="bg-white/5 border border-white/5 rounded-2xl px-4.5 py-3 flex items-center gap-1.5">
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"></span>
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce delay-100"></span>
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce delay-200"></span>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Chat message input form */}
            <form onSubmit={handleSendChatResponse} className="p-4 bg-black/20 border-t border-white/5 flex gap-3">
              <input
                type="text"
                disabled={isTyping}
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="E.g., I build Laravel websites and ignore homework..."
                className="flex-1 glass-input rounded-xl px-4 py-3 text-sm text-white disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={isTyping || !chatInput.trim()}
                className="p-3 bg-accent-primary hover:bg-accent-primary-hover disabled:opacity-50 text-white rounded-xl transition-all cursor-pointer"
              >
                <Send className="w-5 h-5" />
              </button>
            </form>
          </div>
        )}
      </div>
    );
  }

  // --- RENDERING INBOX WORKSPACE ---

  // Calculate high-intent lead counts
  const highIntentLeads = leads.filter(l => l.analysis && l.analysis.score >= 80);

  return (
    <div className="flex-1 flex flex-col h-full min-w-0">
      {/* Workspace Header */}
      <div className="mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            Qualified Inbox <span className="text-xs px-2 py-0.5 bg-accent-primary/20 text-accent-primary rounded-full font-mono">{leads.length} Leads</span>
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Continuously analyzing subreddits based on your active intent profile
          </p>
        </div>

        <button
          onClick={handleTriggerAnalysis}
          disabled={isRefreshingLeads}
          className="px-4 py-2.5 bg-white/5 hover:bg-white/10 border border-white/5 text-slate-200 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshingLeads ? 'animate-spin' : ''}`} />
          {isRefreshingLeads ? 'Syncing...' : 'Scan New Leads'}
        </button>
      </div>

      {/* Top Quick Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div className="glass-card rounded-2xl p-5 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">High Intent Opportunities</p>
            <h3 className="text-2xl font-bold text-white mt-1">{highIntentLeads.length}</h3>
          </div>
          <div className="p-3 bg-accent-secondary/15 rounded-xl border border-accent-secondary/20">
            <Sparkles className="w-5 h-5 text-accent-secondary" />
          </div>
        </div>

        <div className="glass-card rounded-2xl p-5 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Average Lead Score</p>
            <h3 className="text-2xl font-bold text-white mt-1">
              {leads.length > 0 
                ? Math.round(leads.reduce((acc, l) => acc + (l.analysis?.score || 0), 0) / leads.length)
                : 0}
            </h3>
          </div>
          <div className="p-3 bg-accent-primary/15 rounded-xl border border-accent-primary/20">
            <TrendingUp className="w-5 h-5 text-accent-primary" />
          </div>
        </div>

        <div className="glass-card rounded-2xl p-5 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Converted Leads</p>
            <h3 className="text-2xl font-bold text-white mt-1">
              {leads.filter(l => l.analysis?.status === 'Won').length}
            </h3>
          </div>
          <div className="p-3 bg-accent-success/15 rounded-xl border border-accent-success/20">
            <CheckCircle2 className="w-5 h-5 text-accent-success" />
          </div>
        </div>
      </div>

      {/* Leads Feed Layout split pane */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-0 items-stretch">
        
        {/* Left Column: Leads List feed (lg:col-span-5) */}
        <div className="lg:col-span-5 flex flex-col h-[650px] glass-panel rounded-2xl overflow-hidden border border-white/5">
          {/* List Search and Filter bar */}
          <div className="p-4 bg-black/20 border-b border-white/5 space-y-3">
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Search leads by industry..."
                value={filters.industry}
                onChange={(e) => setFilters({ industry: e.target.value })}
                className="flex-1 glass-input rounded-xl px-3 py-2 text-xs text-white"
              />
              <select
                value={filters.statusFilter}
                onChange={(e) => setFilters({ statusFilter: e.target.value })}
                className="glass-input rounded-xl px-2.5 py-2 text-xs text-slate-300"
              >
                <option value="">All Statuses</option>
                <option value="New">New</option>
                <option value="Replied">Replied</option>
                <option value="Interested">Interested</option>
                <option value="Won">Won</option>
                <option value="Lost">Lost</option>
              </select>
            </div>
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold cursor-pointer">
                <input
                  type="checkbox"
                  checked={filters.savedOnly}
                  onChange={(e) => setFilters({ savedOnly: e.target.checked })}
                  className="rounded border-white/10 bg-white/5"
                />
                Bookmarks Only
              </label>
              <button 
                onClick={() => setFilters({ onlyRelevant: !filters.onlyRelevant, minScore: 0, industry: '', statusFilter: '', savedOnly: false })}
                className="text-[10px] text-accent-primary hover:underline font-bold"
              >
                Reset Filters
              </button>
            </div>
          </div>

          {/* Leads Scroll Feed list */}
          <div className="flex-1 overflow-y-auto divide-y divide-white/5">
            {isLoading ? (
              <div className="h-full flex justify-center items-center py-10">
                <RefreshCw className="w-6 h-6 text-slate-500 animate-spin" />
              </div>
            ) : error ? (
              <div className="p-8 text-center text-slate-500 text-sm">
                <AlertTriangle className="w-8 h-8 text-accent-danger mx-auto mb-2 opacity-50" />
                {error}
              </div>
            ) : leads.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm">
                <Inbox className="w-8 h-8 mx-auto mb-2 opacity-40" />
                No matching leads found
              </div>
            ) : (
              leads.map((lead) => {
                const isSelected = lead.id === selectedLeadId;
                const score = lead.analysis?.score || 0;
                return (
                  <div
                    key={lead.id}
                    onClick={() => setSelectedLeadId(lead.id)}
                    className={`p-4 transition-all duration-200 cursor-pointer text-left border-l-2 relative ${
                      isSelected 
                        ? 'bg-white/5 border-l-accent-primary' 
                        : 'hover:bg-white/[0.02] border-l-transparent'
                    }`}
                  >
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-xs text-slate-400 font-mono font-medium">r/{lead.subreddit}</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-bold ${
                        score >= 80 
                          ? 'bg-accent-success/10 text-accent-success border border-accent-success/20' 
                          : 'bg-accent-warning/10 text-accent-warning border border-accent-warning/20'
                      }`}>
                        Score: {score}
                      </span>
                    </div>
                    
                    <h4 className="text-sm font-bold text-white mt-1.5 line-clamp-1 leading-snug">{lead.title}</h4>
                    <p className="text-xs text-slate-400 mt-1 line-clamp-2 leading-relaxed">{lead.analysis?.summary}</p>
                    
                    <div className="flex justify-between items-center mt-3 pt-3 border-t border-white/5">
                      <span className="text-[10px] text-slate-500 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(lead.created_utc).toLocaleDateString()}
                      </span>
                      {lead.analysis?.recommended_service && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-white/5 text-slate-300 rounded font-semibold">
                          {lead.analysis.recommended_service}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Lead match details pane (lg:col-span-7) */}
        <div className="lg:col-span-7 flex flex-col h-[650px] glass-panel rounded-2xl overflow-hidden border border-white/5">
          {selectedLead ? (
            <div className="flex-1 flex flex-col overflow-y-auto p-6 space-y-6">
              
              {/* Header section with Direct reddit link & bookmarks */}
              <div className="flex justify-between items-start gap-4 pb-4 border-b border-white/5">
                <div>
                  <h2 className="text-lg font-bold text-white leading-tight">{selectedLead.title}</h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Found by /u/{selectedLead.author || 'anonymous'} in <span className="font-mono text-slate-300">r/{selectedLead.subreddit}</span>
                  </p>
                </div>
                
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={handleToggleSave}
                    className={`p-2 rounded-xl border transition-all cursor-pointer ${
                      selectedLead.analysis?.saved
                        ? 'bg-accent-warning/15 border-accent-warning/30 text-accent-warning'
                        : 'bg-white/5 border-white/5 hover:border-white/10 text-slate-400 hover:text-white'
                    }`}
                  >
                    <Bookmark className="w-5 h-5 fill-current" />
                  </button>
                  <a
                    href={selectedLead.url || '#'}
                    target="_blank"
                    rel="noreferrer"
                    className="p-2 bg-white/5 border border-white/5 hover:border-white/10 text-slate-400 hover:text-white rounded-xl transition-all flex items-center justify-center cursor-pointer"
                  >
                    <ExternalLink className="w-5 h-5" />
                  </a>
                </div>
              </div>

              {/* Core qualifiers grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="bg-white/5 border border-white/5 rounded-xl p-3 text-center">
                  <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Match Score</span>
                  <div className={`text-xl font-bold mt-1 ${
                    (selectedLead.analysis?.score || 0) >= 80 ? 'text-accent-success' : 'text-accent-warning'
                  }`}>
                    {selectedLead.analysis?.score}/100
                  </div>
                </div>

                <div className="bg-white/5 border border-white/5 rounded-xl p-3 text-center">
                  <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Urgency</span>
                  <div className="text-sm font-bold text-white mt-1.5">
                    {selectedLead.analysis?.urgency || 'Unspecified'}
                  </div>
                </div>

                <div className="bg-white/5 border border-white/5 rounded-xl p-3 text-center">
                  <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Estimated value</span>
                  <div className="text-sm font-bold text-accent-secondary mt-1.5">
                    {selectedLead.analysis?.estimated_budget || 'Unspecified'}
                  </div>
                </div>

                <div className="bg-white/5 border border-white/5 rounded-xl p-3 text-center">
                  <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">CRM status</span>
                  <select
                    value={selectedLead.analysis?.status || 'New'}
                    onChange={(e) => handleStatusChange(e.target.value)}
                    className="w-full text-xs font-bold text-center mt-1 text-white border-0 bg-transparent py-0 focus:ring-0"
                  >
                    <option value="New">New</option>
                    <option value="Replied">Replied</option>
                    <option value="Interested">Interested</option>
                    <option value="Won">Won</option>
                    <option value="Lost">Lost</option>
                  </select>
                </div>
              </div>

              {/* AI summary description block */}
              <div>
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">AI Summary</h4>
                <div className="bg-white/5 border border-white/5 rounded-xl p-4 text-sm text-slate-300 leading-relaxed">
                  {selectedLead.analysis?.summary}
                </div>
              </div>

              {/* Why this lead explainability block */}
              <div>
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Why This Lead?</h4>
                <ul className="space-y-1.5">
                  {selectedLead.analysis?.match_reasoning?.map((reason, idx) => (
                    <li key={idx} className="flex items-start gap-2.5 text-sm text-slate-300">
                      <span className="text-accent-success font-bold mt-0.5">✓</span>
                      {reason}
                    </li>
                  )) || <span className="text-xs text-slate-500">No match reasoning details available</span>}
                </ul>
              </div>

              {/* AI suggested reply pitch builder */}
              {selectedLead.analysis?.suggested_reply && (
                <div className="pt-4 border-t border-white/5">
                  <div className="flex justify-between items-center mb-2.5">
                    <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-accent-secondary" />
                      Suggested Pitch Response
                    </h4>
                    <button
                      onClick={copyToClipboard}
                      className="px-2.5 py-1 text-xs bg-white/5 border border-white/5 hover:border-white/10 text-slate-300 rounded flex items-center gap-1.5 cursor-pointer transition-all active:scale-95"
                    >
                      {copied ? <Check className="w-3.5 h-3.5 text-accent-success" /> : <Copy className="w-3.5 h-3.5" />}
                      {copied ? 'Copied!' : 'Copy Reply'}
                    </button>
                  </div>
                  <div className="bg-black/20 border border-white/5 rounded-xl p-4 text-xs font-mono text-slate-300 leading-relaxed whitespace-pre-wrap">
                    {selectedLead.analysis.suggested_reply}
                  </div>
                </div>
              )}

              {/* Notes CRM timeline */}
              <div className="pt-4 border-t border-white/5 space-y-4">
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                  <MessageSquare className="w-3.5 h-3.5" />
                  Interaction Logs & Notes
                </h4>
                
                {/* Notes input form */}
                <form onSubmit={handleAddNote} className="flex gap-2">
                  <input
                    type="text"
                    value={noteInput}
                    onChange={(e) => setNoteInput(e.target.value)}
                    placeholder="Add an internal log note..."
                    className="flex-1 glass-input rounded-xl px-3 py-2 text-xs text-white"
                  />
                  <button
                    type="submit"
                    disabled={!noteInput.trim()}
                    className="px-4 py-2 bg-accent-primary hover:bg-accent-primary-hover text-white rounded-xl text-xs font-bold transition-all disabled:opacity-50 cursor-pointer"
                  >
                    Add
                  </button>
                </form>

                {/* Notes list */}
                <div className="space-y-2">
                  {selectedLead.analysis?.notes?.slice().reverse().map((note, index) => (
                    <div key={index} className="bg-white/5 border border-white/5 rounded-xl p-3 text-xs">
                      <p className="text-slate-200">{note.text}</p>
                      <span className="text-[10px] text-slate-500 mt-1 block">
                        {new Date(note.timestamp).toLocaleString()}
                      </span>
                    </div>
                  )) || <span className="text-xs text-slate-500">No interaction logs recorded</span>}
                </div>
              </div>

            </div>
          ) : (
            <div className="flex-1 flex flex-col justify-center items-center text-center text-slate-500">
              <Inbox className="w-12 h-12 mb-3 opacity-30" />
              <h3 className="text-sm font-bold text-slate-300">No Lead Selected</h3>
              <p className="text-xs max-w-xs mt-1">Select a matched opportunity from the list feed to inspect AI business insights.</p>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
