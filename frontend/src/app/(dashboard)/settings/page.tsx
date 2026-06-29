'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/useAuthStore';
import { useOnboardingStore } from '@/stores/useOnboardingStore';
import { apiRequest } from '@/lib/api';
import { RefreshCw, Save, Send, AlertTriangle, ShieldCheck } from 'lucide-react';

export default function SettingsPage() {
  const router = useRouter();
  const { user, setUser } = useAuthStore();
  const { resetOnboarding } = useOnboardingStore();
  
  const [minScore, setMinScore] = useState(70);
  const [telegramChatId, setTelegramChatId] = useState('1592153261');
  const [isSaving, setIsSaving] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSuccessMsg(null);
    try {
      // In production, configure through user profile update APIs
      await new Promise(r => setTimeout(r, 800)); // Simulate save
      setSuccessMsg('Notification preferences saved successfully!');
    } catch (err) {
      console.error(err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleResetProfile = async () => {
    if (!confirm('Are you absolutely sure you want to delete your Search Intent Profile? This will erase your current AI matching settings and trigger onboarding chat again.')) {
      return;
    }
    
    setIsResetting(true);
    try {
      // Initialize onboarding on the backend clears existing profile
      await apiRequest('/onboarding/start', { method: 'POST' });
      resetOnboarding();
      router.push('/');
    } catch (err) {
      console.error('Failed to reset profile:', err);
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col max-w-3xl mx-auto w-full pt-4">
      {/* Title Header */}
      <div className="mb-8 border-b border-white/5 pb-6">
        <h1 className="text-2xl font-bold text-white tracking-tight">Account Settings</h1>
        <p className="text-slate-400 text-sm mt-1">
          Configure notifications, Telegram alert integrations, and manage your AI Search Intent Profile
        </p>
      </div>

      {successMsg && (
        <div className="mb-6 p-4 bg-accent-success/10 border border-accent-success/20 rounded-xl text-accent-success text-sm font-medium flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 shrink-0" />
          {successMsg}
        </div>
      )}

      <div className="space-y-6">
        
        {/* Section 1: Telegram Alert Integration Settings */}
        <form onSubmit={handleSaveSettings} className="glass-panel rounded-2xl p-6 space-y-5">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Alert Configurations</h3>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                Min Notification Score
              </label>
              <input
                type="number"
                min="0"
                max="100"
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full glass-input rounded-xl px-4 py-3 text-sm text-white"
              />
              <p className="text-[10px] text-slate-500 mt-1">Leads with scores below this will not trigger active Telegram messages.</p>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                Telegram Chat ID
              </label>
              <input
                type="text"
                value={telegramChatId}
                onChange={(e) => setTelegramChatId(e.target.value)}
                className="w-full glass-input rounded-xl px-4 py-3 text-sm text-white"
              />
              <p className="text-[10px] text-slate-500 mt-1">Your numeric Telegram account ID linked via the LeadRadar bot.</p>
            </div>
          </div>

          <button
            type="submit"
            disabled={isSaving}
            className="px-6 py-2.5 bg-accent-primary hover:bg-accent-primary-hover text-white rounded-xl text-xs font-bold transition-all flex items-center gap-2 disabled:opacity-50 cursor-pointer"
          >
            <Save className="w-4 h-4" />
            {isSaving ? 'Saving...' : 'Save Settings'}
          </button>
        </form>

        {/* Section 2: Reset Preference Intent Profile (CAUTION area) */}
        <div className="glass-panel rounded-2xl p-6 space-y-4 border border-accent-danger/20 bg-accent-danger/[0.02]">
          <h3 className="text-sm font-bold text-accent-danger uppercase tracking-wider flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4" />
            Danger Zone
          </h3>
          
          <p className="text-slate-400 text-xs leading-relaxed max-w-xl">
            Deleting your profile deletes the underlying semantic constraints. Your qualified lead inbox feed will be locked until you complete a new setup chat session.
          </p>

          <button
            onClick={handleResetProfile}
            disabled={isResetting}
            className="px-6 py-2.5 bg-accent-danger hover:bg-accent-danger/80 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-2 disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${isResetting ? 'animate-spin' : ''}`} />
            {isResetting ? 'Resetting Profile...' : 'Reset Search Intent Profile'}
          </button>
        </div>

      </div>
    </div>
  );
}
