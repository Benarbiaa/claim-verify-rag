// The pipeline steps, and under them one time axis for the whole run (the "graticule"):
// every stage is drawn at its real duration, and rate-limit waits are hatched to scale.

import { motion, useReducedMotion } from 'motion/react'
import { formatSeconds } from '@/lib/format'
import type { StageStatus } from '@/lib/answering'
import type { Segment, Timeline } from '@/lib/timeline'
import type { VerdictLabel } from '@/lib/types'
import { cn } from '@/lib/utils'
import { VerdictMark } from './verdict'

export interface Step {
  id: string
  label: string
  status: StageStatus
  /** figures under the label, e.g. "4.4 s", "7.0K tokens" */
  figures: string[]
  /** e.g. "9 retries, 4 min 54 s waiting" */
  note?: string
  /** the key of its span on the axis ('end' = the finish line) */
  span: string | 'end'
}

interface Props {
  steps: Step[]
  timeline: Timeline
  /** seconds reached so far */
  reached: number
  /** the part in flight during replay: the axis fills up to `to` over `duration` ms */
  flight?: { to: number; duration: number } | null
  landed: { at: number; verdict: VerdictLabel; position: number }[]
  focused: string | null
  onFocus: (id: string) => void
  /** live mode: the run is still going, the axis has no known end */
  open?: boolean
}

function niceStep(total: number): number {
  for (const step of [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200]) if (total / step <= 7) return step
  return 3600
}

const pct = (x: number, total: number) => `${Math.max(0, Math.min(100, (x / total) * 100))}%`

function StepMark({ status }: { status: StageStatus }) {
  if (status === 'done')
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
        <circle cx="7" cy="7" r="6.5" fill="var(--ink)" />
        <path d="M4 7.2l2 2 4-4.3" fill="none" stroke="var(--sheet)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  if (status === 'failed')
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
        <rect x="1" y="1" width="12" height="12" rx="2" fill="var(--error)" />
        <rect x="6.1" y="3.5" width="1.8" height="4.5" rx="0.8" fill="var(--sheet)" />
        <circle cx="7" cy="10.1" r="1" fill="var(--sheet)" />
      </svg>
    )
  return (
    <span
      aria-hidden
      className={cn(
        'block size-3.5 rounded-full border',
        status === 'active' ? 'hatch-dense animate-[spin_6s_linear_infinite] border-ink-2' : 'border-dashed border-rule-strong',
      )}
    />
  )
}

