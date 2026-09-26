import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { shortDoc } from '@/lib/format'
import type { Passage } from '@/lib/types'
import { cn } from '@/lib/utils'

/** Similarity score as a short bar on a fixed 0.5–1 scale, so bars compare across the whole run. */
export function ScoreBar({ score }: { score: number }) {
  const width = Math.max(0.04, Math.min(1, (score - 0.5) / 0.5))
  return (
    <span className="inline-flex items-center gap-2" title={`Cosine similarity ${score.toFixed(3)}`}>
      <span className="relative h-1.5 w-12 overflow-hidden rounded-full bg-rule" aria-hidden>
        <span className="absolute inset-y-0 left-0 rounded-full bg-ink-2" style={{ width: `${width * 100}%` }} />
      </span>
      <span className="figures text-xs text-ink-2">{score.toFixed(3)}</span>
    </span>
  )
}

export function PassageBlock({
  passage,
  lead,
  showDoc = false,
  highlight = false,
  defaultOpen = false,
  lines = 4,
}: {
  passage: Passage
  lead?: React.ReactNode
  showDoc?: boolean
  highlight?: boolean
  defaultOpen?: boolean
  lines?: number
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div
      className={cn(
        'rounded-md px-3 py-2.5 transition-colors duration-200',
        highlight ? 'bg-supported-wash ring-1 ring-supported/40' : 'bg-sunk/60',
      )}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {lead}
        {showDoc && (
          <span className="text-sm font-bold" title={passage.filename}>
            {shortDoc(passage.filename)}
          </span>
        )}
        <span className="figures text-xs text-ink-3">chunk #{passage.chunk_index}</span>
        <span className="ml-auto">
          <ScoreBar score={passage.score} />
        </span>
      </div>
      <p
        className={cn('mt-1.5 text-sm leading-relaxed text-ink-2 [overflow-wrap:anywhere]', !open && 'line-clamp-(--lines)')}
        style={{ '--lines': lines } as React.CSSProperties}
      >
        {passage.text}
      </p>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-ink-3 transition-colors hover:text-ink"
      >
        {open ? 'Show less' : 'Read the whole passage'}
        <ChevronDown className={cn('size-3.5 transition-transform duration-200 ease-out', open && 'rotate-180')} />
      </button>
    </div>
  )
}
