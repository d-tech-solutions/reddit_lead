import { create } from 'zustand';

export interface ChatMessage {
  role: 'assistant' | 'user';
  content: string;
}

export interface SearchIntentProfile {
  services: string[];
  desired_opportunities: string[];
  target_businesses: string[];
  preferred_industries: string[];
  excluded_opportunities: string[];
  buying_intent_preferences?: {
    require_budget_mention: boolean;
    allow_implied_needs: boolean;
  };
}

interface OnboardingState {
  status: 'not_started' | 'in_progress' | 'completed';
  history: ChatMessage[];
  question: string | null;
  questionCount: number;
  confidence: number;
  profile: SearchIntentProfile | null;
  resetOnboarding: () => void;
  updateOnboarding: (data: Partial<OnboardingState>) => void;
}

export const useOnboardingStore = create<OnboardingState>((set) => ({
  status: 'not_started',
  history: [],
  question: null,
  questionCount: 0,
  confidence: 0.0,
  profile: null,
  resetOnboarding: () => set({
    status: 'not_started',
    history: [],
    question: null,
    questionCount: 0,
    confidence: 0.0,
    profile: null
  }),
  updateOnboarding: (data) => set((state) => ({ ...state, ...data }))
}));
