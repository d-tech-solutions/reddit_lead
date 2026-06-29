'use client';

import { useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuthStore } from '@/stores/useAuthStore';
import { Shield } from 'lucide-react';

function CallbackHandler() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuthStore();

  useEffect(() => {
    const token = searchParams.get('token');
    if (token) {
      // Login with token, is_admin will be refreshed once we query /auth/me
      login(token, false);
      router.push('/');
    } else {
      router.push('/login?error=oauth_failed');
    }
  }, [searchParams, router, login]);

  return (
    <div className="min-h-screen bg-[#080b10] flex flex-col justify-center items-center">
      <div className="inline-flex items-center justify-center p-4 bg-accent-primary/10 rounded-2xl mb-4 border border-accent-primary/20 animate-pulse">
        <Shield className="w-10 h-10 text-accent-primary animate-spin" />
      </div>
      <h2 className="text-xl font-semibold text-white">Completing Google Login...</h2>
      <p className="text-slate-400 mt-2 text-sm">Please wait while we redirect you to your dashboard.</p>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-[#080b10] flex flex-col justify-center items-center">
        <Shield className="w-10 h-10 text-accent-primary animate-spin" />
      </div>
    }>
      <CallbackHandler />
    </Suspense>
  );
}
