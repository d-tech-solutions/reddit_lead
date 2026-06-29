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

      {/* Grid: Table on left, JSON Inspect panel on right */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch min-h-0">
        
        {/* Users Table (lg:col-span-7) */}
        <div className="lg:col-span-7 flex flex-col h-[550px] glass-panel rounded-2xl overflow-hidden border border-white/5">
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
                      <td colSpan={5} className="p-8 text-center text-slate-500">
                        No registered users found in the system
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* JSON Inspect Panel (lg:col-span-5) */}
        <div className="lg:col-span-5 flex flex-col h-[550px] glass-panel rounded-2xl overflow-hidden border border-white/5">
          {selectedUser ? (
            <div className="flex-1 flex flex-col p-5 overflow-hidden">
              <div className="flex justify-between items-center border-b border-white/5 pb-4 mb-4">
                <div>
                  <h3 className="font-bold text-white text-sm">{selectedUser.full_name || 'Inspect User'}</h3>
                  <p className="text-[10px] font-mono text-slate-500 mt-0.5">{selectedUser.email}</p>
                </div>
                <button
                  onClick={() => setSelectedUser(null)}
                  className="p-1 text-slate-400 hover:text-white hover:bg-white/5 rounded-lg cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 flex flex-col overflow-hidden">
                <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold mb-2">
                  <Code className="w-4 h-4 text-accent-secondary" />
                  Search Intent Profile JSON
                </div>
                
                {selectedUser.onboarding.profile ? (
                  <pre className="flex-1 bg-black/30 border border-white/5 rounded-xl p-4 overflow-auto text-[10px] font-mono text-slate-300 leading-relaxed">
                    {JSON.stringify(selectedUser.onboarding.profile, null, 2)}
                  </pre>
                ) : (
                  <div className="flex-grow flex items-center justify-center border border-dashed border-white/5 rounded-xl text-xs text-slate-600">
                    No generated profile. Onboarding is incomplete.
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-grow flex flex-col items-center justify-center text-slate-500 p-8 text-center">
              <Users className="w-12 h-12 opacity-30 mb-3 text-slate-600" />
              <h4 className="font-bold text-slate-400 text-sm">Select a user to inspect</h4>
              <p className="text-[10px] max-w-xs mt-1 leading-normal">
                Click the eye icon next to any account in the list to inspect their generated Search Intent Profile JSON parameters.
              </p>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
