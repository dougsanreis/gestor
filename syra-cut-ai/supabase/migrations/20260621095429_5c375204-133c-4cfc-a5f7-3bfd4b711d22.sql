
CREATE TYPE public.video_job_status AS ENUM (
  'UPLOADED','QUEUED','PROCESSING','TRANSCRIBING','ANALYZING',
  'CUTTING','RENDERING','VALIDATING','READY_FOR_HUMAN_REVIEW','FAILED'
);

CREATE TABLE public.video_jobs (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  source_file_path text,
  source_file_url text,
  output_file_path text,
  output_file_url text,
  status public.video_job_status NOT NULL DEFAULT 'UPLOADED',
  progress int NOT NULL DEFAULT 0,
  duration_seconds numeric,
  width int,
  height int,
  transcript text,
  title_suggestion text,
  virality_score int,
  error_message text,
  source_file_name text,
  source_file_size bigint,
  technical_report jsonb,
  simulated boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.video_job_events (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES public.video_jobs(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  message text,
  payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.video_assets (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES public.video_jobs(id) ON DELETE CASCADE,
  type text NOT NULL,
  path text,
  url text,
  metadata jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_video_jobs_user ON public.video_jobs(user_id, created_at DESC);
CREATE INDEX idx_video_job_events_job ON public.video_job_events(job_id, created_at DESC);
CREATE INDEX idx_video_assets_job ON public.video_assets(job_id, created_at DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.video_jobs TO authenticated;
GRANT ALL ON public.video_jobs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.video_job_events TO authenticated;
GRANT ALL ON public.video_job_events TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.video_assets TO authenticated;
GRANT ALL ON public.video_assets TO service_role;

ALTER TABLE public.video_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.video_job_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.video_assets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage their own jobs" ON public.video_jobs
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users view events of their jobs" ON public.video_job_events
  FOR SELECT USING (EXISTS (
    SELECT 1 FROM public.video_jobs j WHERE j.id = job_id AND j.user_id = auth.uid()
  ));
CREATE POLICY "Users insert events of their jobs" ON public.video_job_events
  FOR INSERT WITH CHECK (EXISTS (
    SELECT 1 FROM public.video_jobs j WHERE j.id = job_id AND j.user_id = auth.uid()
  ));

CREATE POLICY "Users view assets of their jobs" ON public.video_assets
  FOR SELECT USING (EXISTS (
    SELECT 1 FROM public.video_jobs j WHERE j.id = job_id AND j.user_id = auth.uid()
  ));
CREATE POLICY "Users insert assets of their jobs" ON public.video_assets
  FOR INSERT WITH CHECK (EXISTS (
    SELECT 1 FROM public.video_jobs j WHERE j.id = job_id AND j.user_id = auth.uid()
  ));

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = public;

CREATE TRIGGER update_video_jobs_updated_at
  BEFORE UPDATE ON public.video_jobs
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER PUBLICATION supabase_realtime ADD TABLE public.video_jobs;
ALTER PUBLICATION supabase_realtime ADD TABLE public.video_job_events;

-- Storage policies: users can only touch files under their own user-id folder
CREATE POLICY "Users read own source videos" ON storage.objects
  FOR SELECT TO authenticated USING (
    bucket_id = 'source-videos' AND (storage.foldername(name))[1] = auth.uid()::text
  );
CREATE POLICY "Users upload own source videos" ON storage.objects
  FOR INSERT TO authenticated WITH CHECK (
    bucket_id = 'source-videos' AND (storage.foldername(name))[1] = auth.uid()::text
  );
CREATE POLICY "Users delete own source videos" ON storage.objects
  FOR DELETE TO authenticated USING (
    bucket_id = 'source-videos' AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "Users read own rendered videos" ON storage.objects
  FOR SELECT TO authenticated USING (
    bucket_id = 'rendered-videos' AND (storage.foldername(name))[1] = auth.uid()::text
  );
CREATE POLICY "Users read own reports" ON storage.objects
  FOR SELECT TO authenticated USING (
    bucket_id = 'reports' AND (storage.foldername(name))[1] = auth.uid()::text
  );
