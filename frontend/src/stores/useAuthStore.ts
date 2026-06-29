import { create } from 'zustand';

export interface User {
  id: number;
  email: string;
  full_name: string;
  is_admin: boolean;
  created_at?: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  isInitialized: boolean;
  login: (token: string, is_admin: boolean) => void;
  logout: () => void;
  setUser: (user: User | null) => void;
  setInitialized: (val: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: typeof window !== 'undefined' ? localStorage.getItem('lr_token') : null,
  user: null,
  isInitialized: false,
  login: (token, is_admin) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('lr_token', token);
      localStorage.setItem('lr_is_admin', String(is_admin));
    }
    set({ token });
  },
  logout: () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('lr_token');
      localStorage.removeItem('lr_is_admin');
    }
    set({ token: null, user: null });
  },
  setUser: (user) => set({ user }),
  setInitialized: (val) => set({ isInitialized: val }),
}));
