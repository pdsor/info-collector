-- 页面归档 PostgreSQL 第一阶段表结构草案。
-- 大图片、附件和截图等二进制资产不入库，只保存元数据、哈希和 storage_uri。

create extension if not exists pgcrypto;

create table if not exists archive_pages (
    id uuid primary key default gen_random_uuid(),
    source_url text not null,
    entry_url text,
    final_url text,
    domain text not null,
    platform text,
    subject text,
    title text,
    source_name text,
    publish_time timestamp with time zone,
    author text,
    channel text,
    breadcrumb jsonb not null default '[]'::jsonb,
    html text,
    markdown text,
    metadata jsonb not null default '{}'::jsonb,
    content_hash text not null,
    archive_status text not null default 'success',
    contains_ocr boolean not null default false,
    contains_table boolean not null default false,
    requires_structuring boolean not null default false,
    manual_review_required boolean not null default false,
    fetched_at timestamp with time zone not null,
    created_at timestamp with time zone not null default now(),
    updated_at timestamp with time zone not null default now()
);

create table if not exists archive_blocks (
    id uuid primary key default gen_random_uuid(),
    page_id uuid not null references archive_pages(id) on delete cascade,
    block_order integer not null,
    block_type text not null,
    parent_block_id uuid references archive_blocks(id) on delete set null,
    text text,
    html text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamp with time zone not null default now()
);

create table if not exists archive_assets (
    id uuid primary key default gen_random_uuid(),
    page_id uuid not null references archive_pages(id) on delete cascade,
    block_id uuid references archive_blocks(id) on delete set null,
    asset_type text not null,
    source_url text,
    storage_uri text not null,
    file_name text,
    extension text,
    mime_type text,
    size_bytes bigint,
    content_hash text,
    downloaded boolean not null default false,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamp with time zone not null default now()
);

create table if not exists ocr_results (
    id uuid primary key default gen_random_uuid(),
    page_id uuid not null references archive_pages(id) on delete cascade,
    asset_id uuid references archive_assets(id) on delete set null,
    block_id uuid references archive_blocks(id) on delete set null,
    engine text,
    status text not null default 'success',
    ocr_text text,
    structured_data jsonb not null default '{}'::jsonb,
    elapsed_seconds numeric,
    error text,
    manual_review_required boolean not null default false,
    created_at timestamp with time zone not null default now()
);

create table if not exists structured_records (
    id uuid primary key default gen_random_uuid(),
    page_id uuid not null references archive_pages(id) on delete cascade,
    source_block_id uuid references archive_blocks(id) on delete set null,
    record_type text not null,
    data jsonb not null default '{}'::jsonb,
    raw_columns jsonb not null default '{}'::jsonb,
    confidence numeric,
    status text not null default 'success',
    created_at timestamp with time zone not null default now()
);

create unique index if not exists archive_pages_source_url_hash_idx on archive_pages (content_hash);
create index if not exists archive_pages_domain_idx on archive_pages (domain);
create index if not exists archive_pages_platform_subject_idx on archive_pages (platform, subject);
create index if not exists archive_pages_publish_time_idx on archive_pages (publish_time);
create index if not exists archive_blocks_page_order_idx on archive_blocks (page_id, block_order);
create index if not exists archive_blocks_type_idx on archive_blocks (block_type);
create index if not exists archive_assets_page_idx on archive_assets (page_id);
create index if not exists ocr_results_page_idx on ocr_results (page_id);
create index if not exists structured_records_page_type_idx on structured_records (page_id, record_type);
create index if not exists structured_records_data_gin_idx on structured_records using gin (data);
