-- PipelineHealer PostgreSQL bootstrap schema
-- Applies durable storage tables used by PostgresStorage adapter.

CREATE TABLE IF NOT EXISTS ph_activities (
    id TEXT PRIMARY KEY,
    repository_name TEXT NOT NULL,
    status TEXT NOT NULL,
    failure_type TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ph_activities_created_at ON ph_activities (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ph_activities_repository ON ph_activities (repository_name);
CREATE INDEX IF NOT EXISTS idx_ph_activities_status ON ph_activities (status);
CREATE INDEX IF NOT EXISTS idx_ph_activities_failure_type ON ph_activities (failure_type);

CREATE TABLE IF NOT EXISTS ph_runtime_settings (
    id TEXT PRIMARY KEY,
    updated_at TIMESTAMPTZ NOT NULL,
    settings JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS ph_admin_settings_audit (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ph_admin_settings_audit_timestamp
    ON ph_admin_settings_audit (timestamp DESC);

CREATE TABLE IF NOT EXISTS ph_learning_queue (
    id TEXT PRIMARY KEY,
    status TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ph_learning_queue_updated_at ON ph_learning_queue (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ph_learning_queue_status ON ph_learning_queue (status);
