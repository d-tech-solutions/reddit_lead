'use client';

import { useEffect, useState } from 'react';
import { apiRequest } from '@/lib/api';
import { Terminal, Save, Play, PlayCircle, RefreshCw, CheckCircle2 } from 'lucide-react';

export default function AdminCollectorPage() {
  const [subreddits, setSubreddits] = useState('');
  const [minScore, setMinScore] = useState(70);
  const [loading, setLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [consoleLogs, setConsoleLogs] = useState<string[]>([]);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const data = await apiRequest('/admin/config');
      setSubreddits(data.monitored_subreddits);
      setMinScore(data.min_notification_score);
    } catch (err) {
      console.error('Failed to fetch admin configurations:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setStatusMsg(null);
    try {
      await apiRequest('/admin/config', {
        method: 'PUT',
        json: { subreddits }
      });
      setStatusMsg('Active subreddits configuration updated successfully!');
      logToConsole('SYSTEM: Saved subreddits config: ' + subreddits);
    } catch (err: any) {
      setStatusMsg('Error: ' + err.message);
    } finally {
      setIsSaving(false);
    }
  };

  const logToConsole = (msg: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setConsoleLogs((prev) => [...prev, `[${timestamp}] ${msg}`]);
  };

  const pollTaskStatus = async (taskId: string, component: string): Promise<any> => {
    logToConsole(`${component}: Polling task ID ${taskId}...`);
    return new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        try {
          const data = await apiRequest(`/tasks/${taskId}`);
          logToConsole(`${component}: Task status is ${data.status}`);
          if (data.status === 'SUCCESS') {
            clearInterval(interval);
            resolve(data.result);
          } else if (data.status === 'FAILURE' || data.status === 'REVOKED') {
            clearInterval(interval);
            reject(new Error(`Background task failed with status: ${data.status}`));
          }
        } catch (err) {
          clearInterval(interval);
          reject(err);
        }
      }, 1500);
    });
  };

  const handleTriggerCollection = async () => {
    logToConsole('COLLECTOR: Spawning Reddit RSS feed collection task...');
    try {
      const data = await apiRequest('/admin/trigger/collect', { method: 'POST' });
      const taskId = data.task_id;
      if (taskId) {
        const result = await pollTaskStatus(taskId, 'COLLECTOR');
        logToConsole(`COLLECTOR: Completed. Fetched: ${result.fetched}, Saved: ${result.saved}, Matched: ${result.matched_users}`);
      } else {
        logToConsole('COLLECTOR: Failed. No task ID enqueued.');
      }
    } catch (err: any) {
      logToConsole(`COLLECTOR: Error: ${err.message}`);
    }
  };

  const handleTriggerAnalysis = async () => {
    logToConsole('ANALYZER: Spawning AI scoring matcher task for all active user intent profiles...');
    try {
      const data = await apiRequest('/admin/trigger/analyze', { method: 'POST' });
      const taskIds = data.task_ids;
      if (taskIds && Object.keys(taskIds).length > 0) {
        logToConsole(`ANALYZER: Enqueued ${Object.keys(taskIds).length} user analysis tasks.`);
        
        const pollPromises = Object.entries(taskIds).map(async ([userId, taskId]) => {
          try {
            const res = await pollTaskStatus(taskId as string, `ANALYZER (User ${userId})`);
            logToConsole(`ANALYZER (User ${userId}): Completed matching. Qualified: ${res.processed}, Successful: ${res.successful}`);
          } catch (e: any) {
            logToConsole(`ANALYZER (User ${userId}): Failed: ${e.message}`);
          }
        });
        
        await Promise.all(pollPromises);
        logToConsole('ANALYZER: Global matching cycle complete.');
      } else {
        logToConsole('ANALYZER: Failed. No active users or task IDs returned.');
      }
    } catch (err: any) {
      logToConsole(`ANALYZER: Error: ${err.message}`);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Title Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white tracking-tight">Subreddits & Collector</h1>
        <p className="text-slate-400 text-sm mt-1">
          Configure active subreddits lists and manually trigger backend collection/analysis runner processes
        </p>
      </div>

      {statusMsg && (
        <div className="mb-6 p-4 bg-accent-success/10 border border-accent-success/20 rounded-xl text-accent-success text-xs font-semibold flex items-center gap-2">
          <CheckCircle2 className="w-5 h-5" />
          {statusMsg}
        </div>
      )}

      {/* Split Grid */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch min-h-0">
        
        {/* Controls Column (lg:col-span-5) */}
        <div className="lg:col-span-5 space-y-6">
          
          {/* Subreddits Configuration form */}
          <form onSubmit={handleSaveConfig} className="glass-panel rounded-2xl p-6 space-y-4">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">Subreddits Config</h3>
            
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                Monitored Subreddits (comma separated)
              </label>
              <input
                type="text"
                disabled={loading}
                value={subreddits}
                onChange={(e) => setSubreddits(e.target.value)}
                placeholder="startups, SaaS, forhire..."
                className="w-full glass-input rounded-xl px-3 py-2.5 text-xs text-white"
              />
            </div>

            <button
              type="submit"
              disabled={isSaving || loading}
              className="px-5 py-2 bg-accent-warning hover:bg-accent-warning/95 text-black rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              Save Configuration
            </button>
          </form>

          {/* Trigger manual runners */}
          <div className="glass-panel rounded-2xl p-6 space-y-4">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">Manual System Runners</h3>
            
            <div className="grid grid-cols-2 gap-4">
              <button
                onClick={handleTriggerCollection}
                disabled={loading}
                className="py-3 bg-white/5 hover:bg-white/10 border border-white/5 text-slate-200 hover:text-white rounded-xl text-xs font-bold transition-all flex flex-col items-center justify-center gap-2 cursor-pointer"
              >
                <Play className="w-5 h-5 text-accent-secondary" />
                Trigger Collector
              </button>

              <button
                onClick={handleTriggerAnalysis}
                disabled={loading}
                className="py-3 bg-white/5 hover:bg-white/10 border border-white/5 text-slate-200 hover:text-white rounded-xl text-xs font-bold transition-all flex flex-col items-center justify-center gap-2 cursor-pointer"
              >
                <PlayCircle className="w-5 h-5 text-accent-success" />
                Trigger Matching
              </button>
            </div>
          </div>

        </div>

        {/* System Logs Console Column (lg:col-span-7) */}
        <div className="lg:col-span-7 flex flex-col h-[480px] glass-panel rounded-2xl overflow-hidden border border-white/5">
          <div className="bg-black/30 border-b border-white/5 p-3.5 flex items-center justify-between">
            <span className="text-xs font-bold text-white tracking-wider flex items-center gap-2">
              <Terminal className="w-4.5 h-4.5 text-accent-secondary" />
              Active System Log Console
            </span>
            
            <button
              onClick={() => setConsoleLogs([])}
              className="text-[10px] text-slate-500 hover:text-slate-300 font-bold"
            >
              Clear Logs
            </button>
          </div>

          <div className="flex-1 p-5 bg-black/40 overflow-y-auto font-mono text-[10px] text-accent-success leading-relaxed space-y-1">
            {consoleLogs.map((log, idx) => (
              <div key={idx}>{log}</div>
            ))}
            {consoleLogs.length === 0 && (
              <div className="text-slate-600 text-center py-20">Console active. Trigger a task to stream logs...</div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
