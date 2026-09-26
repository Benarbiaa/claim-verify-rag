// One claim under the loupe: the verdict, the judge's reasoning, and the evidence it read,
// split into the sources for (left) and against (right).

import { Split } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { type Stance, type VerdictEntry, citationMismatch, parseCitation, stanceOf } from '@/lib/answering'
import { formatSeconds, formatTokens, modelOf, plural, shortDoc } from '@/lib/format'
import type { Claim, Passage } from '@/lib/types'
import { cn } from '@/lib/utils'
import { PassageBlock } from '../Passage'
import { StanceMark, VERDICT_TEXT, VerdictMark } from '../verdict'

interface Props {
  claim: Claim
  position: number
  total: number
  entry?: VerdictEntry
  judging?: boolean
}

export function ClaimDetail({ claim, position, total, entry, judging }: Props) {
  const reduce = useReducedMotion()
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.section
        key={claim.id + (entry ? ':done' : ':pending')}
        initial={reduce ? false : { opacity: 0, transform: 'translateY(6px)', filter: 'blur(2px)' }}
        animate={{ opacity: 1, transform: 'translateY(0px)', filter: 'blur(0px)' }}
        exit={{ opacity: 0, transition: { duration: 0.08 } }}
        transition={{ duration: 0.24, ease: [0.23, 1, 0.32, 1] }}
        aria-label={`Claim ${position} of ${total}`}
        className="rounded-lg border border-rule bg-sheet p-4 sm:p-5"
      >
        <header className="flex items-center gap-3">
          <VerdictMark verdict={entry?.verdict.verdict ?? 'pending'} size={30} />
          <div className="min-w-0">
            <p className={cn('text-lg leading-tight font-extrabold', entry ? VERDICT_TEXT[entry.verdict.verdict].ink : 'text-ink-2')}>
              {entry ? VERDICT_TEXT[entry.verdict.verdict].label : judging ? 'Being judged…' : 'Not verified yet'}
            </p>
            <p className="figures text-xs text-ink-3">
              claim {position} of {total}
            </p>
          </div>
        </header>
        <blockquote className="mt-3 text-[1.08rem] leading-snug font-semibold text-pretty text-ink">{claim.claim}</blockquote>
        {entry ? <Verdict entry={entry} /> : <PendingDetail claim={claim} />}
      </motion.section>
    </AnimatePresence>
  )
}

function PendingDetail({ claim }: { claim: Claim }) {
  const cited = parseCitation(claim.cited_source)
  return (
    <p className="mt-3 text-sm text-ink-2">
      {cited ? (
        <>
          The draft cited <strong className="text-ink">{cited.filename}</strong>. The judge will ignore that and search every
          document again.
        </>
      ) : (
        'The draft gave no citation for this claim. The judge will search every document for it.'
      )}
    </p>
  )
}

function Verdict({ entry }: { entry: VerdictEntry }) {
  const v = entry.verdict
  const mismatch = citationMismatch(v)
  const byStance = (s: Stance) => v.evidence.filter((p) => stanceOf(v, p.filename) === s)
  const forSide = byStance('supports')
  const againstSide = byStance('contradicts')
  const silent = byStance('silent')
  const cited = parseCitation(v.original_cited_source)

  return (
    <>
      <p className="mt-1.5 text-xs text-ink-3">{VERDICT_TEXT[v.verdict].meaning}</p>

      {mismatch && (
        <p className="mt-3 flex gap-2 rounded-md bg-sunk px-3 py-2 text-sm text-ink">
          <Split className="mt-0.5 size-4 shrink-0 text-ink-2" aria-hidden />
          <span>
            The draft cited <strong>{shortDoc(mismatch)}</strong>
            {cited?.chunk != null && <> #{cited.chunk}</>}, but the judge's verdict rests on{' '}
            <strong>{[...v.supporting_sources, ...v.contradicting_sources].map(shortDoc).join(' and ')}</strong>.
          </span>
        </p>
      )}

      <div className="mt-4">
        <h3 className="text-sm font-bold text-ink">Why the judge decided this</h3>
        <p className="mt-1 text-sm leading-relaxed text-pretty text-ink-2">{v.justification}</p>
      </div>

      {v.verdict !== 'error' && (
        <div className={cn('mt-4 grid grid-cols-2 gap-3', v.verdict === 'contested' && 'rounded-lg bg-sunk p-2.5')}>
          {v.verdict === 'contested' && (
            <p className="col-span-2 text-sm font-bold text-ink">The sources disagree with each other on this claim.</p>
          )}
          <Side title="For" stance="supports" sources={v.supporting_sources} passages={forSide} />
          <Side title="Against" stance="contradicts" sources={v.contradicting_sources} passages={againstSide} />
        </div>
      )}

      {silent.length > 0 && (
        <details className="group mt-3">
          <summary className="cursor-pointer list-none text-sm font-semibold text-ink-2 transition-colors hover:text-ink">
            <span className="inline-flex items-center gap-1.5">
              <StanceMark stance="silent" size={13} />
              {plural(silent.length, 'other passage')} read, silent on this claim
              <span className="text-ink-3 group-open:hidden">(show)</span>
            </span>
          </summary>
          <div className="mt-2 flex flex-col gap-2">
            {silent.map((p) => (
              <PassageBlock key={`${p.filename}#${p.chunk_index}`} passage={p} showDoc lines={3} />
            ))}
          </div>
        </details>
      )}

      <p className="figures mt-4 border-t border-rule pt-3 text-xs text-ink-3">
        {modelOf(v.verifier)} · read {plural(v.evidence.length, 'passage')} · {formatTokens(entry.usage.tokens_in + entry.usage.tokens_out)} tokens
        {entry.usage.retries > 0 && (
          <>
            {' '}
            · {plural(entry.usage.retries, 'retry', 'retries')}, waited {formatSeconds(entry.usage.waited_seconds)}
          </>
        )}
      </p>
    </>
  )
}

function Side({ title, stance, sources, passages }: { title: string; stance: Stance; sources: string[]; passages: Passage[] }) {
  const empty = sources.length === 0
  return (
    <div className="min-w-0">
      <h3 className="mb-1.5 flex items-center gap-1.5 text-sm font-bold text-ink">
        <StanceMark stance={stance} size={12} />
        {title}
      </h3>
      {empty ? (
        <p className="rounded-md border border-dashed border-rule-strong px-3 py-2 text-sm text-ink-3">No source</p>
      ) : (
        <div className="flex flex-col gap-2">
          {sources.map((s) => {
            const read = passages.filter((p) => p.filename === s)
            return read.length ? (
              read.map((p) => <PassageBlock key={`${p.filename}#${p.chunk_index}`} passage={p} showDoc lines={4} />)
            ) : (
              <p key={s} className="rounded-md bg-sunk px-3 py-2 text-sm font-bold" title={s}>
                {shortDoc(s)}
              </p>
            )
          })}
        </div>
      )}
    </div>
  )
}
