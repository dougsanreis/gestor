-- Vibe Funnel OS — PostgreSQL reference schema
-- Convert this file into versioned migrations; do not apply directly to production.

BEGIN;

CREATE TABLE tenants (
  tenant_id text PRIMARY KEY CHECK (tenant_id ~ '^ten_[A-Za-z0-9_-]{8,}$'),
  name text NOT NULL,
  region text NOT NULL DEFAULT 'br',
  status text NOT NULL CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')),
  policy_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE visitor_profiles (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  visitor_id text NOT NULL,
  journey_state text NOT NULL,
  state_version integer NOT NULL DEFAULT 1 CHECK (state_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, visitor_id)
);

CREATE TABLE consent_records (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  consent_id text NOT NULL,
  visitor_id text NOT NULL,
  purpose text NOT NULL CHECK (purpose IN ('ANALYTICS', 'PERSONALIZATION', 'MARKETING', 'REPOSITORY_ACCESS')),
  state text NOT NULL CHECK (state IN ('GRANTED', 'DENIED', 'WITHDRAWN')),
  policy_version text NOT NULL,
  source text NOT NULL,
  recorded_at timestamptz NOT NULL,
  expires_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (tenant_id, consent_id),
  FOREIGN KEY (tenant_id, visitor_id) REFERENCES visitor_profiles(tenant_id, visitor_id)
);

CREATE INDEX consent_records_visitor_purpose_idx
  ON consent_records (tenant_id, visitor_id, purpose, recorded_at DESC);

CREATE TABLE missions (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  mission_id text NOT NULL,
  mission_type text NOT NULL,
  goal text NOT NULL,
  scope jsonb NOT NULL,
  risk_class text NOT NULL CHECK (risk_class IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
  autonomy_level text NOT NULL CHECK (autonomy_level IN ('L0', 'L1', 'L2', 'L3', 'L4')),
  state text NOT NULL CHECK (state IN (
    'DRAFT', 'VALIDATING', 'PLANNED', 'RUNNING', 'WAITING_APPROVAL',
    'EVALUATING', 'APPROVED', 'RELEASED', 'OBSERVING', 'COMPLETED',
    'REJECTED', 'CANCELLED', 'ROLLED_BACK'
  )),
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  budgets jsonb NOT NULL,
  policies jsonb NOT NULL,
  success_criteria jsonb NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, mission_id)
);

CREATE INDEX missions_state_idx ON missions (tenant_id, state, updated_at);

CREATE TABLE mission_steps (
  tenant_id text NOT NULL,
  step_id text NOT NULL,
  mission_id text NOT NULL,
  step_type text NOT NULL,
  state text NOT NULL CHECK (state IN ('PENDING', 'READY', 'RUNNING', 'WAITING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
  dependencies jsonb NOT NULL DEFAULT '[]'::jsonb,
  input_artifact_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  output_artifact_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
  max_attempts integer NOT NULL CHECK (max_attempts > 0),
  lease_owner text,
  lease_expires_at timestamptz,
  idempotency_key text NOT NULL,
  last_error jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, step_id),
  FOREIGN KEY (tenant_id, mission_id) REFERENCES missions(tenant_id, mission_id),
  UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX mission_steps_claim_idx
  ON mission_steps (tenant_id, state, lease_expires_at, created_at);

CREATE TABLE artifacts (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  artifact_id text NOT NULL,
  mission_id text NOT NULL,
  artifact_type text NOT NULL,
  schema_version text NOT NULL,
  content_uri text NOT NULL,
  content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[a-f0-9]{64}$'),
  generator jsonb NOT NULL,
  sources jsonb NOT NULL DEFAULT '[]'::jsonb,
  classification text NOT NULL CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')),
  contains_personal_data boolean NOT NULL DEFAULT false,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, artifact_id),
  FOREIGN KEY (tenant_id, mission_id) REFERENCES missions(tenant_id, mission_id)
);

CREATE TABLE evaluations (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  evaluation_id text NOT NULL,
  artifact_id text NOT NULL,
  rubric_version text NOT NULL,
  evaluator_identity text NOT NULL,
  evaluator_run_id text NOT NULL,
  verdict text NOT NULL CHECK (verdict IN ('PASS', 'REWORK', 'FAIL')),
  findings jsonb NOT NULL DEFAULT '[]'::jsonb,
  scores jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, evaluation_id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifacts(tenant_id, artifact_id)
);

CREATE TABLE governance_decisions (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  decision_id text NOT NULL,
  subject_type text NOT NULL,
  subject_id text NOT NULL,
  policy_version text NOT NULL,
  risk_class text NOT NULL CHECK (risk_class IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
  decision text NOT NULL CHECK (decision IN ('APPROVE', 'REQUIRE_APPROVAL', 'REWORK', 'REJECT', 'PAUSE', 'ROLLBACK')),
  reason_codes jsonb NOT NULL,
  blocking_failures jsonb NOT NULL DEFAULT '[]'::jsonb,
  required_approvals jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  issued_by text NOT NULL,
  issued_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, decision_id)
);

CREATE TABLE approvals (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  approval_id text NOT NULL,
  decision_id text NOT NULL,
  role text NOT NULL,
  actor_id text NOT NULL,
  status text NOT NULL CHECK (status IN ('APPROVED', 'REJECTED', 'REVOKED')),
  reason text,
  signed_at timestamptz NOT NULL,
  expires_at timestamptz,
  PRIMARY KEY (tenant_id, approval_id),
  FOREIGN KEY (tenant_id, decision_id) REFERENCES governance_decisions(tenant_id, decision_id)
);

CREATE TABLE evidence_records (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  evidence_id text NOT NULL,
  evidence_type text NOT NULL,
  source_uri text,
  content_hash text NOT NULL,
  license_or_permission text,
  status text NOT NULL CHECK (status IN ('PENDING', 'VALID', 'EXPIRED', 'REVOKED', 'REJECTED')),
  valid_from timestamptz,
  valid_until timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, evidence_id)
);

CREATE TABLE claims (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  claim_id text NOT NULL,
  exact_text text NOT NULL,
  claim_type text NOT NULL CHECK (claim_type IN ('FACTUAL', 'TESTIMONIAL', 'CASE', 'COMPARISON', 'GUARANTEE')),
  risk_class text NOT NULL CHECK (risk_class IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
  scope jsonb NOT NULL,
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL CHECK (status IN ('DRAFT', 'APPROVED', 'EXPIRED', 'REJECTED')),
  approved_by text,
  valid_from timestamptz,
  valid_until timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, claim_id)
);

CREATE TABLE content_items (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  content_id text NOT NULL,
  funnel_id text NOT NULL,
  module text NOT NULL,
  locale text NOT NULL,
  risk_class text NOT NULL CHECK (risk_class IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
  status text NOT NULL CHECK (status IN ('DRAFT', 'PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')),
  content jsonb NOT NULL,
  claim_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  proof_dependencies jsonb NOT NULL DEFAULT '[]'::jsonb,
  content_hash text NOT NULL,
  approved_by text,
  approved_at timestamptz,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, content_id)
);

CREATE INDEX content_eligibility_idx
  ON content_items (tenant_id, funnel_id, module, locale, status, expires_at);

CREATE TABLE experiments (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  experiment_id text NOT NULL,
  hypothesis_id text NOT NULL,
  state text NOT NULL CHECK (state IN ('DRAFT', 'REVIEW', 'REJECTED', 'APPROVED', 'RUNNING', 'PAUSED', 'ANALYZING', 'PROMOTED', 'KEEP_CONTROL', 'INVALID', 'OBSERVING', 'ROLLED_BACK', 'CLOSED')),
  spec jsonb NOT NULL,
  spec_hash text NOT NULL,
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  governance_decision_id text,
  started_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, experiment_id)
);

