'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/stores/useAuthStore';
import { useOnboardingStore } from '@/stores/useOnboardingStore';
import { apiRequest } from '@/lib/api';
import Link from 'next/link';
import { 
  Inbox, 
  Columns, 
  Bookmark, 
  BarChart3, 
  Settings, 
  ShieldAlert, 
  LogOut, 
  Shield, 
  Sparkles,
  Menu,
  X
} from 'lucide-react';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { token, user, setUser, logout, isInitialized, setInitialized } = useAuthStore();
  const { updateOnboarding } = useOnboardingStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Authenticate user
  useEffect(() => {
    if (!token) {
      router.push('/login');
      return;
    }

    const fetchUserProfileAndOnboarding = async () => {
      try {
        // Fetch current user details
        const me = await apiRequest('/auth/me');
        setUser(me);
        
        // Fetch onboarding status
        const onboarding = await apiRequest('/onboarding/status');
        updateOnboarding({
          status: onboarding.status,
          history: onboarding.history,
          questionCount: onboarding.question_count,
          confidence: onboarding.confidence,
          profile: onboarding.profile
        });
        
        setInitialized(true);
      } catch (err) {
        console.error('Failed to initialize dashboard:', err);
        logout();
        router.push('/login');
      }
    };

    fetchUserProfileAndOnboarding();
  }, [token, router, setUser, logout, updateOnboarding, setInitialized]);

  if (!token || !isInitialized || !user) {
    return (
      <div className="min-h-screen bg-[#080b10] flex flex-col justify-center items-center">
        <div className="p-4 bg-accent-primary/10 rounded-2xl animate-pulse">
          <Shield className="w-8 h-8 text-accent-primary" />
        </div>
        <p className="text-slate-400 mt-4 text-sm font-medium">Validating session...</p>
      </div>
    );
  }

  const menuItems = [
    { name: 'Qualified Inbox', path: '/', icon: Inbox },
    { name: 'CRM Board', path: '/crm', icon: Columns },
    { name: 'Bookmarks', path: '/saved', icon: Bookmark },
    { name: 'Analytics', path: '/analytics', icon: BarChart3 },
    { name: 'Settings', path: '/settings', icon: Settings },
  ];

  return (
    <div className="min-h-screen bg-[#080b10] flex text-slate-100 font-sans">
      {/* Sidebar for Desktop */}
      <aside className="hidden md:flex flex-col w-64 glass-panel border-r border-white/5 p-6 shrink-0 relative z-20">
        {/* Brand Header */}
        <div className="flex items-center gap-3 px-2 mb-8">
          <Shield className="w-6 h-6 text-accent-primary" />
          <span className="text-xl font-bold tracking-tight text-white flex items-center gap-1">
            LeadRadar <span className="text-xs px-1.5 py-0.5 bg-accent-secondary/20 text-accent-secondary rounded font-mono font-medium">AI</span>
          </span>
        </div>

        {/* Nav Links */}
        <nav className="space-y-1.5 flex-1">
          {menuItems.map((item) => {
            const isActive = pathname === item.path;
            const Icon = item.icon;
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200 cursor-pointer ${
                  isActive 
                    ? 'bg-accent-primary text-white shadow-lg shadow-accent-primary/20' 
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <Icon className="w-4 h-4" />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* Superadmin Panel Access Button */}
        {user.is_admin && (
          <Link
            href="/admin"
            className="flex items-center gap-3 px-4 py-3 mb-4 border border-accent-warning/20 bg-accent-warning/5 hover:bg-accent-warning/10 text-accent-warning rounded-xl text-sm font-semibold transition-all duration-200 cursor-pointer"
          >
            <ShieldAlert className="w-4 h-4" />
            Superadmin Panel
          </Link>
        )}

        {/* Bottom Profile Info & Logout */}
        <div className="pt-6 border-t border-white/5 space-y-4">
          <div className="px-2">
            <h4 className="text-sm font-bold text-white truncate">{user.full_name || 'User'}</h4>
            <p className="text-xs text-slate-500 truncate mt-0.5">{user.email}</p>
          </div>
          <button
            onClick={() => { logout(); router.push('/login'); }}
            className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-accent-danger/10 text-slate-400 hover:text-accent-danger rounded-xl text-sm font-semibold transition-all duration-200 cursor-pointer text-left"
          >
            <LogOut className="w-4 h-4" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Mobile Top Navbar */}
      <div className="md:hidden w-full fixed top-0 left-0 h-16 bg-[#0c1017] border-b border-white/5 px-4 flex items-center justify-between z-30">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-accent-primary" />
          <span className="text-lg font-bold text-white">LeadRadar AI</span>
        </div>
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-2 text-slate-400 hover:text-white cursor-pointer"
        >
          {sidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Mobile Sidebar overlay Drawer */}
      {sidebarOpen && (
        <aside className="md:hidden fixed inset-y-0 left-0 w-64 bg-[#0c1017] border-r border-white/5 p-6 z-40 flex flex-col pt-20">
          <nav className="space-y-2 flex-1">
            {menuItems.map((item) => {
              const isActive = pathname === item.path;
              const Icon = item.icon;
              return (
                <Link
                  key={item.path}
                  href={item.path}
                  onClick={() => setSidebarOpen(false)}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all cursor-pointer ${
                    isActive 
                      ? 'bg-accent-primary text-white' 
                      : 'text-slate-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {item.name}
                </Link>
              );
            })}
          </nav>
          
          {user.is_admin && (
            <Link
              href="/admin"
              onClick={() => setSidebarOpen(false)}
              className="flex items-center gap-3 px-4 py-3 mb-4 border border-accent-warning/20 bg-accent-warning/5 text-accent-warning rounded-xl text-sm font-semibold cursor-pointer"
            >
              <ShieldAlert className="w-4 h-4" />
              Superadmin Panel
            </Link>
          )}

          <div className="pt-6 border-t border-white/5 space-y-4">
            <div className="px-2">
              <h4 className="text-sm font-bold text-white truncate">{user.full_name}</h4>
              <p className="text-xs text-slate-500 truncate">{user.email}</p>
            </div>
            <button
              onClick={() => { logout(); router.push('/login'); }}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-slate-400 hover:text-accent-danger rounded-xl text-sm font-semibold cursor-pointer"
            >
              <LogOut className="w-4 h-4" />
              Sign Out
            </button>
          </div>
        </aside>
      )}

      {/* Main Body */}
      <main className="flex-1 flex flex-col min-w-0 pt-16 md:pt-0">
        <div className="flex-1 flex flex-col p-4 md:p-8 overflow-y-auto relative z-10">
          {children}
        </div>
      </main>
    </div>
  );
}
