import { useAuthStore } from '../stores/useAuthStore';

// In production, configure through Vercel environment variables
const API_BASE_URL = typeof window !== 'undefined' && window.location.hostname !== 'localhost'
  ? 'https://your-backend-api-production.com'  // production fallback
  : 'http://localhost:8000';

interface RequestOptions extends RequestInit {
  json?: any;
}

export async function apiRequest<T = any>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = useAuthStore.getState().token;
  
  const headers = new Headers(options.headers || {});
  
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  
  if (options.json) {
    headers.set('Content-Type', 'application/json');
    options.body = JSON.stringify(options.json);
  }
  
  const url = `${API_BASE_URL}${path}`;
  const response = await fetch(url, {
    ...options,
    headers,
  });
  
  if (response.status === 401 && token) {
    // Session expired, logout user
    useAuthStore.getState().logout();
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
    throw new Error('Session expired');
  }
  
  if (!response.ok) {
    let errorDetail = 'API Request Failed';
    try {
      const errorJson = await response.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }
  
  // For RedirectResponse or other non-json responses, handle appropriately
  if (response.headers.get('content-type')?.includes('application/json')) {
    return response.json() as Promise<T>;
  }
  
  return {} as Promise<T>;
}
