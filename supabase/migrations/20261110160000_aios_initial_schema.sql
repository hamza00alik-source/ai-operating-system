-- AIOS initial PostgreSQL schema baseline.
-- Source: src/ai_os/db.py and src/ai_os/workflows.py
-- Intended for a new/empty AIOS database. No customer data is inserted.
-- This migration is not applied to the connected Supabase production project.

CREATE TABLE IF NOT EXISTS public.tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    department TEXT NOT NULL DEFAULT 'general',
    business_id TEXT NOT NULL DEFAULT 'core',
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public.approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    business_id TEXT NOT NULL DEFAULT 'core',
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    decided_at TEXT,
    FOREIGN KEY (task_id) REFERENCES public.tasks(id)
);

CREATE TABLE IF NOT EXISTS public.discovery_scans (
    id TEXT PRIMARY KEY,
    categories TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    result_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS public.provider_catalog_entries (
    source_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    website TEXT NOT NULL DEFAULT '',
    api_key_url TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    free_tier_json TEXT NOT NULL DEFAULT '{}',
    policy_json TEXT NOT NULL DEFAULT '{}',
    confidence TEXT NOT NULL DEFAULT 'unknown',
    last_verified TEXT,
    probe_json TEXT NOT NULL DEFAULT '{}',
    status_json TEXT NOT NULL DEFAULT '{}',
    sources_json TEXT NOT NULL DEFAULT '[]',
    source_url TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    review_state TEXT NOT NULL DEFAULT 'pending',
    PRIMARY KEY (source_id, provider_id)
);

CREATE TABLE IF NOT EXISTS public.research_sources (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL DEFAULT 'core',
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS public.provider_credentials (
    provider TEXT PRIMARY KEY,
    encrypted_secret TEXT NOT NULL,
    model TEXT NOT NULL,
    base_url TEXT NOT NULL,
    free_confirmed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS public.business_integration_credentials (
    business_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    encrypted_secret TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (business_id, provider)
);

CREATE TABLE IF NOT EXISTS public.agent_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    assigned_agent_id TEXT,
    specialist_output TEXT,
    ceo_review TEXT,
    usage_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (task_id) REFERENCES public.tasks(id)
);

CREATE TABLE IF NOT EXISTS public.agent_run_events (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES public.agent_runs(id)
);

CREATE TABLE IF NOT EXISTS public.agent_run_steps (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    role TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    input_summary TEXT NOT NULL DEFAULT '',
    output TEXT NOT NULL DEFAULT '',
    error TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (run_id) REFERENCES public.agent_runs(id),
    UNIQUE (run_id, sequence_no)
);

CREATE TABLE IF NOT EXISTS public.brain_experiences (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    task_id TEXT,
    business_id TEXT NOT NULL DEFAULT 'core',
    department TEXT NOT NULL DEFAULT 'general',
    task_title TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public.brain_memories (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL DEFAULT 'core',
    category TEXT NOT NULL DEFAULT 'lesson',
    department TEXT NOT NULL DEFAULT 'general',
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_run_id TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    review_note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS public.owner_sessions (
    token_hash TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public.business_records (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL DEFAULT 'core',
    record_type TEXT NOT NULL CHECK (record_type IN ('customer', 'expense', 'revenue')),
    title TEXT NOT NULL,
    amount REAL,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    approval_id TEXT,
    contact TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public.investor_contacts (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL DEFAULT 'core',
    name TEXT NOT NULL,
    organization TEXT NOT NULL DEFAULT '',
    contact TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT 'prospect',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public.code_assets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    repository_url TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    asset_type TEXT NOT NULL DEFAULT 'source_code',
    ownership_status TEXT NOT NULL DEFAULT 'unverified',
    license TEXT NOT NULL DEFAULT 'unknown',
    dependency_review TEXT NOT NULL DEFAULT 'not_reviewed',
    token_estimate INTEGER,
    token_method TEXT NOT NULL DEFAULT 'not_measured',
    git_history_tokens INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public.license_offers (
    id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    buyer TEXT NOT NULL,
    terms TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft_pending_owner_approval',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES public.code_assets(id)
);

CREATE TABLE IF NOT EXISTS public.department_messages (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    sender_department TEXT NOT NULL,
    recipient_department TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    related_task_id TEXT,
    status TEXT NOT NULL DEFAULT 'unread',
    created_at TEXT NOT NULL,
    read_at TEXT,
    FOREIGN KEY (related_task_id) REFERENCES public.tasks(id)
);

CREATE TABLE IF NOT EXISTS public.department_delegations (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    parent_task_id TEXT,
    child_task_id TEXT NOT NULL UNIQUE,
    from_department TEXT NOT NULL,
    to_department TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TEXT NOT NULL,
    FOREIGN KEY (parent_task_id) REFERENCES public.tasks(id),
    FOREIGN KEY (child_task_id) REFERENCES public.tasks(id)
);

CREATE TABLE IF NOT EXISTS public.discovery_candidates (
    canonical_url TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL,
    license TEXT NOT NULL DEFAULT 'unknown',
    maintenance TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL,
    stars INTEGER NOT NULL DEFAULT 0,
    discovered_at TEXT NOT NULL,
    evidence TEXT NOT NULL,
    review_state TEXT NOT NULL DEFAULT 'pending',
    review_notes TEXT NOT NULL DEFAULT '',
    review_updated_at TEXT
);

CREATE TABLE IF NOT EXISTS public.workflow_instances (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL DEFAULT 'core',
    template_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public.workflow_steps (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    department TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'blocked',
    output TEXT NOT NULL DEFAULT '',
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE (workflow_id, sequence_no),
    UNIQUE (task_id),
    FOREIGN KEY (workflow_id) REFERENCES public.workflow_instances(id),
    FOREIGN KEY (task_id) REFERENCES public.tasks(id)
);

-- Preserve the application's named indexes, including indexes added by legacy upgrades.
CREATE INDEX IF NOT EXISTS idx_provider_catalog_category ON public.provider_catalog_entries(category, name);
CREATE INDEX IF NOT EXISTS idx_research_sources_captured ON public.research_sources(captured_at);
CREATE INDEX IF NOT EXISTS idx_business_integrations_scope ON public.business_integration_credentials(business_id, provider);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status_created ON public.agent_runs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_run_events_run_id ON public.agent_run_events(run_id, id);
CREATE INDEX IF NOT EXISTS idx_agent_run_steps_run_id ON public.agent_run_steps(run_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_brain_experiences_department ON public.brain_experiences(department, created_at);
CREATE INDEX IF NOT EXISTS idx_brain_memories_status_department ON public.brain_memories(status, department, created_at);
CREATE INDEX IF NOT EXISTS idx_business_records_type_created ON public.business_records(record_type, created_at);
CREATE INDEX IF NOT EXISTS idx_investor_contacts_stage ON public.investor_contacts(stage, created_at);
CREATE INDEX IF NOT EXISTS idx_code_assets_created ON public.code_assets(created_at);
CREATE INDEX IF NOT EXISTS idx_license_offers_created ON public.license_offers(created_at);
CREATE INDEX IF NOT EXISTS idx_department_messages_inbox ON public.department_messages(business_id, recipient_department, status, created_at);
CREATE INDEX IF NOT EXISTS idx_department_messages_thread ON public.department_messages(business_id, created_at);
CREATE INDEX IF NOT EXISTS idx_department_delegations_scope ON public.department_delegations(business_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_business_records_scope ON public.business_records(business_id, record_type, created_at);
CREATE INDEX IF NOT EXISTS idx_investor_contacts_scope ON public.investor_contacts(business_id, created_at);
CREATE INDEX IF NOT EXISTS idx_research_sources_scope ON public.research_sources(business_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_approvals_scope ON public.approvals(business_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_brain_memories_business_status ON public.brain_memories(business_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_brain_experiences_business ON public.brain_experiences(business_id, created_at);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow ON public.workflow_steps(workflow_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_workflow_instances_scope ON public.workflow_instances(business_id, created_at);

-- Supabase has an RLS auto-enable event trigger. Explicitly enable RLS as a
-- defence-in-depth baseline; no client-facing policies or grants are added.
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.discovery_scans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.provider_catalog_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.provider_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_integration_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_run_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_run_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brain_experiences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brain_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.owner_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.investor_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.code_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.license_offers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.department_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.department_delegations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.discovery_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workflow_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workflow_steps ENABLE ROW LEVEL SECURITY;
