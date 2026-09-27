// The pipeline steps, and under them one time axis for the whole run, drawn to scale:
// solid = working, hatched = waiting on the provider's rate limit. Each step has its own colour.

import { formatSeconds } from '@/lib/format'
import { stageColor, tint } from '@/lib/stages'
import type { StageStatus } from '@/lib/answering'
import type { Segment, Timeline } from '@/lib/timeline'
import { cn } from '@/lib/utils'

export interface Step {
  id: string
  label: string
  status: StageStatus
  /** one short figure under the label, e.g. "4.4 s" */
  figure?: string
}

interface Props {
  steps: Step[]
  timeline: Timeline
  /** seconds reached so far */
  reached: number
  /** the part in flight during replay: the axis fills up to `to` over `duration` ms */
  flight?: { to: number; duration: number } | null
  focused: string | null
  onFocus: (id: string) => void
  /** live mode: the run is still going, the axis has no known end */
  open?: boolean
}

const pct = (x: number, total: number) => `${Math.max(0, Math.min(100, (x / total) * 100))}%`

function StepMark({ status, color }: { status: StageStatus; color: string }) {
  if (status === 'done')
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden className="shrink-0">
        <circle cx="7" cy="7" r="6.5" fill={color} />
        <path d="M4 7.2l2 2 4-4.3" fill="none" stroke="var(--sheet)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  if (status === 'failed')
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden className="shrink-0">
        <rect x="1" y="1" width="12" height="12" rx="2" fill="var(--error)" />
      </svg>
    )
  return (
    <span
      aria-hidden
      className={cn('block size-3.5 shrink-0 rounded-full border', status === 'active' ? 'hatch-dense' : 'border-dashed')}
      style={
        status === 'active'
          ? ({ borderColor: color, '--hatch': tint(color) } as React.CSSProperties)
          : { borderColor: tint(color, 45) }
      }
    />
  )
}

export function RunTimeline({ steps, timeline, reached, flight, focused, onFocus, open }: Props) {
  const total = Math.max(timeline.total, reached, flight?.to ?? 0, 0.001) * (open ? 1.08 : 1)
  const target = flight ? flight.to : reached
  const fill = Math.min(100, (target / total) * 100)
  const transition = flight ? `clip-path ${flight.duration}ms linear, transform ${flight.duration}ms linear` : 'none'
  const waiting = timeline.segments.filter((s) => s.kind === 'wait').reduce((sum, s) => sum + s.end - s.start, 0)

  return (
    <div className="select-none">
      <nav aria-label="Pipeline steps">
        <ol className="grid gap-1" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
          {steps.map((step, i) => {
            const color = stageColor(step.id)
            return (
            <li key={step.id} className="min-w-0">
              <button
                type="button"
                onClick={() => onFocus(step.id)}
                aria-current={focused === step.id ? 'step' : undefined}
                className={cn(
                  'relative flex w-full min-w-0 items-start gap-2 overflow-hidden rounded-lg border px-2.5 pt-2.5 pb-2 text-left transition-[background-color,border-color,transform] duration-150 ease-out active:scale-[0.98]',
                  focused === step.id ? 'bg-sheet' : 'border-transparent hover:bg-sunk',
                  step.status === 'pending' && 'text-ink-3',
                )}
                style={focused === step.id ? { borderColor: color } : undefined}
              >
                <span
                  aria-hidden
                  className={cn('absolute inset-x-0 top-0 h-[3px]', step.status === 'pending' && 'opacity-35')}
                  style={{ background: color }}
                />
                <span className="mt-[3px]">
                  <StepMark status={step.status} color={color} />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-bold">
                    <span className="font-normal text-ink-3 max-sm:hidden">{i + 1}. </span>
                    {step.label}
                  </span>
                  <span className="figures block truncate text-xs text-ink-3 max-sm:hidden">{step.figure || ' '}</span>
                </span>
              </button>
            </li>
            )
          })}
        </ol>
      </nav>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-ink-3">
        <span className="figures">
          <span className="font-bold text-ink-2">Time</span> · {formatSeconds(timeline.total)}
          {waiting > 0 && <> · {Math.round((waiting / Math.max(timeline.total, 0.001)) * 100)}% of it waiting</>}
        </span>
        <span className="flex items-center gap-3" aria-hidden>
          <span className="flex items-center gap-1.5">
            <span className="inline-flex h-2.5 w-4 overflow-hidden rounded-[2px]">
              {[1, 2, 3, 4].map((n) => (
                <span key={n} className="flex-1" style={{ background: `var(--stage-${n})` }} />
              ))}
            </span>{' '}
            working
          </span>
          <span className="flex items-center gap-1.5">
            <span className="hatch inline-block h-2.5 w-4 rounded-[2px] bg-sunk" /> waiting (rate limit)
          </span>
        </span>
      </div>
      <div className="relative mt-1.5 h-3 overflow-hidden rounded-full bg-sunk" role="img" aria-label={axisLabel(timeline, waiting)}>
        <Track segments={timeline.segments} total={total} ghost />
        <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - fill}% 0 0)`, transition }}>
          <Track segments={timeline.segments} total={total} />
        </div>
        <div className="pointer-events-none absolute inset-0" style={{ transform: `translateX(${fill}%)`, transition }}>
          <span className="absolute inset-y-0 left-0 w-0.5 -translate-x-1/2 bg-ink" />
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
          className={cn('absolute inset-y-0', s.kind === 'wait' ? 'hatch' : ghost && 'bg-rule', ghost && s.kind === 'wait' && 'opacity-50')}
          style={{
            left: pct(s.start, total),
            width: `max(1.5px, ${pct(s.end - s.start, total)})`,
            ...(s.kind === 'work' && !ghost && { background: stageColor(s.stage) }),
            ...(s.kind === 'wait' && !ghost && ({ '--hatch': tint(stageColor(s.stage)) } as React.CSSProperties)),
          }}
        />
      ))}
    </div>
  )
}

function axisLabel(timeline: Timeline, waiting: number): string {
  return `The run took ${formatSeconds(timeline.total)}, of which ${formatSeconds(waiting)} waiting on the provider's rate limit.`
}
