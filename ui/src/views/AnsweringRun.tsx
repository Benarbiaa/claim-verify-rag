// An answering run: the question, the pipeline steps on one time axis, and the focused step's output.
// Replay (a recorded run, cue by cue) and live (events streamed from the API) share this view.

import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useMemo, useState } from 'react'
import { type AnsweringState, type StageId, type StageStatus, buildAnsweringState, questionEvents } from '@/lib/answering'
import { formatRunDate, formatSeconds, formatTokens, plural } from '@/lib/format'
import type { LiveFailure, LiveStatus } from '@/lib/live'
import type { Replay } from '@/lib/replay'
import { type Timeline, buildTimeline } from '@/lib/timeline'
import type { PipelineEvent, RunSummary, VerdictLabel } from '@/lib/types'
import { RunTimeline, type Step } from '@/components/RunTimeline'
import { Transport } from '@/components/Transport'
import { DraftPanel } from '@/components/panels/DraftPanel'
import { IntroPanel } from '@/components/panels/IntroPanel'
import { PlatePanel } from '@/components/panels/PlatePanel'
import { RetrievePanel } from '@/components/panels/RetrievePanel'
import { SummaryPanel } from '@/components/panels/SummaryPanel'
import { LiveBanner } from '@/components/LiveBanner'
import { FixtureNote } from '@/components/FixtureNote'

type Panel = 'intro' | 'retrieve' | 'draft' | 'plate' | 'summary'

const PANEL_OF_STEP: Record<StageId, Panel> = { retrieve: 'retrieve', draft: 'draft', decompose: 'plate', verify: 'plate', done: 'summary' }
const STEP_OF_PANEL: Record<Panel, StageId | null> = { intro: null, retrieve: 'retrieve', draft: 'draft', plate: 'verify', summary: 'done' }

interface Props {
  summary: RunSummary
  events: PipelineEvent[]
  /** replay: the controls and the cursor; absent in live mode */
  replay?: Replay
  live?: { status: LiveStatus; failure: LiveFailure | null }
}

