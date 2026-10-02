import { fixtureEvents } from '@/test/fixture'
import { cueDelay } from './replay'
import { buildTimeline, sumSegments } from './timeline'
import type { PipelineEvent } from './types'

const events = fixtureEvents()

describe('buildTimeline', () => {
  const t = buildTimeline(events, 'answering')

  it('places every stage on one axis, in order, without overlap', () => {
    for (let i = 1; i < t.segments.length; i++) expect(t.segments[i].start).toBeGreaterThanOrEqual(t.segments[i - 1].end - 1e-6)
    expect(Object.keys(t.spans)).toEqual(['retrieve', 'draft', 'decompose', 'verify'])
  })

  it('draws the waits announced by llm_waiting events to scale', () => {
    expect(sumSegments(t.segments, 'wait', 'verify')).toBeCloseTo(155, 0)
    expect(sumSegments(t.segments, 'wait', 'decompose')).toBeCloseTo(2, 0)
    expect(t.segments.some((s) => s.approximate)).toBe(false)
  })

  it('places waits from the usage totals when a run has no llm_waiting events', () => {
    const old = buildTimeline(events.filter((e) => e.type !== 'llm_waiting'), 'answering')
    expect(sumSegments(old.segments, 'wait', 'verify')).toBeCloseTo(155, 0)
    expect(old.segments.filter((s) => s.kind === 'wait').every((s) => s.approximate)).toBe(true)
  })
})

describe('replay pacing', () => {
  const offsets = buildTimeline(events, 'answering').offsets
  const verified = events.filter((e) => e.type === 'claim_verified')

  it('stays within bounds', () => {
    const delays = events.map((_, i) => cueDelay(offsets, events, i))
    expect(delays[0]).toBe(0)
    expect(Math.max(...delays)).toBeLessThan(6000)
  })

  it('gives a long real gap more time than a short one', () => {
    const [a, b] = verified
    const seq = (gap: number) => cueDelay([0, 1, 1 + gap], [a, b, b] as PipelineEvent[], 2)
    expect(seq(30)).toBeGreaterThan(seq(1))
    expect(seq(300)).toBe(seq(40)) // compressed: very long waits are capped
  })

  it('leaves time to read a stage output before the next cue', () => {
    const draft = events.findIndex((e) => e.type === 'draft_written')
    expect(cueDelay(offsets, events, draft + 1)).toBeGreaterThan(3000)
  })
})

describe('indexing timeline', () => {
  const at = (s: number) => new Date(Date.UTC(2026, 9, 2, 8, 0, s)).toISOString()
  const base = { run_id: 'r', pipeline: 'indexing' as const }
  const indexing = [
    { ...base, time: at(0), type: 'run_started', config: {}, inputs: {} },
    { ...base, time: at(1), type: 'documents_loaded', documents: [], seconds: 1 },
    { ...base, time: at(2), type: 'documents_cleaned', documents: [], seconds: 1 },
    { ...base, time: at(3), type: 'chunks_built', chunks: [], seconds: 1 },
  ] as unknown as PipelineEvent[]

  it('places the cleaning step between loading and cutting', () => {
    expect(Object.keys(buildTimeline(indexing, 'indexing').spans)).toEqual(['load', 'clean', 'chunk'])
  })

  it('still reads runs recorded before the cleaning step', () => {
    const old = indexing.filter((e) => e.type !== 'documents_cleaned')
    expect(Object.keys(buildTimeline(old, 'indexing').spans)).toEqual(['load', 'chunk'])
  })
})
