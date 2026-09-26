// Replay controls: play / pause, step, speed, and a scrubber over the run's cues (events).

import { Pause, Play, RotateCcw, SkipBack, SkipForward } from 'lucide-react'
import { Slider as SliderPrimitive } from 'radix-ui'
import { useEffect } from 'react'
import { type Replay, SPEEDS, describeCue } from '@/lib/replay'
import type { PipelineEvent } from '@/lib/types'
import { cn } from '@/lib/utils'

export function Transport({ replay, events }: { replay: Replay; events: PipelineEvent[] }) {
  const { cursor, playing, speed } = replay
  const total = events.length
  const atEnd = cursor >= total

  // Space plays / pauses, arrows step through the cues (not while typing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.closest('input, textarea, select, [role="slider"], [contenteditable]')) return
      if (e.key === ' ' && !target.closest('button, a')) {
        e.preventDefault()
        replay.toggle()
      } else if (e.key === 'ArrowRight') replay.step(1)
      else if (e.key === 'ArrowLeft') replay.step(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [replay])

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="flex items-center gap-1">
        <IconButton label="Previous cue" onClick={() => replay.step(-1)} disabled={cursor === 0}>
          <SkipBack className="size-4" />
        </IconButton>
        <button
          type="button"
          onClick={replay.toggle}
          className="inline-flex h-10 min-w-[7.5rem] items-center justify-center gap-2 rounded-lg bg-ink px-4 text-[0.95rem] font-bold text-sheet shadow-lift transition-transform duration-150 ease-out active:scale-[0.97]"
          aria-label={playing ? 'Pause the replay' : atEnd ? 'Replay from the start' : 'Play the replay'}
        >
          {playing ? <Pause className="size-4 fill-current" /> : atEnd ? <RotateCcw className="size-4" /> : <Play className="size-4 fill-current" />}
          {playing ? 'Pause' : atEnd ? 'Replay' : cursor === 0 ? 'Play' : 'Resume'}
        </button>
        <IconButton label="Next cue" onClick={() => replay.step(1)} disabled={atEnd}>
          <SkipForward className="size-4" />
        </IconButton>
      </div>

      <div role="radiogroup" aria-label="Replay speed" className="flex rounded-lg bg-sunk p-0.5">
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            role="radio"
            aria-checked={speed === s}
            onClick={() => replay.setSpeed(s)}
            className={cn(
              'figures rounded-md px-2.5 py-1 text-sm font-semibold text-ink-2 transition-colors duration-150',
              speed === s && 'bg-sheet text-ink shadow-[0_1px_2px_rgb(0_0_0/0.12)]',
            )}
          >
            {s}×
          </button>
        ))}
      </div>

      <div className="flex min-w-[16rem] flex-1 items-center gap-3">
        <SliderPrimitive.Root
          className="relative flex h-6 flex-1 touch-none items-center"
          min={0}
          max={total}
          step={1}
          value={[cursor]}
          onValueChange={([v]) => {
            replay.pause()
            replay.seek(v)
          }}
          aria-label="Replay position"
        >
          <SliderPrimitive.Track className="relative h-1 flex-1 overflow-hidden rounded-full bg-rule">
            <SliderPrimitive.Range className="absolute h-full bg-ink-2" />
          </SliderPrimitive.Track>
          <SliderPrimitive.Thumb
            className="block size-4 rounded-full border-2 border-ink bg-sheet shadow-lift transition-transform duration-100 active:scale-110"
            aria-valuetext={`Cue ${cursor} of ${total}: ${describeCue(events[cursor - 1])}`}
          />
        </SliderPrimitive.Root>
        <span className="figures w-[4.5rem] shrink-0 text-right text-xs text-ink-3" aria-hidden>
          {cursor}/{total}
        </span>
      </div>
      {!atEnd && (
        <button
          type="button"
          onClick={() => {
            replay.pause()
            replay.seek(total)
          }}
          className="rounded-md px-2 py-1 text-sm font-medium text-ink-2 underline-offset-4 transition-colors hover:text-ink hover:underline"
        >
          Jump to result
        </button>
      )}
      <p className="sr-only" aria-live="polite">
        {describeCue(events[cursor - 1])}
      </p>
    </div>
  )
}

function IconButton({ label, children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="inline-flex size-9 items-center justify-center rounded-lg text-ink-2 transition-[transform,color,background-color] duration-150 ease-out hover:bg-sunk hover:text-ink active:scale-[0.95] disabled:pointer-events-none disabled:opacity-35"
      {...props}
    >
      {children}
    </button>
  )
}
