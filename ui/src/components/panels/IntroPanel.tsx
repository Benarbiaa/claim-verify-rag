import { Play } from 'lucide-react'
import type { AnsweringState } from '@/lib/answering'

const STEPS = [
  ['Search', 'find passages in every document'],
  ['Answer', 'write an answer from them'],
  ['Split', 'cut the answer into short claims'],
  ['Check', 'test each claim against every source'],
]

export function IntroPanel({ onPlay }: { state: AnsweringState; onPlay?: () => void }) {
  return (
    <div className="flex flex-col items-start gap-8 py-6">
      <p className="max-w-[30ch] text-[clamp(1.5rem,1.1rem+1.3vw,2.3rem)] leading-[1.15] font-extrabold tracking-[-0.03em] text-balance">
        An AI answers the question, then fact-checks its own answer.
      </p>
      <ol className="grid w-full max-w-4xl gap-3 sm:grid-cols-4">
        {STEPS.map(([title, text], i) => (
          <li key={title} className="flex gap-3 sm:flex-col sm:gap-1.5">
            <span className="figures inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-ink text-sm font-bold text-sheet">
              {i + 1}
            </span>
            <span>
              <span className="block font-bold">{title}</span>
              <span className="text-sm text-ink-2">{text}</span>
            </span>
          </li>
        ))}
      </ol>
      {onPlay && (
        <button
          type="button"
          onClick={onPlay}
          className="inline-flex h-12 items-center gap-2.5 rounded-xl bg-ink px-6 text-lg font-bold text-sheet transition-transform duration-150 ease-out active:scale-[0.97]"
        >
          <Play className="size-5 fill-current" />
          Play
        </button>
      )}
    </div>
  )
}
