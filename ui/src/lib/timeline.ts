// One time axis for the whole run: every stage, work and waiting alike, in real seconds.

import type { EventOf, PipelineEvent } from './types'

export interface Segment {
  stage: string
  kind: 'work' | 'wait'
  start: number
  end: number
  /** claim position for verification segments */
  position?: number
  /** a wait placed from the usage totals, not from an llm_waiting event (older runs) */
  approximate?: boolean
}

export interface Timeline {
  segments: Segment[]
  total: number
  /** seconds since the start, for each event of the list given (same order) */
  offsets: number[]
  /** where each stage starts and ends on the axis */
  spans: Record<string, { start: number; end: number }>
}

const time = (e: PipelineEvent) => Date.parse(e.time) / 1000

const ANSWERING_STAGE: Partial<Record<PipelineEvent['type'], string>> = {
  passages_retrieved: 'retrieve',
  draft_written: 'draft',
  claims_extracted: 'decompose',
  claim_verified: 'verify',
}

const INDEXING_STAGE: Partial<Record<PipelineEvent['type'], string>> = {
  documents_loaded: 'load',
  documents_cleaned: 'clean',
  chunks_built: 'chunk',
  chunks_embedded: 'embed',
  chunks_stored: 'store',
}

export function buildTimeline(events: PipelineEvent[], pipeline: 'answering' | 'indexing'): Timeline {
  const stageOf = pipeline === 'answering' ? ANSWERING_STAGE : INDEXING_STAGE
  const origin = events.find((e) => e.type === (pipeline === 'answering' ? 'question_started' : 'run_started'))
  const t0 = origin ? time(origin) : events.length ? time(events[0]) : 0
  const offsets = events.map((e) => Math.max(0, time(e) - t0))
  const segments: Segment[] = []
  const spans: Timeline['spans'] = {}

  let windowStart = 0
  let waits: { start: number; seconds: number }[] = []
  events.forEach((e, i) => {
    const at = offsets[i]
    if (e.type === 'llm_waiting') {
      waits.push({ start: at, seconds: e.seconds })
      return
    }
    const stage = stageOf[e.type]
    if (!stage) return
    const end = at
    const position = e.type === 'claim_verified' ? e.position : undefined
    let placed = waits.map((w) => ({ start: w.start, end: Math.min(w.start + w.seconds, end), approximate: false }))
    const usage = 'usage' in e ? (e as EventOf<'claim_verified'>).usage : undefined
    if (!placed.length && usage && usage.waited_seconds > 0) {
      // No llm_waiting events (runs recorded before they existed): the waits sit before the last attempt.
      const lastCall = Math.max(0, (usage.seconds - usage.waited_seconds) / (usage.retries + 1))
      const waitEnd = Math.max(windowStart, end - lastCall)
      placed = [{ start: Math.max(windowStart, waitEnd - usage.waited_seconds), end: waitEnd, approximate: true }]
    }
    let cursor = windowStart
    for (const w of placed) {
      if (w.start > cursor) segments.push({ stage, kind: 'work', start: cursor, end: w.start, position })
      if (w.end > w.start) segments.push({ stage, kind: 'wait', start: w.start, end: w.end, position, approximate: w.approximate || undefined })
      cursor = Math.max(cursor, w.end)
    }
    if (end > cursor || !placed.length) segments.push({ stage, kind: 'work', start: cursor, end: Math.max(end, cursor), position })
    spans[stage] = { start: spans[stage]?.start ?? windowStart, end }
    windowStart = end
    waits = []
  })

  const finished = events.find((e) => e.type === 'question_finished' || e.type === 'run_finished')
  const total = Math.max(finished && 'seconds' in finished ? Math.min(finished.seconds, offsets[offsets.length - 1] || finished.seconds) : 0, windowStart, ...offsets)
  return { segments, total, offsets, spans }
}

export function sumSegments(segments: Segment[], kind: Segment['kind'], stage?: string): number {
  return segments.filter((s) => s.kind === kind && (!stage || s.stage === stage)).reduce((sum, s) => sum + (s.end - s.start), 0)
}
