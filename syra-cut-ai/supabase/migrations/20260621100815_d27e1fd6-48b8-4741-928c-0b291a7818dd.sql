
ALTER TABLE public.video_jobs
  ADD COLUMN intelligence jsonb,
  ADD COLUMN intelligence_status text NOT NULL DEFAULT 'PENDING';
