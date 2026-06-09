-- 普通采集结果 PostgreSQL 主库表结构。
-- 页面归档继续使用 archive_pages / archive_blocks / archive_assets / ocr_results / structured_records。

create extension if not exists pgcrypto;

create table if not exists collection_runs (
    id uuid primary key default gen_random_uuid(),
    rule_name text not null,
    rule_path text not null,
    subject text not null,
    platform text not null,
    status text not null,
    total_collected integer not null default 0,
    saved_count integer not null default 0,
    dedup_filtered integer not null default 0,
    output_path text,
    started_at timestamp with time zone not null,
    finished_at timestamp with time zone not null,
    duration_seconds numeric,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamp with time zone not null default now()
);

create table if not exists collection_items (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references collection_runs(id) on delete cascade,
    rule_name text not null,
    rule_path text not null,
    subject text not null,
    platform text not null,
    raw_id text,
    url text,
    title text,
    content_hash text,
    field_completeness numeric,
    injection_risk boolean not null default false,
    data jsonb not null default '{}'::jsonb,
    governance jsonb not null default '{}'::jsonb,
    collected_at timestamp with time zone not null,
    created_at timestamp with time zone not null default now()
);

create table if not exists collection_run_items (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references collection_runs(id) on delete cascade,
    rule_name text not null,
    rule_path text not null,
    subject text not null,
    platform text not null,
    item_stage text not null,
    raw_id text,
    url text,
    title text,
    content_hash text,
    filter_reason text,
    matched_existing_id text,
    data jsonb not null default '{}'::jsonb,
    governance jsonb not null default '{}'::jsonb,
    collected_at timestamp with time zone not null,
    created_at timestamp with time zone not null default now()
);

create table if not exists collection_governance_records (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references collection_runs(id) on delete cascade,
    subject text not null,
    platform text not null,
    item_count integer not null default 0,
    duplicate_count integer not null default 0,
    injection_risk_count integer not null default 0,
    field_completeness numeric not null default 1,
    quality_score numeric not null default 1,
    status text not null,
    summary jsonb not null default '{}'::jsonb,
    created_at timestamp with time zone not null default now()
);

create index if not exists collection_items_run_idx on collection_items (run_id);
create index if not exists collection_items_subject_platform_idx on collection_items (subject, platform);
create index if not exists collection_items_url_idx on collection_items (url);
create index if not exists collection_items_content_hash_idx on collection_items (content_hash);
create index if not exists collection_items_data_gin_idx on collection_items using gin (data);
create index if not exists collection_run_items_run_stage_idx on collection_run_items (run_id, item_stage);
create index if not exists collection_run_items_subject_platform_idx on collection_run_items (subject, platform);
create index if not exists collection_run_items_url_idx on collection_run_items (url);
create index if not exists collection_run_items_data_gin_idx on collection_run_items using gin (data);
create index if not exists collection_governance_subject_platform_idx on collection_governance_records (subject, platform);
