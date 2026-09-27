// Replay controls: play / pause, a progress bar you can drag, and the speed.
// Keyboard: space plays / pauses, arrows step through the events.

import { Pause, Play, RotateCcw } from 'lucide-react'
import { Slider as SliderPrimitive } from 'radix-ui'
import { useEffect } from 'react'
import { type Replay, SPEEDS, describeCue } from '@/lib/replay'
import type { PipelineEvent } from '@/lib/types'
import { cn } from '@/lib/utils'

export function Transport({ replay, events }: { replay: Replay; events: PipelineEvent[] }) {
  const { cursor, playing, speed } = replay
  const total = events.length
  const atEnd = cursor >= total

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
    <div className="flex items-center gap-3 sm:gap-4">
      <button
        type="button"
        onClick={replay.toggle}
        className="inline-flex h-10 min-w-[6.5rem] shrink-0 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-[0.95rem] font-bold text-sheet transition-transform duration-150 ease-out active:scale-[0.97]"
      >
        {playing ? <Pause className="size-4 fill-current" /> : atEnd ? <RotateCcw className="size-4" /> : <Play className="size-4 fill-current" />}
        {playing ? 'Pause' : atEnd ? 'Replay' : 'Play'}
      </button>

      <SliderPrimitive.Root
        className="relative flex h-6 min-w-0 flex-1 touch-none items-center"
        min={0}
        max={total}
        step={1}
        value={[cursor]}
        onValueChange={([v]) => {
          replay.pause()
          replay.seek(v)
        }}
        aria-label="Replay progress"
      >
        <SliderPrimitive.Track className="relative h-1 flex-1 overflow-hidden rounded-full bg-rule">
          <SliderPrimitive.Range className="absolute h-full bg-ink-2" />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb
          className="block size-4 rounded-full border-2 border-ink bg-sheet transition-transform duration-100 active:scale-110"
          aria-valuetext={`Step ${cursor} of ${total}: ${describeCue(events[cursor - 1])}`}
        />
      </SliderPrimitive.Root>

      <div role="radiogroup" aria-label="Replay speed" className="flex shrink-0 rounded-lg bg-sunk p-0.5">
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            role="radio"
            aria-checked={speed === s}
            onClick={() => replay.setSpeed(s)}
            className={cn(
              'figures rounded-md px-2 py-1 text-sm font-semibold text-ink-3 transition-colors duration-150',
              speed === s && 'bg-sheet text-ink shadow-[0_1px_2px_rgb(0_0_0/0.12)]',
            )}
          >
            {s}×
          </button>
        ))}
      </div>
      <p className="sr-only" aria-live="polite">
        {describeCue(events[cursor - 1])}
      </p>
    </div>
  )
}