export function RunTimeline({ steps, timeline, reached, flight, landed, focused, onFocus, open }: Props) {
  const reduce = useReducedMotion()
  const total = Math.max(timeline.total, reached, flight?.to ?? 0, 0.001) * (open ? 1.08 : 1)
  const tick = niceStep(total)
  const ticks = Array.from({ length: Math.floor(total / tick) + 1 }, (_, i) => i * tick)
  const target = flight ? flight.to : reached
  const fill = Math.min(100, (target / total) * 100)
  const transition = flight && !reduce ? `clip-path ${flight.duration}ms linear, transform ${flight.duration}ms linear` : 'none'
  const hasNotes = steps.some((s) => s.note)
  const focusedIndex = steps.findIndex((s) => s.id === focused)
  const anchor = (step: Step) => {
    if (step.span === 'end') return timeline.total
    const span = timeline.spans[step.span]
    return span ? (span.start + span.end) / 2 : undefined
  }

  return (
    <div className="select-none">
      <ol className="grid gap-px" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
        {steps.map((step) => (
          <li key={step.id} className="min-w-0">
            <button
              type="button"
              onClick={() => onFocus(step.id)}
              aria-current={focused === step.id ? 'step' : undefined}
              className={cn(
                'group relative flex w-full min-w-0 flex-col items-start gap-0.5 rounded-md px-1.5 py-1.5 text-left sm:px-2.5 transition-[background-color,transform] duration-150 ease-out hover:bg-sunk active:scale-[0.985]',
                focused === step.id && 'bg-sunk',
                step.status === 'pending' && 'text-ink-3',
              )}
            >
              <span className="flex max-w-full min-w-0 items-center gap-1.5 text-sm font-bold sm:gap-2 sm:text-[0.95rem]">
                <StepMark status={step.status} />
                <span className="truncate">{step.label}</span>
              </span>
              <span className="figures hidden max-w-full truncate text-xs text-ink-2 sm:block">
                {step.figures.filter(Boolean).join(' · ') || '\u00a0'}
              </span>
              {hasNotes && <span className="figures hidden max-w-full truncate text-xs text-ink-3 md:block">{step.note || '\u00a0'}</span>}
              {focused === step.id && (
                <motion.span
                  layoutId="focused-step"
                  className="absolute inset-x-2.5 -bottom-px h-0.5 rounded-full bg-ink"
                  transition={{ type: 'spring', duration: 0.35, bounce: 0.1 }}
                />
              )}
            </button>
          </li>
        ))}
      </ol>

      {/* a leader from the focused step to its stretch of the axis */}
      <svg className="block h-3 w-full" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden>
        {focusedIndex >= 0 &&
          (() => {
            const x = anchor(steps[focusedIndex])
            if (x == null) return null
            const from = ((focusedIndex + 0.5) / steps.length) * 100
            const to = (x / total) * 100
            return (
              <path
                d={`M${from} 0 V4 H${to} V10`}
                fill="none"
                stroke="var(--ink-2)"
                strokeWidth={1.2}
                vectorEffect="non-scaling-stroke"
              />
            )
          })()}
      </svg>

      <div className="relative">
        {/* verdicts land on the axis at the moment they were given */}
        <div className="relative h-4" aria-hidden>
          {landed.map((v) => (
            <motion.span
              key={v.position}
              className="absolute top-0 -translate-x-1/2"
              style={{ left: pct(v.at, total) }}
              initial={reduce ? false : { opacity: 0, transform: 'translateY(-6px) scale(0.85)' }}
              animate={{ opacity: 1, transform: 'translateY(0px) scale(1)' }}
              transition={{ duration: 0.25, ease: [0.23, 1, 0.32, 1] }}
            >
              <VerdictMark verdict={v.verdict} size={14} />
            </motion.span>
          ))}
        </div>

        <div className="relative h-5 overflow-hidden rounded-[3px] bg-sunk" role="img" aria-label={axisLabel(timeline, reached)}>
          <Track segments={timeline.segments} total={total} ghost />
          <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - fill}% 0 0)`, transition }}>
            <Track segments={timeline.segments} total={total} />
          </div>
          <div className="pointer-events-none absolute inset-0" style={{ transform: `translateX(${fill}%)`, transition }}>
            <span className="absolute inset-y-0 left-0 w-0.5 -translate-x-1/2 bg-ink" />
          </div>
        </div>

        <div className="figures relative mt-0.5 h-4 text-[0.7rem] text-ink-3" aria-hidden>
          {ticks.map((t) => (
            <span
              key={t}
              className="absolute -translate-x-1/2 whitespace-nowrap first:translate-x-0 max-sm:[&:nth-child(even)]:hidden"
              style={{ left: pct(t, total) }}
            >
              {t === 0 ? '0' : formatSeconds(t)}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

function Track({ segments, total, ghost }: { segments: Segment[]; total: number; ghost?: boolean }) {
  return (
    <div className="absolute inset-0">
      {segments.map((s, i) => (
        <span
          key={i}
          className={cn(
            'absolute inset-y-0',
            s.kind === 'wait' ? 'hatch' : ghost ? 'bg-rule' : 'bg-ink-2',
            s.kind === 'wait' && !ghost && 'bg-ink-3/15',
            ghost && s.kind === 'wait' && 'opacity-60',
          )}
          style={{ left: pct(s.start, total), width: `max(1.5px, ${pct(s.end - s.start, total)})` }}
        >
          {/* claim boundaries inside verification */}
          {s.position != null && s.kind === 'work' && <span className="absolute inset-y-0 right-0 w-px bg-sheet/70" />}
        </span>
      ))}
    </div>
  )
}

function axisLabel(timeline: Timeline, reached: number): string {
  const waiting = timeline.segments.filter((s) => s.kind === 'wait').reduce((sum, s) => sum + s.end - s.start, 0)
  return `Time axis: ${formatSeconds(reached)} of ${formatSeconds(timeline.total)} shown; ${formatSeconds(waiting)} of the run was spent waiting on rate limits.`
}
