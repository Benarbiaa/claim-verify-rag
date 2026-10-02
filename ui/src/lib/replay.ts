// Replay of a recorded run: events are "cues" applied one after another, no API call.
// Real gaps are compressed (a 30 s rate-limit wait plays in about 2 s) but stay proportional.

import { useCallback, useEffect, useRef, useState } from 'react'
import type { PipelineEvent } from './types'

export const SPEEDS = [1, 2, 4] as const
export type Speed = (typeof SPEEDS)[number]

const MIN_MS = 300
const EXTRA_MS = 1600
const GAP_CAP_SECONDS = 40

// Time to look at what a cue brought before the next one starts (at 1x).
const DWELL_MS: Partial<Record<PipelineEvent['type'], number>> = {
  question_started: 700,
  passages_retrieved: 2600,
  draft_written: 3200,
  claims_extracted: 1800,
  claim_verified: 350,
  documents_loaded: 1200,
  documents_cleaned: 1200,
  chunks_built: 1200,
}

/** How long cue i stays in flight before it lands, at 1x: reading time for the previous cue, then the real gap, compressed. */
export function cueDelay(offsets: number[], events: PipelineEvent[], i: number): number {
  if (i <= 0) return 0
  const dwell = DWELL_MS[events[i - 1].type] ?? 0
  if (events[i].type === 'llm_waiting') return dwell + 320 // the announcement lands fast; the wait is the next gap
  const gap = Math.max(0, offsets[i] - offsets[i - 1])
  return dwell + MIN_MS + (EXTRA_MS * Math.min(gap, GAP_CAP_SECONDS)) / GAP_CAP_SECONDS
}

export interface Flight {
  /** the cue being played: events[index] lands when the flight ends */
  index: number
  startedAt: number
  duration: number
}

export interface Replay {
  cursor: number
  playing: boolean
  speed: Speed
  flight: Flight | null
  play: () => void
  pause: () => void
  toggle: () => void
  step: (delta: number) => void
  seek: (cursor: number) => void
  setSpeed: (speed: Speed) => void
}

/** cursor = number of events applied (0 = nothing yet, events.length = the end). */
export function useReplay(events: PipelineEvent[], offsets: number[], initialCursor: number): Replay {
  const [cursor, setCursor] = useState(initialCursor)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<Speed>(1)
  const [flight, setFlight] = useState<Flight | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const total = events.length

  useEffect(() => {
    window.clearTimeout(timer.current)
    if (!playing) {
      setFlight(null)
      return
    }
    if (cursor >= total) {
      setPlaying(false)
      setFlight(null)
      return
    }
    const duration = cueDelay(offsets, events, cursor) / speed
    setFlight({ index: cursor, startedAt: performance.now(), duration })
    timer.current = window.setTimeout(() => setCursor((c) => Math.min(c + 1, total)), duration)
    return () => window.clearTimeout(timer.current)
  }, [playing, cursor, speed, total, events, offsets])

  const play = useCallback(() => {
    setCursor((c) => (c >= total ? 0 : c))
    setPlaying(true)
  }, [total])
  const pause = useCallback(() => setPlaying(false), [])
  const toggle = useCallback(() => (playing ? pause() : play()), [playing, pause, play])
  const seek = useCallback((c: number) => setCursor(Math.max(0, Math.min(total, Math.round(c)))), [total])
  const step = useCallback(
    (delta: number) => {
      setPlaying(false)
      setCursor((c) => Math.max(0, Math.min(total, c + delta)))
    },
    [total],
  )

  return { cursor, playing, speed, flight, play, pause, toggle, step, seek, setSpeed }
}

/** A short name for a cue, for the scrubber and screen readers. */
export function describeCue(e: PipelineEvent | undefined): string {
  if (!e) return 'Start'
  switch (e.type) {
    case 'run_started':
      return 'Run started'
    case 'question_started':
      return 'Question received'
    case 'passages_retrieved':
      return `${e.passages.length} passages retrieved`
    case 'draft_written':
      return 'Draft written'
    case 'claims_extracted':
      return `${e.claims.length} claims extracted`
    case 'claim_verified':
      return `Claim ${e.position}/${e.total}: ${e.verdict.verdict}`
    case 'llm_waiting':
      return `${e.role}: waiting ${Math.round(e.seconds)} s (${e.reason.replace('_', ' ')})`
    case 'question_finished':
      return 'Question finished'
    case 'run_finished':
      return 'Run finished'
    case 'documents_loaded':
      return `${e.documents.length} documents loaded`
    case 'documents_cleaned':
      return `${e.documents.filter((d) => Object.values(d.changes).some(Boolean)).length} documents repaired`
    case 'chunks_built':
      return `${e.chunks.length} chunks built`
    case 'chunks_embedded':
      return `${e.count} chunks embedded`
    case 'chunks_stored':
      return `${e.count} chunks stored`
  }
}
