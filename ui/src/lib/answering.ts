// Turns the events of an answering run into what the run view shows.
// Pure functions: replay calls them on the first n events, live mode on the events so far.

import type { Claim, Config, Draft, EventOf, Passage, PipelineEvent, Usage, Verdict } from './types'

export type StageId = 'retrieve' | 'draft' | 'decompose' | 'verify' | 'done'
export type StageStatus = 'pending' | 'active' | 'done' | 'failed'

export const STAGES: { id: StageId; label: string; role?: string }[] = [
  { id: 'retrieve', label: 'Retrieve' },
  { id: 'draft', label: 'Draft', role: 'draft' },
  { id: 'decompose', label: 'Decompose', role: 'decompose' },
  { id: 'verify', label: 'Verify', role: 'verify' },
  { id: 'done', label: 'Done' },
]

const STAGE_OF_EVENT: Partial<Record<PipelineEvent['type'], StageId>> = {
  passages_retrieved: 'retrieve',
  draft_written: 'draft',
  claims_extracted: 'decompose',
  claim_verified: 'verify',
  question_finished: 'done',
}

export interface StageState {
  id: StageId
  label: string
  status: StageStatus
  seconds: number
  usage: Usage
}

export interface VerdictEntry {
  verdict: Verdict
  position: number
  total: number
  usage: Usage
}

export interface WaitNotice {
  role: string
  model: string
  seconds: number
  attempt: number
  reason: string
  /** seconds since the question started */
  at: number
}

export interface AnsweringState {
  config?: Config
  configFile?: string
  questions: string[]
  questionIndex: number
  question?: string
  passages?: Passage[]
  draft?: Draft
  claims?: Claim[]
  verdicts: Record<string, VerdictEntry>
  waits: WaitNotice[]
  /** a wait announced and not yet followed by the stage's result */
  pendingWait?: WaitNotice
  stages: StageState[]
  /** the stage that is running (or the last one reached) */
  current: StageId | null
  finished: boolean
  questionSeconds?: number
}

export const ZERO_USAGE: Usage = { calls: 0, tokens_in: 0, tokens_out: 0, retries: 0, waited_seconds: 0, seconds: 0 }

export function addUsage(a: Usage, b: Usage): Usage {
  return {
    calls: a.calls + b.calls,
    tokens_in: a.tokens_in + b.tokens_in,
    tokens_out: a.tokens_out + b.tokens_out,
    retries: a.retries + b.retries,
    waited_seconds: a.waited_seconds + b.waited_seconds,
    seconds: a.seconds + b.seconds,
  }
}

const time = (e: PipelineEvent) => Date.parse(e.time) / 1000

/** Events that belong to one question (plus the run-level ones). */
export function questionEvents(events: PipelineEvent[], questionIndex: number): PipelineEvent[] {
  return events.filter((e) => !('question_index' in e) || e.question_index === questionIndex || e.question_index == null)
}

export function buildAnsweringState(events: PipelineEvent[], questionIndex = 1): AnsweringState {
  const started = events.find((e): e is EventOf<'run_started'> => e.type === 'run_started')
  const state: AnsweringState = {
    config: started?.config,
    configFile: started?.inputs.config_file as string | undefined,
    questions: (started?.inputs.questions as string[] | undefined) ?? [],
    questionIndex,
    verdicts: {},
    waits: [],
    stages: STAGES.map((s) => ({ id: s.id, label: s.label, status: 'pending', seconds: 0, usage: ZERO_USAGE })),
    current: null,
    finished: false,
  }
  const stage = (id: StageId) => state.stages.find((s) => s.id === id)!
  let t0: number | undefined

  for (const e of questionEvents(events, questionIndex)) {
    switch (e.type) {
      case 'question_started':
        state.question = e.question
        t0 = time(e)
        state.current = 'retrieve'
        stage('retrieve').status = 'active'
        break
      case 'passages_retrieved':
        state.passages = e.passages
        break
      case 'draft_written':
        state.draft = e.draft
        break
      case 'claims_extracted':
        state.claims = e.claims
        break
      case 'claim_verified':
        state.verdicts[e.verdict.claim_id] = { verdict: e.verdict, position: e.position, total: e.total, usage: e.usage }
        break
      case 'llm_waiting': {
        const notice = { role: e.role, model: e.model, seconds: e.seconds, attempt: e.attempt, reason: e.reason, at: time(e) - (t0 ?? time(e)) }
        state.waits.push(notice)
        state.pendingWait = notice
        break
      }
      case 'question_finished':
        state.questionSeconds = e.seconds
        state.finished = true
        break
    }
    const id = STAGE_OF_EVENT[e.type]
    if (!id) continue
    state.pendingWait = undefined
    const s = stage(id)
    if ('usage' in e) s.usage = addUsage(s.usage, e.usage)
    if (id === 'verify') {
      const ev = e as EventOf<'claim_verified'>
      s.seconds = s.seconds + (ev.usage.seconds || 0)
      s.status = ev.position >= ev.total ? 'done' : 'active'
    } else {
      s.seconds = 'seconds' in e ? e.seconds : 0
      s.status = 'done'
    }
    // the next stage starts as soon as this one is done
    const order = STAGES.map((x) => x.id)
    if (s.status === 'done' && id !== 'done') {
      let next = order[order.indexOf(id) + 1]
      // no claims: nothing to verify
      if (next === 'verify' && state.claims?.length === 0) {
        stage('verify').status = 'done'
        next = 'done'
      }
      if (stage(next).status === 'pending') stage(next).status = 'active'
      state.current = next
    } else {
      state.current = id
    }
  }
  // verification time: from the claims to the last verdict (includes retrieval of each claim)
  const decomposed = events.find((e) => e.type === 'claims_extracted' && e.question_index === questionIndex)
  const lastVerdict = [...events].reverse().find((e) => e.type === 'claim_verified' && e.question_index === questionIndex)
  if (decomposed && lastVerdict) stage('verify').seconds = time(lastVerdict) - time(decomposed)
  if (state.finished) {
    stage('done').status = 'done'
    state.current = 'done'
  }
  return state
}

