// The assay plate: one row per claim, one column per source document.
// Each cell says what that source did with that claim, according to the judge.

import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { type AnsweringState, type Stance, citationMismatch, documentsOf, modelsByRole, parseCitation, stanceOf } from '@/lib/answering'
import { formatSeconds, shortDoc, sourceKind } from '@/lib/format'
import { VERDICT_LABELS } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { STANCE_TEXT, StanceMark, VERDICT_TEXT, VerdictMark } from '../verdict'
import { ClaimDetail } from './ClaimDetail'
import { PanelHeading, Pending } from './common'

interface Props {
  state: AnsweringState
  selected: string | null
  onSelect: (claimId: string) => void
  /** position of the claim being judged right now (replay flight or live) */
  judging?: number | null
}

export function PlatePanel({ state, selected, onSelect, judging }: Props) {
  const reduce = useReducedMotion()
  const claims = state.claims
  if (!claims)
    return (
      <>
        <PanelHeading title="Claims">The decomposer splits the draft into short claims that can each be checked on their own.</PanelHeading>
        <Pending label="Splitting the draft into claims" />
      </>
    )

  const docs = documentsOf(state)
  const sourceTypes = new Map<string, string>()
  state.passages?.forEach((p) => sourceTypes.set(p.filename, p.source_type))
  Object.values(state.verdicts).forEach((v) => v.verdict.evidence.forEach((p) => sourceTypes.set(p.filename, p.source_type)))
  const verified = Object.keys(state.verdicts).length
  const models = modelsByRole(state.config)
  const selectedId = selected ?? claims[0]?.id
  const selectedClaim = claims.find((c) => c.id === selectedId)

  return (
    <>
      <PanelHeading
        title={
          verified === claims.length && claims.length
            ? `${claims.length} claims, each checked against every source`
            : `${claims.length} claims · ${verified} verified`
        }
        aside={<Legend />}
      >
        For each claim, the judge ({models.verify}, another model family than the drafter) searches the{' '}
        <strong className="font-bold text-ink">whole corpus</strong> again instead of trusting the draft's citation.
      </PanelHeading>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <div className="min-w-0 overflow-x-auto rounded-lg border border-rule bg-sheet">
          <table className="w-full min-w-[34rem] border-collapse text-left">
            <caption className="sr-only">Claims (rows) against source documents (columns)</caption>
            <thead>
              <tr className="border-b border-rule">
                <th scope="col" className="w-[3.2rem] py-2 pl-3 text-xs font-semibold text-ink-3">
                  #
                </th>
                <th scope="col" className="py-2 pr-3 text-xs font-semibold text-ink-3">
                  Claim
                </th>
                {docs.map((d) => (
                  <th key={d} scope="col" className="w-[4.6rem] px-1 py-2 text-center align-bottom">
                    <span className="block text-xs leading-tight font-bold" title={d}>
                      {shortDoc(d)}
                    </span>
                    <span className="block text-[0.68rem] leading-tight font-normal text-ink-3">{sourceKind(sourceTypes.get(d))}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {claims.map((claim, i) => {
                const entry = state.verdicts[claim.id]
                const isSelected = claim.id === selectedId
                const inFlight = !entry && judging === i + 1
                const cited = parseCitation(claim.cited_source)
                const mismatch = entry ? citationMismatch(entry.verdict) : null
                return (
                  <tr
                    key={claim.id}
                    onClick={() => onSelect(claim.id)}
                    className={cn(
                      'cursor-pointer border-b border-rule last:border-b-0 transition-colors duration-150',
                      isSelected ? 'bg-sunk' : 'hover:bg-sunk/50',
                    )}
                  >
                    <td className="py-2 pl-3 align-top">
                      <span className="flex items-center gap-2">
                        <span className="relative inline-flex size-5 items-center justify-center">
                          <AnimatePresence initial={false} mode="popLayout">
                            <motion.span
                              key={entry ? entry.verdict.verdict : 'pending'}
                              initial={reduce ? false : { opacity: 0, transform: 'scale(0.6)', filter: 'blur(3px)' }}
                              animate={{ opacity: 1, transform: 'scale(1)', filter: 'blur(0px)' }}
                              exit={{ opacity: 0, transform: 'scale(0.9)', transition: { duration: 0.1 } }}
                              transition={{ type: 'spring', duration: 0.4, bounce: 0.25 }}
                              className="inline-flex"
                            >
                              <VerdictMark verdict={entry ? entry.verdict.verdict : 'pending'} size={20} className={cn(inFlight && 'animate-pulse')} />
                            </motion.span>
                          </AnimatePresence>
                        </span>
                      </span>
                    </td>
                    <th scope="row" className="py-2 pr-3 align-top font-normal">
                      <button
                        type="button"
                        aria-current={isSelected || undefined}
                        className="text-left text-[0.93rem] leading-snug text-ink outline-offset-4"
                        aria-label={`Claim ${i + 1}: ${claim.claim}. ${entry ? VERDICT_TEXT[entry.verdict.verdict].label : 'Not verified yet'}.`}
                        onClick={(e) => {
                          e.stopPropagation()
                          onSelect(claim.id)
                        }}
                      >
                        <span className="line-clamp-2">{claim.claim}</span>
                      </button>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-ink-3">
                        <span className="figures">c{i + 1}</span>
                        <span>
                          {cited ? (
                            <>
                              draft cited <span className="font-semibold text-ink-2">{shortDoc(cited.filename)}</span>
                              {cited.chunk != null && <span className="figures"> #{cited.chunk}</span>}
                            </>
                          ) : (
                            'no citation in the draft'
                          )}
                        </span>
                        {mismatch && <span className="font-semibold text-ink-2 underline decoration-dotted underline-offset-2">· judge relied on other sources</span>}
                        {inFlight && <span className="font-semibold text-ink-2">· judging…</span>}
                      </span>
                    </th>
                    {docs.map((d) => {
                      const stance: Stance | null = entry ? stanceOf(entry.verdict, d) : null
                      const citedHere = cited?.filename === d
                      return (
                        <td key={d} className="px-1 py-2 text-center align-top">
                          <Cell stance={stance} cited={citedHere} doc={d} inFlight={inFlight} />
                        </td>
                      )
                    })}
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
              position={claims.indexOf(selectedClaim) + 1}
              total={claims.length}
              entry={state.verdicts[selectedClaim.id]}
              judging={judging === claims.indexOf(selectedClaim) + 1}
            />
          )}
        </div>
      </div>
      <p className="mt-4 text-xs text-ink-3">
        Verification time for {verified} claims: {formatSeconds(state.stages.find((s) => s.id === 'verify')?.seconds)}. Click a
        claim to see the evidence the judge read.
      </p>
    </>
  )
}

function Cell({ stance, cited, doc, inFlight }: { stance: Stance | null; cited: boolean; doc: string; inFlight: boolean }) {
  const label = stance ? `${shortDoc(doc)}: ${STANCE_TEXT[stance]}` : `${shortDoc(doc)}: not judged yet`
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            'relative mx-auto flex size-8 items-center justify-center rounded-full ring-1 ring-rule ring-inset',
            !stance && 'hatch',
            !stance && inFlight && 'animate-pulse',
            cited && 'rounded-md ring-[1.5px] ring-ink-3',
          )}
          aria-label={label + (cited ? ' (the source the draft cited)' : '')}
          role="img"
        >
          {stance && (
            <motion.span
              initial={{ opacity: 0, transform: 'scale(0.7)' }}
              animate={{ opacity: 1, transform: 'scale(1)' }}
              transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
              className="inline-flex"
            >
              <StanceMark stance={stance} />
            </motion.span>
          )}
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">
        {label}
        {cited && <span className="block opacity-80">Framed: the source the draft cited</span>}
      </TooltipContent>
    </Tooltip>
  )
}

function Legend() {
  return (
    <dl className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-2" aria-label="Legend">
      {(['supports', 'contradicts', 'silent', 'not_read'] as Stance[]).map((s) => (
        <div key={s} className="flex items-center gap-1.5">
          <dt>
            <StanceMark stance={s} size={13} />
          </dt>
          <dd>{{ supports: 'supports', contradicts: 'contradicts', silent: 'read, silent', not_read: 'not retrieved' }[s]}</dd>
        </div>
      ))}
      <div className="flex items-center gap-1.5">
        <dt>
          <span className="block size-3.5 rounded-[3px] ring-[1.5px] ring-ink-3 ring-inset" />
        </dt>
        <dd>cited by the draft</dd>
      </div>
    </dl>
  )
}

export function VerdictCounts({ counts }: { counts: Partial<Record<string, number>> }) {
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {VERDICT_LABELS.filter((l) => counts[l]).map((l) => (
        <span key={l} className="inline-flex items-center gap-1.5 text-sm">
          <VerdictMark verdict={l} size={15} />
          <span className="figures font-semibold">{counts[l]}</span>
          <span className="text-ink-2">{VERDICT_TEXT[l].label.toLowerCase()}</span>
        </span>
      ))}
    </span>
  )
}
