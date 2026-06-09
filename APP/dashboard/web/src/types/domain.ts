// 业务领域类型 — 与 APP/dashboard/apis/* 返回结构对齐

export type LifecycleStatus = 'ACTIVE' | 'PAUSED' | 'DEPRECATED' | 'TESTING';

export interface SourceItem {
  id: string;
  name: string;
  domain: string;
  type: 'api' | 'website' | string;
  category: string;
  trust_score: number;
  update_frequency: number;
  anti_crawl_level: string;
  parser_strategy: string;
  auth_required: boolean;
  language: string;
  tags: string[];
  enabled: boolean;
  lifecycle_status: LifecycleStatus | string;
  rule_path: string;
  updated_at?: string;
}

export interface SourceSummary {
  total: number;
  active: number;
  paused: number;
  avg_trust_score: number;
}

// 规则列表项 — 由 engine_cli list-rules 输出，字段较灵活
export interface RuleItem {
  path: string;
  name?: string;
  platform?: string;
  subject?: string;
  enabled?: boolean;
  status?: string;
  rule_id?: string;
  source_id?: string;
  version?: number;
  last_run?: string;
}

export interface RuleDetail {
  yaml: string;
  path?: string;
}

export interface OcrSummary {
  enabled: boolean;
  plugin?: string;
  images_found?: number;
  images_downloaded?: number;
  ocr_success?: number;
  manual_review_required?: number;
}

export interface RulePreviewResult {
  success: boolean;
  status?: string;
  total_collected?: number;
  preview_count?: number;
  items?: Record<string, unknown>[];
  ocr_summary?: OcrSummary;
  error?: string;
}

export interface HealthSelectorResult {
  hits: number;
  sample?: string[];
  error?: string;
}

export interface HealthCheckReport {
  health_score: number;
  working_selectors: number;
  total_selectors: number;
  dom_structure_hash: string;
  selectors: Record<string, HealthSelectorResult>;
  dom_baseline_hash?: string | null;
  baseline_set_at?: string | null;
  dom_drifted?: boolean;
}

export type TaskNgStatus =
  | 'PENDING'
  | 'QUEUED'
  | 'RUNNING'
  | 'SUCCESS'
  | 'PARTIAL_SUCCESS'
  | 'FAILED'
  | 'RETRYING'
  | 'CANCELLED';

export interface TaskHistoryItem {
  id: number;
  task_name: string;
  status: string;
  ng_status?: TaskNgStatus | string;
  message?: string;
  new_count: number;
  duration: number;
  trigger_type: string;
  rule_path?: string | null;
  created_at: string;
  collection_run?: CollectionRun | null;
}

export interface CollectionRun {
  id: string;
  rule_name: string;
  rule_path: string;
  subject: string;
  platform: string;
  status: string;
  total_collected: number;
  saved_count: number;
  dedup_filtered: number;
  output_path?: string;
  started_at?: string;
  finished_at?: string;
  duration_seconds?: number;
}

export interface CollectionRunItem {
  raw_id?: string;
  url?: string;
  title?: string;
  content_hash?: string;
  filter_reason?: string;
  matched_existing_id?: string;
  matched_existing_item?: {
    id?: string;
    title?: string;
    url?: string;
    content_hash?: string;
    collected_at?: string;
  };
  archive?: {
    page_id?: string;
    title?: string;
    content_hash?: string;
    contains_ocr?: boolean;
    fetched_at?: string;
    body_text?: string;
    ocr_text?: string;
    blocks?: Array<{
      block_order?: number;
      block_type?: string;
      text?: string;
    }>;
    ocr_results?: Array<{
      status?: string;
      ocr_text?: string;
      elapsed_seconds?: number;
      manual_review_required?: boolean;
    }>;
  };
  data?: Record<string, unknown>;
  governance?: Record<string, unknown>;
  collected_at?: string;
}

export interface TaskItemsResponse {
  run: CollectionRun | null;
  items: {
    raw: CollectionRunItem[];
    deduped: CollectionRunItem[];
    filtered: CollectionRunItem[];
  };
}

export type TaskEventType =
  | 'start'
  | 'status'
  | 'progress'
  | 'error'
  | 'skip'
  | 'complete'
  | 'summary'
  | 'done'
  | 'heartbeat';

export interface TaskStreamEvent {
  type: TaskEventType;
  task_id?: number;
  status?: string;
  rule?: string;
  msg?: string;
  phase?: string;
  current?: number;
  total?: number;
  message?: string;
  detail?: string;
  reason?: string;
  new_count?: number;
  duration?: number;
  success?: boolean;
  total_new?: number;
  total_skip?: number;
  total_error?: number;
}

export interface GovernanceSummary {
  file_count: number;
  total_items: number;
  injection_risk_count: number;
  avg_field_completeness: number;
  avg_quality_score: number;
}

export interface GovernanceRecord {
  subject: string;
  platform: string;
  source_file: string;
  item_count: number;
  duplicate_count: number;
  injection_risk_count: number;
  field_completeness: number;
  quality_score: number;
  status: string;
  collected_at: string;
}

export interface ArchivePage {
  content_hash: string;
  title: string;
  source_url: string;
  domain: string;
  platform: string;
  subject: string;
  fetched_at: string;
  contains_ocr: boolean;
  contains_table: boolean;
  requires_structuring: boolean;
  block_count: number;
  ocr_block_count: number;
  image_block_count: number;
}

export type ArchiveBlockType = 'heading' | 'paragraph' | 'image' | 'ocr' | 'table' | 'attachment';

export interface ArchiveBlock {
  id?: number | string;
  block_order: number;
  block_type: ArchiveBlockType | string;
  level?: number;
  text?: string;
  ocr_text?: string;
  source_url?: string;
  meta?: Record<string, unknown>;
}

export interface ArchiveStructuredRecord {
  record_type: string;
  data: Record<string, unknown>;
}

export interface ArchiveDetail {
  meta: Record<string, unknown>;
  blocks: ArchiveBlock[];
  assets?: Record<string, unknown>[];
  structured_records: ArchiveStructuredRecord[];
}
