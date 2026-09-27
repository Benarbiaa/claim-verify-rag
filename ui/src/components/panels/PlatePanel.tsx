// The fact-check grid: one row per claim, one column per source document.
// A cell says whether that source supports or contradicts the claim.

import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { type AnsweringState, type Stance, documentsOf, stanceOf } from '@/lib/answering'
import { shortDoc } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { StanceMark, VERDICT_TEXT, VerdictMark } from '../verdict'
import { ClaimDetail } from './ClaimDetail'
import { PanelHeading, Pending } from './common'

interface Props {
  state: AnsweringState
  selected: string | null
  onSelect: (claimId: string) => void
  /** position of the claim being checked right now (replay or live) */
  judging?: number | null
}

export function PlatePanel({ state, selected, onSelect, judging }: Props) {
  const reduce = useReducedMotion()
  const claims = state.claims
  if (!claims)
    return (
      <>
        <PanelHeading step="3" title="Fact-check" />
        <Pending label="Splitting the answer into claims…" />
      </>
    )

  const docs = documentsOf(state)
  const selectedId = selected ?? claims[0]?.id
  const selectedClaim = claims.find((c) => c.id === selectedId)

  return (
    <>
      <PanelHeading step="3–4" title="Fact-check" aside={<Legend />}>
        Each row is a claim from the answer, each column a source. Click a row to see why.
      </PanelHeading>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <div className="min-w-0 overflow-x-auto rounded-lg border border-rule bg-sheet">
          <table className="w-full min-w-[32rem] border-collapse text-left">
            <caption className="sr-only">Claims (rows) against source documents (columns)</caption>
            <thead>
              <tr className="border-b border-rule text-xs text-ink-3">
                <th scope="col" className="py-2 pl-4 font-semibold" colSpan={2}>
                  Claim
                </th>
                {docs.map((d) => (
                  <th key={d} scope="col" className="w-[4.5rem] px-1 py-2 text-center font-bold text-ink-2" title={d}>
                    {shortDoc(d)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {claims.map((claim, i) => {
                const entry = state.verdicts[claim.id]
                const isSelected = claim.id === selectedId
                const inFlight = !entry && judging === i + 1
                return (
                  <tr
                    key={claim.id}
                    onClick={() => onSelect(claim.id)}
                    className={cn(
                      'cursor-pointer border-b border-rule transition-colors duration-150 last:border-b-0',
                      isSelected ? 'bg-sunk' : 'hover:bg-sunk/50',
                    )}
                  >
                    <td className="w-10 py-3 pl-4 align-top">
                      <AnimatePresence initial={false} mode="popLayout">
                        <motion.span
                          key={entry ? entry.verdict.verdict : 'pending'}
                          initial={reduce ? false : { opacity: 0, transform: 'scale(0.6)' }}
                          animate={{ opacity: 1, transform: 'scale(1)' }}
                          transition={{ type: 'spring', duration: 0.4, bounce: 0.25 }}
                          className="inline-flex"
                        >
                          <VerdictMark
                            verdict={entry ? entry.verdict.verdict : 'pending'}
                            size={20}
                            className={cn(inFlight && 'animate-pulse')}
                          />
                        </motion.span>
                      </AnimatePresence>
                    </td>
                    <th scope="row" className="py-3 pr-3 align-top font-normal">
                      <button
                        type="button"
                        aria-current={isSelected || undefined}
                        aria-label={`${claim.claim}: ${entry ? VERDICT_TEXT[entry.verdict.verdict].label : 'not checked yet'}`}
                        onClick={(e) => {
                          e.stopPropagation()
                          onSelect(claim.id)
                        }}
                        className="line-clamp-2 text-left text-[0.93rem] leading-snug text-ink outline-offset-4"
                      >
                        {claim.claim}
                      </button>
                    </th>
                    {docs.map((d) => (
                      <td key={d} className="px-1 py-3 text-center align-top">
                        <Cell stance={entry ? stanceOf(entry.verdict, d) : null} doc={d} inFlight={inFlight} />
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="min-w-0 xl:sticky xl:top-4">
          {selectedClaim && (
            <ClaimDetail
              claim={selectedClaim}
              entry={state.verdicts[selectedClaim.id]}
              judging={judging === claims.indexOf(selectedClaim) + 1}
            />
          )}
        </div>
      </div>
    </>
  )
}

const CELL_TEXT: Record<Stance, string> = {
  supports: 'supports the claim',
  contradicts: 'contradicts the claim',
  silent: 'says nothing about it',
  not_read: 'says nothing about it',
}

function Cell({ stance, doc, inFlight }: { stance: Stance | null; doc: string; inFlight: boolean }) {
  const shown = stance === 'supports' || stance === 'contradicts' ? stance : null
  const label = stance ? `${shortDoc(doc)} ${CELL_TEXT[stance]}` : `${shortDoc(doc)}: not checked yet`
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="img"
          aria-label={label}
          className={cn(
            'mx-auto flex size-7 items-center justify-center rounded-full ring-1 ring-rule ring-inset',
            !stance && 'hatch',
            !stance && inFlight && 'animate-pulse',
          )}
        >
          {shown && (
            <motion.span
              initial={{ opacity: 0, transform: 'scale(0.7)' }}
              animate={{ opacity: 1, transform: 'scale(1)' }}
              transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
              className="inline-flex"
            >
              <StanceMark stance={shown} size={15} />
            </motion.span>
          )}
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">{label}</TooltipContent>
    </Tooltip>
  )
}

function Legend() {
  return (
    <p className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-2" aria-label="Legend">
      <span className="flex items-center gap-1.5">
        <StanceMark stance="supports" size={13} /> supports
      </span>
      <span className="flex items-center gap-1.5">
        <StanceMark stance="contradicts" size={13} /> contradicts
      </span>
      <span className="flex items-center gap-1.5">
        <span className="block size-3.5 rounded-full ring-1 ring-rule-strong ring-inset" /> says nothing
      </span>
    </p>
  )
}
