'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/stores/useAuthStore';
import Link from 'next/link';
import { 
  ShieldCheck, 
  Users, 
  Cpu, 
  Terminal, 
  Sliders, 
  ArrowLeft, 
  Lock,
  Menu,
  X
} from 'lucide-react';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, token, isInitialized } = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Enforce admin check
  if (!token || !isInitialized || !user) {
    return (
      <div className="min-h-screen bg-[#080b10] flex justify-center items-center">
        <Lock className="w-8 h-8 text-accent-danger animate-bounce" />
      </div>
    );
  }

  // Reject non-admins
  if (!user.is_admin) {
    return (
      <div className="min-h-screen bg-[#080b10] flex flex-col justify-center items-center px-4 text-center">
        <div className="p-4 bg-accent-danger/10 border border-accent-danger/20 rounded-2xl mb-4">
          <Lock className="w-10 h-10 text-accent-danger" />
        </div>
        <h1 className="text-2xl font-bold text-white">403 - Access Denied</h1>
        <p className="text-slate-400 text-sm mt-2 max-w-sm">
          You do not have administrative privileges to access this control panel.
        </p>
        <Link
          href="/"
          className="mt-6 px-6 py-2.5 bg-accent-primary hover:bg-accent-primary-hover text-white rounded-xl text-xs font-bold transition-all cursor-pointer"
        >
          Return to Dashboard
        </Link>
      </div>
    );
  }

  const adminMenu = [
    { name: 'Admin Overview', path: '/admin', icon: Sliders },
    { name: 'Manage Users', path: '/admin/users', icon: Users },
    { name: 'Subreddits & Collector', path: '/admin/collector', icon: Terminal },
  ];

  return (
    <div className="min-h-screen bg-[#06080c] flex text-slate-100 font-sans">
      
      {/* Admin Sidebar for Desktop */}
      <aside className="hidden md:flex flex-col w-64 glass-panel border-r border-accent-warning/10 p-6 shrink-0 relative z-20">
        <div className="flex items-center gap-3 px-2 mb-8">
          <ShieldCheck className="w-6 h-6 text-accent-warning" />
          <span className="text-lg font-bold tracking-tight text-white">
            LR Admin Panel
          </span>
        </div>

        <nav className="space-y-1.5 flex-1">
          {adminMenu.map((item) => {
            const isActive = pathname === item.path;
            const Icon = item.icon;
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 cursor-pointer ${
                  isActive 
                    ? 'bg-accent-warning text-black shadow-lg shadow-accent-warning/20' 
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <Icon className="w-4 h-4" />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* Exit Admin Mode */}
        <div className="pt-6 border-t border-white/5">
          <Link
            href="/"
            className="flex items-center gap-3 px-4 py-3 hover:bg-white/5 text-slate-400 hover:text-white rounded-xl text-sm font-semibold transition-all duration-200 cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
            Exit Admin Mode
          </Link>
        </div>
      </aside>

      {/* Mobile Top Navbar */}
      <div className="md:hidden w-full fixed top-0 left-0 h-16 bg-[#06080c] border-b border-accent-warning/10 px-4 flex items-center justify-between z-30">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-accent-warning" />
          <span className="text-md font-bold text-white">LR Admin Portal</span>
        </div>
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-2 text-slate-400 hover:text-white cursor-pointer"
        >
          {sidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Mobile Admin Sidebar overlay drawer */}
      {sidebarOpen && (
        <aside className="md:hidden fixed inset-y-0 left-0 w-64 bg-[#06080c] border-r border-white/5 p-6 z-40 flex flex-col pt-20">
          <nav className="space-y-2 flex-1">
            {adminMenu.map((item) => {
              const isActive = pathname === item.path;
              const Icon = item.icon;
              return (
                <Link
                  key={item.path}
                  href={item.path}
                  onClick={() => setSidebarOpen(false)}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition-all cursor-pointer ${
                    isActive 
                      ? 'bg-accent-warning text-black' 
                      : 'text-slate-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {item.name}
                </Link>
              );
            })}
          </nav>

          <div className="pt-6 border-t border-white/5">
            <Link
              href="/"
              onClick={() => setSidebarOpen(false)}
              className="flex items-center gap-3 px-4 py-3 text-slate-400 hover:text-white rounded-xl text-sm font-semibold cursor-pointer"
            >
              <ArrowLeft className="w-4 h-4" />
              Exit Admin Mode
            </Link>
          </div>
        </aside>
      )}

      {/* Main Admin workspace */}
      <main className="flex-1 flex flex-col min-w-0 pt-16 md:pt-0">
        <div className="flex-1 flex flex-col p-4 md:p-8 overflow-y-auto relative z-10">
          {children}
        </div>
      </main>
    </div>
  );
}