export function AnsweringRun({ summary, events, replay, live }: Props) {
  const reduce = useReducedMotion()
  const [questionIndex, setQuestionIndex] = useState(1)
  const allForQuestion = useMemo(() => questionEvents(events, questionIndex), [events, questionIndex])
  const fullTimeline = useMemo(() => buildTimeline(allForQuestion, 'answering'), [allForQuestion])

  // replay shows the first `cursor` events of the whole run
  const shown = replay ? events.slice(0, replay.cursor) : events
  const state = useMemo(() => buildAnsweringState(shown, questionIndex), [shown, questionIndex])
  const shownForQuestion = useMemo(() => questionEvents(shown, questionIndex), [shown, questionIndex])
  const timeline: Timeline = live ? buildTimeline(allForQuestion, 'answering') : fullTimeline
  const reachedIndex = shownForQuestion.length - 1
  const reached = reachedIndex >= 0 ? (buildTimeline(shownForQuestion, 'answering').offsets[reachedIndex] ?? 0) : 0

  // the cue in flight (replay): its target time on the axis, and how long it takes to land
  const cue = replay?.flight
  const flight = useMemo(() => {
    if (!cue) return null
    const next = events[cue.index]
    const i = allForQuestion.indexOf(next)
    if (i < 0) return null
    return { to: fullTimeline.offsets[i], duration: cue.duration, event: next, gap: gapWait(fullTimeline, i) }
  }, [cue, events, allForQuestion, fullTimeline])

  // Focus: follows the pipeline until the viewer picks a step; Play hands it back.
  const [manualPanel, setManualPanel] = useState<Panel | null>(null)
  const [manualClaim, setManualClaim] = useState<string | null>(null)
  useEffect(() => {
    if (replay?.playing) {
      setManualPanel(null)
      setManualClaim(null)
    }
  }, [replay?.playing])
  const followPanel = followedPanel(state, shown.length)
  const panel = manualPanel ?? followPanel
  const latestVerdict = Object.values(state.verdicts).sort((a, b) => b.position - a.position)[0]
  const judging = judgingPosition(state, flight?.event, !!live)
  const followClaim = judging && state.claims ? state.claims[judging - 1]?.id : latestVerdict?.verdict.claim_id
  const selectedClaim = manualClaim ?? followClaim ?? null

  const steps = buildSteps(state, fullTimeline, live?.status === 'failed')
  const landed = useMemo(() => {
    const t = buildTimeline(shownForQuestion, 'answering')
    return shownForQuestion.flatMap((e, i) =>
      e.type === 'claim_verified' ? [{ at: t.offsets[i], verdict: e.verdict.verdict as VerdictLabel, position: e.position }] : [],
    )
  }, [shownForQuestion])

  const question = state.question ?? summary.questions?.[questionIndex - 1] ?? state.questions[questionIndex - 1] ?? 'Answering run'
  const nowLine = describeNow(state, flight, live)

  return (
    <div className="mx-auto w-full max-w-[1760px] px-4 pt-5 pb-16 sm:px-6">
      <header className="mb-3 flex flex-wrap items-start justify-between gap-x-8 gap-y-2">
        <div className="min-w-0 max-w-[80ch]">
          <h1 className="text-[clamp(1.25rem,0.95rem+0.95vw,1.9rem)] leading-tight font-extrabold tracking-[-0.025em] text-balance">{question}</h1>
          <p className="figures mt-1 flex flex-wrap gap-x-3 text-xs text-ink-3">
            <span>{formatRunDate(summary.run_id)}</span>
            {state.configFile && <span>{state.configFile}</span>}
            <span>{summary.run_id}</span>
            {live && <span className="font-sans font-bold text-ink-2">live run</span>}
          </p>
        </div>
        {state.questions.length > 1 && (
          <label className="flex items-center gap-2 text-sm text-ink-2">
            Question
            <select
              className="rounded-md border border-rule-strong bg-sheet px-2 py-1 text-ink"
              value={questionIndex}
              onChange={(e) => setQuestionIndex(Number(e.target.value))}
            >
              {state.questions.map((q, i) => (
                <option key={i} value={i + 1}>
                  {i + 1}. {q.length > 60 ? `${q.slice(0, 60)}…` : q}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>

      {summary.source === 'fixture' && <FixtureNote />}

      <div className="z-20 -mx-4 mb-5 border-b border-rule bg-paper/95 px-4 pt-1 pb-2 backdrop-blur-sm sm:-mx-6 sm:px-6 [@media(min-height:860px)_and_(min-width:1024px)]:sticky [@media(min-height:860px)_and_(min-width:1024px)]:top-12">
        {replay ? <Transport replay={replay} events={events} /> : live && <LiveBanner status={live.status} failure={live.failure} />}
        <div className="mt-1.5">
          <RunTimeline
            steps={steps}
            timeline={timeline}
            reached={reached}
            flight={flight}
            landed={landed}
            focused={STEP_OF_PANEL[panel]}
            onFocus={(id) => setManualPanel(PANEL_OF_STEP[id as StageId])}
            open={!!live && live.status === 'running'}
          />
        </div>
        <p className="min-h-5 text-sm text-ink-2" aria-live="polite">
          {nowLine}
        </p>
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={panel}
          initial={reduce ? false : { opacity: 0, transform: 'translateY(8px)', filter: 'blur(3px)' }}
          animate={{ opacity: 1, transform: 'translateY(0px)', filter: 'blur(0px)' }}
          exit={{ opacity: 0, filter: 'blur(2px)', transition: { duration: 0.1 } }}
          transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}
        >
          {panel === 'intro' && <IntroPanel state={state} onPlay={replay?.play} />}
          {panel === 'retrieve' && <RetrievePanel state={state} />}
          {panel === 'draft' && <DraftPanel state={state} />}
          {panel === 'plate' && (
            <PlatePanel
              state={state}
              selected={selectedClaim}
              onSelect={(id) => {
                replay?.pause()
                setManualClaim(id)
              }}
              judging={judging}
            />
          )}
          {panel === 'summary' && <SummaryPanel state={state} timeline={fullTimeline} />}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

/** Where the view goes by itself: the output of the latest stage. */
function followedPanel(state: AnsweringState, shownCount: number): Panel {
  if (shownCount === 0 || !state.question) return 'intro'
  if (state.claims) return 'plate'
  if (state.draft) return 'draft'
  return 'retrieve'
}

function judgingPosition(state: AnsweringState, next: PipelineEvent | undefined, live: boolean): number | null {
  if (next?.type === 'claim_verified') return next.position
  if (next?.type === 'llm_waiting' && next.role === 'verify' && state.claims) return Object.keys(state.verdicts).length + 1
  if (live && state.claims && !state.finished) {
    const n = Object.keys(state.verdicts).length
    return n < state.claims.length ? n + 1 : null
  }
  return null
}

/** Rate-limit wait inside the gap before event i, in seconds. */
function gapWait(timeline: Timeline, i: number): number {
  const from = timeline.offsets[i - 1] ?? 0
  const to = timeline.offsets[i]
  return timeline.segments
    .filter((s) => s.kind === 'wait' && s.start >= from - 0.01 && s.end <= to + 0.01)
    .reduce((sum, s) => sum + s.end - s.start, 0)
}

function describeNow(
  state: AnsweringState,
  flight: { event: PipelineEvent; gap: number; duration: number } | null,
  live?: { status: LiveStatus; failure: LiveFailure | null },
): React.ReactNode {
  const n = state.claims?.length ?? 0
  const verified = Object.keys(state.verdicts).length
  if (flight) {
    const e = flight.event
    const wait = flight.gap >= 1 ? <WaitNote seconds={flight.gap} /> : null
    switch (e.type) {
      case 'passages_retrieved':
        return 'Searching every document for passages about the question…'
      case 'draft_written':
        return <>Writing the draft from the passages…{wait}</>
      case 'claims_extracted':
        return <>Splitting the draft into claims…{wait}</>
      case 'claim_verified':
        return (
          <>
            Judging claim {e.position} of {e.total} against every source…{wait}
          </>
        )
      case 'llm_waiting':
        return <>The {e.role === 'verify' ? 'judge' : e.role} hit the provider's rate limit.</>
      case 'question_finished':
        return 'Finishing…'
      default:
        return null
    }
  }
  if (live?.status === 'running' && !state.finished) {
    if (state.pendingWait) return <LiveWait wait={state.pendingWait} />
    if (!state.passages) return 'Searching every document for passages about the question…'
    if (!state.draft) return 'Writing the draft…'
    if (!state.claims) return 'Splitting the draft into claims…'
    return `Judging claim ${verified + 1} of ${n} against every source…`
  }
  if (state.finished) return `Done: ${plural(n, 'claim')} checked.`
  return null
}

function WaitNote({ seconds }: { seconds: number }) {
  return (
    <span className="ml-2 inline-flex items-center gap-1.5 text-ink-3">
      <span className="hatch inline-block h-2.5 w-5 rounded-[2px] bg-sunk" aria-hidden />
      includes {formatSeconds(seconds)} waiting on the rate limit (sped up)
    </span>
  )
}

function LiveWait({ wait }: { wait: NonNullable<AnsweringState['pendingWait']> }) {
  const [now, setNow] = useState(() => Date.now())
  const [since] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [])
  const left = Math.max(0, Math.ceil(wait.seconds - (now - since) / 1000))
  const reason = wait.reason === 'rate_limit' ? 'rate limit' : wait.reason === 'server_error' ? 'server error' : 'connection problem'
  return (
    <span className="inline-flex items-center gap-2">
      <span className="hatch inline-block h-2.5 w-5 rounded-[2px] bg-sunk" aria-hidden />
      <span>
        The {wait.role === 'verify' ? 'judge' : wait.role} hit a {reason}: retrying in{' '}
        <span className="figures font-semibold text-ink">{left} s</span> (attempt {wait.attempt + 1}).
      </span>
    </span>
  )
}

function buildSteps(state: AnsweringState, timeline: Timeline, failed: boolean): Step[] {
  const s = (id: StageId) => state.stages.find((x) => x.id === id)!
  const tokens = (id: StageId) => {
    const u = s(id).usage
    return u.calls ? `${formatTokens(u.tokens_in + u.tokens_out)} tok` : ''
  }
  const waitNote = (id: StageId) => {
    const u = s(id).usage
    return u.retries ? `${plural(u.retries, 'retry', 'retries')} · ${formatSeconds(u.waited_seconds)} waiting` : undefined
  }
  const done = (id: StageId) => s(id).status === 'done'
  const verified = Object.keys(state.verdicts).length
  const n = state.claims?.length
  return [
    {
      id: 'retrieve',
      label: 'Retrieve',
      status: s('retrieve').status,
      figures: done('retrieve') ? [formatSeconds(s('retrieve').seconds), `${state.passages?.length} passages`] : [],
      span: 'retrieve',
    },
    {
      id: 'draft',
      label: 'Draft',
      status: s('draft').status,
      figures: done('draft') ? [formatSeconds(s('draft').seconds), tokens('draft')] : [],
      note: waitNote('draft'),
      span: 'draft',
    },
    {
      id: 'decompose',
      label: 'Decompose',
      status: s('decompose').status,
      figures: done('decompose') ? [formatSeconds(s('decompose').seconds), `${n} claims`] : [],
      note: waitNote('decompose'),
      span: 'decompose',
    },
    {
      id: 'verify',
      label: n ? `Verify ${verified}/${n}` : 'Verify',
      status: s('verify').status,
      figures: verified ? [formatSeconds(s('verify').seconds), tokens('verify')] : [],
      note: waitNote('verify'),
      span: 'verify',
    },
    {
      id: 'done',
      label: 'Done',
      status: (state.finished ? 'done' : 'pending') as StageStatus,
      figures: state.finished ? [formatSeconds(state.questionSeconds ?? timeline.total), 'summary'] : [],
      span: 'end',
    },
  ].map((step) => (failed && step.status === 'active' ? { ...step, status: 'failed' as const } : step))
}
