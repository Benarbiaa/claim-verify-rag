import { useState } from 'react'
import { shortDoc } from '@/lib/format'
import type { Passage } from '@/lib/types'
import { cn } from '@/lib/utils'

/** A retrieved passage: its source, and its text (click to read it all). */
export function PassageBlock({
  passage,
  showDoc = false,
  highlight = false,
  lines = 4,
}: {
  passage: Passage
  showDoc?: boolean
  highlight?: boolean
  lines?: number
}) {
  const [open, setOpen] = useState(false)
  return (
    <button
      type="button"
      onClick={() => setOpen(!open)}
      aria-expanded={open}
      title={open ? 'Show less' : 'Read the whole passage'}
      className={cn(
        'block w-full rounded-md px-3 py-2.5 text-left transition-colors duration-200',
        highlight ? 'bg-supported-wash ring-1 ring-supported/40' : 'bg-sunk/70 hover:bg-sunk',
      )}
    >
      {showDoc && <span className="mb-1 block text-sm font-bold text-ink">{shortDoc(passage.filename)}</span>}
      <span
        className={cn('block text-sm leading-relaxed text-ink-2 [overflow-wrap:anywhere]', !open && 'line-clamp-(--lines)')}
        style={{ '--lines': lines } as React.CSSProperties}
      >
        {passage.text}
      </span>
    </button>
  )
}