CREATE TABLE exposures (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  exposure_id text NOT NULL,
  experiment_id text NOT NULL,
  allocation_epoch integer NOT NULL CHECK (allocation_epoch >= 1),
  unit_type text NOT NULL,
  unit_id_hash text NOT NULL,
  variant_id text NOT NULL,
  decision_id text NOT NULL,
  exposed_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, exposure_id),
  FOREIGN KEY (tenant_id, experiment_id) REFERENCES experiments(tenant_id, experiment_id),
  UNIQUE (tenant_id, experiment_id, allocation_epoch, unit_id_hash)
);

CREATE INDEX exposures_analysis_idx
  ON exposures (tenant_id, experiment_id, variant_id, exposed_at);

CREATE TABLE journey_events (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  event_id text NOT NULL,
  event_name text NOT NULL,
  schema_version text NOT NULL,
  occurred_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  anonymous_id text,
  user_id text,
  session_id text NOT NULL,
  funnel_id text,
  page_id text,
  page_version text,
  decision_id text,
  experiment_id text,
  variant_id text,
  consent_state jsonb NOT NULL,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  context jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text NOT NULL,
  status text NOT NULL DEFAULT 'ACCEPTED' CHECK (status IN ('ACCEPTED', 'DUPLICATE', 'QUARANTINED')),
  PRIMARY KEY (tenant_id, event_id),
  UNIQUE (tenant_id, idempotency_key),
  CHECK (anonymous_id IS NOT NULL OR user_id IS NOT NULL)
);

