// One claim: its verdict, why, and the sources for (left) and against (right).

import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useState } from 'react'
import { type VerdictEntry, citationMismatch } from '@/lib/answering'
import { shortDoc } from '@/lib/format'
import type { Claim, Passage } from '@/lib/types'
import { cn } from '@/lib/utils'
import { PassageBlock } from '../Passage'
import { StanceMark, VERDICT_TEXT, VerdictMark } from '../verdict'

interface Props {
  claim: Claim
  entry?: VerdictEntry
  judging?: boolean
}

export function ClaimDetail({ claim, entry, judging }: Props) {
  const reduce = useReducedMotion()
  const v = entry?.verdict
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.section
        key={claim.id + (v ? ':done' : ':pending')}
        initial={reduce ? false : { opacity: 0, transform: 'translateY(6px)' }}
        animate={{ opacity: 1, transform: 'translateY(0px)' }}
        exit={{ opacity: 0, transition: { duration: 0.08 } }}
        transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
        aria-label="Selected claim"
        className="rounded-lg border border-rule bg-sheet p-5"
      >
        <p className="flex items-center gap-2.5">
          <VerdictMark verdict={v?.verdict ?? 'pending'} size={26} />
          <span className={cn('text-lg font-extrabold', v ? VERDICT_TEXT[v.verdict].ink : 'text-ink-2')}>
            {v ? VERDICT_TEXT[v.verdict].label : judging ? 'Checking…' : 'Not checked yet'}
          </span>
        </p>
        <p className="mt-3 text-[1.05rem] leading-snug font-semibold text-pretty">{claim.claim}</p>

        {v && (
          <>
            <Why text={v.justification} />
            {v.verdict !== 'error' && (
              <div className={cn('mt-4 grid grid-cols-2 gap-3', v.verdict === 'contested' && 'rounded-lg bg-sunk p-3')}>
                <Side title="For" stance="supports" sources={v.supporting_sources} evidence={v.evidence} />
                <Side title="Against" stance="contradicts" sources={v.contradicting_sources} evidence={v.evidence} />
              </div>
            )}
            {citationMismatch(v) && (
              <p className="mt-3 text-sm text-ink-3">
                The answer cited {shortDoc(citationMismatch(v)!)}, but the check relied on other sources.
              </p>
            )}
          </>
        )}
      </motion.section>
    </AnimatePresence>
  )
}

function Why({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-3">
      <p className={cn('text-sm leading-relaxed text-ink-2 text-pretty', !open && 'line-clamp-3')}>{text}</p>
      <button type="button" onClick={() => setOpen(!open)} className="mt-1 text-xs font-semibold text-ink-3 hover:text-ink">
        {open ? 'Less' : 'Why? Read more'}
      </button>
    </div>
  )
}

function Side({ title, stance, sources, evidence }: { title: string; stance: 'supports' | 'contradicts'; sources: string[]; evidence: Passage[] }) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <div className="min-w-0">
      <h3 className="mb-1.5 flex items-center gap-1.5 text-sm font-bold">
        <StanceMark stance={stance} size={12} />
        {title}
      </h3>
      {sources.length === 0 ? (
        <p className="text-sm text-ink-3">None</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {sources.map((s) => {
            const passage = evidence.find((p) => p.filename === s)
            return (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => setOpen(open === s ? null : s)}
                  aria-expanded={open === s}
                  className="w-full rounded-md bg-sunk px-3 py-1.5 text-left text-sm font-bold transition-colors hover:bg-rule"
                  title={s}
                >
                  {shortDoc(s)}
                </button>
                {open === s && passage && (
                  <div className="mt-1.5">
                    <PassageBlock passage={passage} lines={8} />
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
