// Mirrors src/claimverify/contracts.py and events.py (as the API serializes them).

export const VERDICT_LABELS = ['supported', 'contradicted', 'contested', 'unverifiable', 'error'] as const
export type VerdictLabel = (typeof VERDICT_LABELS)[number]

export interface Passage {
  filename: string
  source_type: string
  chunk_index: number
  text: string
  score: number
}

export interface Chunk {
  chunk_id: string
  doc_id: string
  filename: string
  source_type: string
  chunk_index: number
  text: string
  /** size in the embedding model's tokens; absent in runs chunked by words */
  tokens?: number | null
}

export interface Draft {
  question: string
  text: string
  passages: Passage[]
}

export interface Claim {
  id: string
  claim: string
  cited_source: string | null
}

export interface Verdict {
  claim_id: string
  claim: string
  verdict: VerdictLabel
  justification: string
  supporting_sources: string[]
  contradicting_sources: string[]
  original_cited_source: string | null
  verifier: string
  evidence: Passage[]
}

export interface Usage {
  calls: number
  tokens_in: number
  tokens_out: number
  retries: number
  waited_seconds: number
  seconds: number
}

interface EventBase {
  run_id: string
  pipeline: 'indexing' | 'answering'
  time: string
}

export interface DocumentSummary {
  doc_id: string
  filename: string
  source_type: string
  characters: number
}

export interface CleaningSummary {
  filename: string
  characters_before: number
  characters_after: number
  /** rule -> number of repairs (page_numbers, nfkc, hyphens_joined, hyphens_kept) */
  changes: Record<string, number>
}

export type PipelineEvent = EventBase &
  (
    | { type: 'run_started'; config: Config; inputs: Record<string, unknown> }
    | { type: 'run_finished'; summary: Record<string, unknown>; seconds: number }
    | { type: 'documents_loaded'; documents: DocumentSummary[]; seconds: number }
    | { type: 'documents_cleaned'; documents: CleaningSummary[]; seconds: number }
    | { type: 'chunks_built'; chunks: Chunk[]; seconds: number }
    | { type: 'chunks_embedded'; count: number; dimension: number; seconds: number }
    | { type: 'chunks_stored'; count: number; seconds: number }
    | { type: 'question_started'; question_index: number; question: string }
    | { type: 'passages_retrieved'; question_index: number; passages: Passage[]; seconds: number; usage: Usage }
    | { type: 'draft_written'; question_index: number; draft: Draft; seconds: number; usage: Usage }
    | { type: 'claims_extracted'; question_index: number; claims: Claim[]; seconds: number; usage: Usage }
    | {
        type: 'claim_verified'
        question_index: number
        position: number
        total: number
        verdict: Verdict
        usage: Usage
      }
    | {
        type: 'llm_waiting'
        question_index: number | null
        role: string
        model: string
        seconds: number
        attempt: number
        reason: 'rate_limit' | 'server_error' | 'connection' | string
      }
    | { type: 'question_finished'; question_index: number; verdict_counts: Record<string, number>; seconds: number }
  )

export type EventOf<T extends PipelineEvent['type']> = Extract<PipelineEvent, { type: T }>

export interface LLMStageConfig {
  type: string
  provider: string
  model: string
}

export interface Config {
  providers: Record<string, { base_url: string; api_key_env: string; max_retries: number; max_wait_seconds: number }>
  embedding: { type: string; model: string; device: string }
  indexing: {
    loader: { type: string }
    /** absent in runs recorded before the cleaning step */
    cleaner?: { type: string }
    chunker: { type: string; chunk_size: number; overlap_ratio: number }
  }
  answering: {
    retriever: { type: string; top_k_per_doc: number }
    drafter: LLMStageConfig
    decomposer: LLMStageConfig
    verifier: { type: string; retriever: { type: string; top_k_per_doc: number }; judge: LLMStageConfig }
  }
}

export type RunStatus = 'finished' | 'incomplete' | 'running' | 'failed' | 'unreadable'

export interface RunSummary {
  run_id: string
  source: 'recorded' | 'fixture'
  pipeline: 'indexing' | 'answering'
  status: RunStatus
  started_at?: string | null
  seconds?: number
  config_file?: string | null
  usage?: { calls: number; tokens_in: number; tokens_out: number; retries: number; waited_seconds: number }
  event_count?: number
  questions?: string[]
  verdict_counts?: Partial<Record<VerdictLabel, number>>
  claims?: number
  corpus_dir?: string | null
  documents?: number | null
  chunks?: number | null
  error?: { kind: string; message: string } | string | null
}

export interface RunDetail {
  summary: RunSummary
  events: PipelineEvent[]
  report: Record<string, unknown> | null
}

export interface LiveInfo {
  enabled: boolean
  configs?: { file: string; models?: Record<string, string>; missing_keys?: string[]; error?: string }[]
  database_configured?: boolean
  estimate?: { tokens_per_question: number; basis_runs: number; daily_limit_note: string }
  running?: string | null
}