CREATE INDEX journey_events_metric_idx
  ON journey_events (tenant_id, event_name, occurred_at);

CREATE TABLE releases (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  release_id text NOT NULL,
  subject_id text NOT NULL,
  artifact_hash text NOT NULL,
  state text NOT NULL CHECK (state IN ('DRAFT', 'APPROVED', 'STAGING', 'CANARY', 'PROMOTED', 'PAUSED', 'ROLLED_BACK', 'FAILED')),
  feature_flag text NOT NULL,
  previous_healthy_release_id text,
  governance_decision_id text NOT NULL,
  manifest jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, release_id)
);

CREATE TABLE incidents (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  incident_id text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('SEV-0', 'SEV-1', 'SEV-2', 'SEV-3')),
  status text NOT NULL CHECK (status IN ('OPEN', 'MITIGATING', 'MONITORING', 'CLOSED')),
  title text NOT NULL,
  impact jsonb NOT NULL,
  timeline jsonb NOT NULL DEFAULT '[]'::jsonb,
  commander_id text,
  opened_at timestamptz NOT NULL,
  mitigated_at timestamptz,
  closed_at timestamptz,
  PRIMARY KEY (tenant_id, incident_id)
);

CREATE TABLE outbox_events (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  outbox_id bigserial NOT NULL,
  aggregate_type text NOT NULL,
  aggregate_id text NOT NULL,
  aggregate_version integer NOT NULL,
  event_type text NOT NULL,
  event_version text NOT NULL,
  payload jsonb NOT NULL,
  idempotency_key text NOT NULL,
  occurred_at timestamptz NOT NULL,
  published_at timestamptz,
  attempts integer NOT NULL DEFAULT 0,
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  last_error text,
  PRIMARY KEY (tenant_id, outbox_id),
  UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX outbox_unpublished_idx
  ON outbox_events (tenant_id, next_attempt_at, outbox_id)
  WHERE published_at IS NULL;

-- Tenant-scoped tables use app.tenant_id set inside the authenticated transaction.
DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'visitor_profiles', 'consent_records', 'missions', 'mission_steps',
    'artifacts', 'evaluations', 'governance_decisions', 'approvals',
    'evidence_records', 'claims', 'content_items', 'experiments', 'exposures',
    'journey_events', 'releases', 'incidents', 'outbox_events'
  ]
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
      'CREATE POLICY tenant_isolation_%I ON %I USING (tenant_id = current_setting(''app.tenant_id'', true)) WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))',
      table_name,
      table_name
    );
  END LOOP;
END $$;

COMMIT;