/** Every source document seen in the run, most relevant first (by the draft retrieval's best score). */
export function documentsOf(state: AnsweringState): string[] {
  const best = new Map<string, number>()
  const note = (p: Passage) => best.set(p.filename, Math.max(best.get(p.filename) ?? -1, p.score))
  state.passages?.forEach(note)
  Object.values(state.verdicts).forEach((v) => v.verdict.evidence.forEach(note))
  return [...best.entries()].sort((a, b) => b[1] - a[1]).map(([f]) => f)
}

export type Stance = 'supports' | 'contradicts' | 'silent' | 'not_read'

/** What one source said about one claim, according to the judge. */
export function stanceOf(verdict: Verdict, filename: string): Stance {
  if (verdict.supporting_sources.includes(filename)) return 'supports'
  if (verdict.contradicting_sources.includes(filename)) return 'contradicts'
  if (verdict.evidence.some((p) => p.filename === filename)) return 'silent'
  return 'not_read'
}

/** "file.pdf | chunk #3" -> { filename: "file.pdf", chunk: 3 } */
export function parseCitation(cited: string | null | undefined): { filename: string; chunk?: number } | null {
  if (!cited) return null
  const match = cited.match(/^\s*(.+?)\s*(?:\|\s*chunk\s*#?\s*(\d+))?\s*$/i)
  if (!match) return null
  return { filename: match[1], chunk: match[2] != null ? Number(match[2]) : undefined }
}

/**
 * The draft cited a source the judge did not use as support.
 * Worth flagging: the verifier re-searched the whole corpus instead of trusting the citation.
 */
export function citationMismatch(verdict: Verdict): string | null {
  const cited = parseCitation(verdict.original_cited_source)
  if (!cited || verdict.verdict === 'error' || verdict.verdict === 'unverifiable') return null
  const judged = [...verdict.supporting_sources, ...verdict.contradicting_sources]
  if (judged.includes(cited.filename)) return null
  return cited.filename
}

export function totalUsage(state: AnsweringState): Usage {
  return state.stages.reduce((sum, s) => addUsage(sum, s.usage), ZERO_USAGE)
}

/** Split a draft into text and citation chips: 【file | chunk #n】 or [file]. */
export type DraftPiece = { kind: 'text'; text: string } | { kind: 'cite'; filename: string; chunk?: number; raw: string }

export function splitCitations(text: string): DraftPiece[] {
  const pieces: DraftPiece[] = []
  const pattern = /【([^】]+)】|\[([^\]\n]+\.(?:pdf|md|txt|html))(?:\s*\|\s*chunk\s*#?\s*(\d+))?\]/gi
  let last = 0
  for (const m of text.matchAll(pattern)) {
    if (m.index! > last) pieces.push({ kind: 'text', text: text.slice(last, m.index) })
    const cite = m[1] ? parseCitation(m[1]) : { filename: m[2], chunk: m[3] != null ? Number(m[3]) : undefined }
    if (cite) pieces.push({ kind: 'cite', filename: cite.filename, chunk: cite.chunk, raw: m[0] })
    last = m.index! + m[0].length
  }
  if (last < text.length) pieces.push({ kind: 'text', text: text.slice(last) })
  return pieces
}

/** Model per role, from the run's config. */
export function modelsByRole(config?: Config): Record<string, string> {
  if (!config) return {}
  const a = config.answering
  return { draft: a.drafter.model, decompose: a.decomposer.model, verify: a.verifier.judge.model }
}
