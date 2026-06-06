-- Run this in: Supabase Dashboard → SQL Editor → New query → Paste → Run

CREATE TABLE IF NOT EXISTS public.transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    date DATE NOT NULL,
    amount FLOAT NOT NULL,
    merchant TEXT NOT NULL,
    category TEXT DEFAULT 'Other',
    description TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.budgets (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    category TEXT NOT NULL,
    amount FLOAT NOT NULL,
    period TEXT DEFAULT 'monthly',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, category)
);

CREATE TABLE IF NOT EXISTS public.user_context (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, key)
);

CREATE TABLE IF NOT EXISTS public.conversations (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    title TEXT DEFAULT 'New Chat',
    messages JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    merchant TEXT NOT NULL,
    amount FLOAT NOT NULL,
    frequency_days INTEGER NOT NULL,
    last_seen DATE,
    occurrence_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS public.anomalies (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    transaction_id BIGINT REFERENCES public.transactions(id) ON DELETE SET NULL,
    merchant TEXT,
    amount FLOAT,
    category TEXT,
    date DATE,
    reason TEXT,
    severity TEXT DEFAULT 'medium',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security (service_role key bypasses RLS automatically)
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.anomalies ENABLE ROW LEVEL SECURITY;

-- Policies so users can only see their own data via anon/user tokens
CREATE POLICY "own_data" ON public.transactions FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON public.budgets FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON public.user_context FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON public.conversations FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON public.subscriptions FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON public.anomalies FOR ALL USING (auth.uid() = user_id);
