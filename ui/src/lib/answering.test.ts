import { fixtureEvents } from '@/test/fixture'
import { buildAnsweringState, citationMismatch, documentsOf, parseCitation, splitCitations, stanceOf } from './answering'
import type { PipelineEvent } from './types'

const events = fixtureEvents()
const upTo = (type: PipelineEvent['type']) => events.slice(0, events.findIndex((e) => e.type === type) + 1)

describe('buildAnsweringState', () => {
  it('starts empty before the question', () => {
    const state = buildAnsweringState(events.slice(0, 1))
    expect(state.question).toBeUndefined()
    expect(state.current).toBeNull()
    expect(state.stages.every((s) => s.status === 'pending')).toBe(true)
  })

  it('marks each stage done as its event arrives, and the next one active', () => {
    const state = buildAnsweringState(upTo('draft_written'))
    const status = Object.fromEntries(state.stages.map((s) => [s.id, s.status]))
    expect(status).toEqual({ retrieve: 'done', draft: 'done', decompose: 'active', verify: 'pending', done: 'pending' })
    expect(state.passages).toHaveLength(8)
    expect(state.draft?.text).toContain('【')
  })

  it('fills verdicts one by one and finishes', () => {
    const partial = buildAnsweringState(events.slice(0, events.findIndex((e) => e.type === 'claim_verified') + 1))
    expect(Object.keys(partial.verdicts)).toEqual(['c1'])
    expect(partial.stages.find((s) => s.id === 'verify')?.status).toBe('active')

    const full = buildAnsweringState(events)
    expect(full.finished).toBe(true)
    expect(full.current).toBe('done')
    expect(Object.values(full.verdicts).map((v) => v.verdict.verdict)).toEqual([
      'supported', 'contested', 'contradicted', 'supported', 'unverifiable', 'error',
    ])
  })

  it('keeps a wait pending until the stage it delays reports', () => {
    const i = events.findIndex((e) => e.type === 'llm_waiting' && e.role === 'verify')
    expect(buildAnsweringState(events.slice(0, i + 1)).pendingWait?.seconds).toBe(29)
    expect(buildAnsweringState(events.slice(0, i + 2)).pendingWait).toBeUndefined()
  })

  it('sums usage per stage, including retries and waits', () => {
    const verify = buildAnsweringState(events).stages.find((s) => s.id === 'verify')!
    expect(verify.usage.calls).toBe(6)
    expect(verify.usage.retries).toBe(6)
    expect(verify.usage.waited_seconds).toBe(155)
  })
})

describe('the plate', () => {
  const state = buildAnsweringState(events)
  const contested = state.verdicts.c2.verdict

  it('has one column per document seen, most relevant first', () => {
    expect(documentsOf(state)[0]).toBe('vectara-semantic-chunking-naacl2025.pdf')
    expect(documentsOf(state)).toHaveLength(4)
  })

  it('says what each source did with a claim', () => {
    expect(stanceOf(contested, 'lumberchunker-emnlp2024.pdf')).toBe('supports')
    expect(stanceOf(contested, 'vectara-semantic-chunking-naacl2025.pdf')).toBe('contradicts')
    expect(stanceOf(contested, 'lewis-rag-neurips2020.pdf')).toBe('silent')
    expect(stanceOf(contested, 'SOURCES.md')).toBe('not_read')
  })

  it('flags a verdict resting on other sources than the cited one', () => {
    expect(citationMismatch(state.verdicts.c4.verdict)).toBe('vectara-semantic-chunking-naacl2025.pdf')
    expect(citationMismatch(state.verdicts.c1.verdict)).toBeNull()
    expect(citationMismatch(state.verdicts.c5.verdict)).toBeNull() // no citation
  })
})

describe('citations', () => {
  it('parses the drafter citation format', () => {
    expect(parseCitation('vectara.pdf | chunk #3')).toEqual({ filename: 'vectara.pdf', chunk: 3 })
    expect(parseCitation('vectara.pdf')).toEqual({ filename: 'vectara.pdf', chunk: undefined })
    expect(parseCitation(null)).toBeNull()
  })

  it('splits a draft into text and citation chips', () => {
    const pieces = splitCitations('A claim【a.pdf | chunk #1】 and another [b.md].')
    expect(pieces.map((p) => p.kind)).toEqual(['text', 'cite', 'text', 'cite', 'text'])
    expect(pieces[1]).toMatchObject({ filename: 'a.pdf', chunk: 1 })
    expect(pieces[3]).toMatchObject({ filename: 'b.md' })
  })
})
