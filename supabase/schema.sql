-- ============================================================
-- 1. Jobs table
-- ============================================================
CREATE TABLE public.jobs (
  id                UUID PRIMARY KEY,            
  user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  status            TEXT NOT NULL DEFAULT 'processing'
                    CHECK (status IN ('processing', 'completed', 'failed')),
  title             TEXT NOT NULL,               
  total_pages       INTEGER DEFAULT 0,
  total_components  INTEGER DEFAULT 0,
  results           JSONB,                       
  storage_path      TEXT                         
);

CREATE INDEX idx_jobs_user_id ON public.jobs (user_id);

-- ============================================================
-- 2. Row Level Security
-- ============================================================
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own jobs"
  ON public.jobs FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own jobs"
  ON public.jobs FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own jobs"
  ON public.jobs FOR DELETE
  USING (auth.uid() = user_id);


-- ============================================================
-- 3. Storage bucket: scans
-- ============================================================
INSERT INTO storage.buckets (id, name, public)
  VALUES ('scans', 'scans', true)
  ON CONFLICT (id) DO NOTHING;

CREATE POLICY "Authenticated users can upload to own folder"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'scans'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "Public read access for scans"
  ON storage.objects FOR SELECT
  TO public
  USING (bucket_id = 'scans');

CREATE POLICY "Users can delete own scans"
  ON storage.objects FOR DELETE
  TO authenticated
  USING (
    bucket_id = 'scans'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );
