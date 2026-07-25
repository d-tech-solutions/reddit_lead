'use client';

import { useEffect, useState } from 'react';
import { apiRequest } from '@/lib/api';
import { Users, Code, Mail, Eye, ShieldAlert, Sparkles, RefreshCw, X } from 'lucide-react';

interface UserAdminRecord {
  id: number;
  email: string;
  full_name: string | null;
  is_admin: boolean;
  created_at: string;
  onboarding: {
    status: 'not_started' | 'in_progress' | 'completed';
    question_count: number;
    confidence: number;
    profile: Record<string, any> | null;
  };
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserAdminRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserAdminRecord | null>(null);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const data = await apiRequest('/admin/users');
      setUsers(data);
    } catch (err) {
      console.error('Failed to fetch admin users list:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Title Header */}
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            Manage Users <span className="text-xs px-2.5 py-0.5 bg-accent-warning/20 text-accent-warning rounded-full font-mono font-bold">{users.length} Users</span>
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Monitor registered platform users and inspect their generated AI Search Intent Profile JSON configurations
          </p>
        </div>
        <button
          onClick={fetchUsers}
          className="p-2.5 bg-white/5 hover:bg-white/10 border border-white/5 text-slate-300 hover:text-white rounded-xl transition-all cursor-pointer"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Users Table */}
      <div className="w-full flex flex-col h-[550px] glass-panel rounded-2xl overflow-hidden border border-white/5">
        <div className="flex-grow overflow-y-auto">
          {loading ? (
            <div className="h-full flex justify-center items-center">
              <RefreshCw className="w-6 h-6 text-accent-warning animate-spin" />
            </div>
          ) : (
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-black/30 border-b border-white/5 text-slate-400 uppercase font-semibold tracking-wider">
                  <th className="p-4">Name / Email</th>
                  <th className="p-4">Admin</th>
                  <th className="p-4">Onboarding</th>
                  <th className="p-4">Confidence</th>
                  <th className="p-4">Created Date</th>
                  <th className="p-4 text-center">Inspect</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {users.map((u) => (
                  <tr 
                    key={u.id}
                    className={`hover:bg-white/[0.02] transition-colors ${
                      selectedUser?.id === u.id ? 'bg-white/5' : ''
                    }`}
                  >
                    <td className="p-4">
                      <div className="font-bold text-white">{u.full_name || 'Guest'}</div>
                      <div className="text-slate-500 font-mono mt-0.5">{u.email}</div>
                    </td>
                    <td className="p-4">
                      {u.is_admin ? (
                        <span className="text-[10px] px-2 py-0.5 bg-accent-warning/10 text-accent-warning border border-accent-warning/20 rounded font-semibold">
                          Admin
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-500 font-medium">Standard</span>
                      )}
                    </td>
                    <td className="p-4">
                      <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
                        u.onboarding.status === 'completed' ? 'bg-accent-success/15 text-accent-success' :
                        u.onboarding.status === 'in_progress' ? 'bg-accent-secondary/15 text-accent-secondary' :
                        'bg-white/5 text-slate-500'
                      }`}>
                        {u.onboarding.status}
                      </span>
                    </td>
                    <td className="p-4 font-mono font-bold text-slate-300">
                      {Math.round(u.onboarding.confidence * 100)}%
                    </td>
                    <td className="p-4 text-slate-300">
                      {new Date(u.created_at).toLocaleDateString(undefined, {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })}
                    </td>
                    <td className="p-4 text-center">
                      <button
                        onClick={() => setSelectedUser(u)}
                        className="p-1.5 bg-white/5 hover:bg-accent-primary text-slate-400 hover:text-white rounded-lg transition-colors cursor-pointer"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                
                {users.length === 0 && (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-slate-500">
                      No registered users found in the system
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Dialog / Modal for inspecting user details */}
      {selectedUser && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={() => setSelectedUser(null)}
        >
          <div 
            className="w-full max-w-2xl bg-[#0d111b] border border-white/10 rounded-2xl flex flex-col h-[550px] shadow-2xl relative"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex justify-between items-center border-b border-white/5 p-6 pb-4">
              <div>
                <h3 className="font-bold text-white text-lg flex items-center gap-2">
                  <Users className="w-5 h-5 text-accent-warning" />
                  {selectedUser.full_name || 'Guest User'}
                </h3>
                <p className="text-xs font-mono text-slate-400 mt-1">{selectedUser.email}</p>
              </div>
              <button
                onClick={() => setSelectedUser(null)}
                className="p-2 text-slate-400 hover:text-white hover:bg-white/5 rounded-xl transition-all cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* User Meta Data Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="bg-white/5 p-3.5 rounded-xl border border-white/5">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Role</div>
                  <div className="mt-1 font-bold text-sm text-slate-200">
                    {selectedUser.is_admin ? (
                      <span className="text-accent-warning">Admin</span>
                    ) : (
                      <span className="text-slate-400">Standard</span>
                    )}
                  </div>
                </div>
                <div className="bg-white/5 p-3.5 rounded-xl border border-white/5">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Onboarding</div>
                  <div className="mt-1 font-bold text-sm text-slate-200 capitalize">
                    <span className={
                      selectedUser.onboarding.status === 'completed' ? 'text-accent-success' :
                      selectedUser.onboarding.status === 'in_progress' ? 'text-accent-secondary' :
                      'text-slate-500'
                    }>
                      {selectedUser.onboarding.status.replace('_', ' ')}
                    </span>
                  </div>
                </div>
                <div className="bg-white/5 p-3.5 rounded-xl border border-white/5">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Confidence</div>
                  <div className="mt-1 font-bold text-sm text-slate-200">
                    {Math.round(selectedUser.onboarding.confidence * 100)}%
                  </div>
                </div>
                <div className="bg-white/5 p-3.5 rounded-xl border border-white/5">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Created</div>
                  <div className="mt-1 font-bold text-sm text-slate-200">
                    {new Date(selectedUser.created_at).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric'
                    })}
                  </div>
                </div>
              </div>

              {/* JSON Profile */}
              <div className="flex flex-col flex-1 min-h-0">
                <div className="flex items-center gap-2 text-sm text-slate-300 font-semibold mb-3">
                  <Code className="w-4.5 h-4.5 text-accent-secondary" />
                  Search Intent Profile JSON
                </div>
                
                {selectedUser.onboarding.profile ? (
                  <pre className="flex-1 bg-black/40 border border-white/5 rounded-xl p-4 overflow-auto text-xs font-mono text-slate-300 leading-relaxed max-h-[220px]">
                    {JSON.stringify(selectedUser.onboarding.profile, null, 2)}
                  </pre>
                ) : (
                  <div className="flex-grow flex flex-col items-center justify-center p-8 border border-dashed border-white/5 rounded-xl text-sm text-slate-500 min-h-[150px]">
                    <Sparkles className="w-8 h-8 opacity-20 mb-2" />
                    No generated profile. Onboarding is incomplete.
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="border-t border-white/5 p-4 flex justify-end">
              <button
                onClick={() => setSelectedUser(null)}
                className="px-5 py-2 text-slate-300 hover:text-white bg-white/5 hover:bg-white/10 border border-white/5 rounded-xl transition-all font-semibold text-xs cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
