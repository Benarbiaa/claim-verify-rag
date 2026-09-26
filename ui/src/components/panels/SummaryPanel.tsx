import { type AnsweringState, STAGES, modelsByRole, totalUsage } from '@/lib/answering'
import { familyOf, formatInt, formatSeconds, formatTokens, plural } from '@/lib/format'
import { type Timeline, sumSegments } from '@/lib/timeline'
import { VERDICT_LABELS, type VerdictLabel } from '@/lib/types'
import { VERDICT_TEXT, VerdictMark } from '../verdict'
import { PanelHeading, Pending } from './common'

export function SummaryPanel({ state, timeline }: { state: AnsweringState; timeline: Timeline }) {
  const verdicts = Object.values(state.verdicts).sort((a, b) => a.position - b.position)
  if (!state.claims)
    return (
      <>
        <PanelHeading title="Summary" />
        <Pending label="Available once the claims are verified" />
      </>
    )

  const counts = Object.fromEntries(VERDICT_LABELS.map((l) => [l, verdicts.filter((v) => v.verdict.verdict === l).length])) as Record<
    VerdictLabel,
    number
  >
  const total = timeline.total
  const waited = sumSegments(timeline.segments, 'wait')
  const verifyWait = sumSegments(timeline.segments, 'wait', 'verify')
  const verifySeconds = state.stages.find((s) => s.id === 'verify')!.seconds
  const usage = totalUsage(state)
  const models = modelsByRole(state.config)
  const sameFamily = familyOf(models.draft) === familyOf(models.verify)
  const a = state.config?.answering

  return (
    <>
      <PanelHeading title={state.finished ? 'Summary' : 'Summary so far'} />
      <div className="grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <section aria-labelledby="sum-verdicts">
          <h3 id="sum-verdicts" className="mb-3 text-base font-extrabold">
            {plural(verdicts.length, 'verdict')}
            {state.claims.length > verdicts.length && <span className="font-normal text-ink-3"> of {state.claims.length} claims</span>}
          </h3>
          <div className="flex flex-wrap gap-1.5" aria-hidden>
            {verdicts.map((v) => (
              <span key={v.position} title={`Claim ${v.position}: ${v.verdict.verdict}`}>
                <VerdictMark verdict={v.verdict.verdict} size={26} />
              </span>
            ))}
          </div>
          <dl className="mt-4 grid grid-cols-[auto_auto_1fr] items-center gap-x-3 gap-y-2">
            {VERDICT_LABELS.map((l) => (
              <div key={l} className="contents">
                <dt className="flex items-center gap-2">
                  <VerdictMark verdict={l} size={16} />
                  <span className={`text-sm font-bold ${VERDICT_TEXT[l].ink}`}>{VERDICT_TEXT[l].label}</span>
                </dt>
                <dd className="figures text-right text-sm font-semibold">{counts[l]}</dd>
                <dd className="text-xs text-ink-3">{VERDICT_TEXT[l].meaning}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section aria-labelledby="sum-time">
          <h3 id="sum-time" className="mb-1 text-base font-extrabold">
            {formatSeconds(total)} in total, {total ? Math.round((waited / total) * 100) : 0}% of it waiting
          </h3>
          <p className="mb-3 text-sm text-ink-2 text-pretty">
            {verifyWait > 0 ? (
              <>
                Verification took {formatSeconds(verifySeconds)}, of which {formatSeconds(verifyWait)} was spent waiting on the
                provider's per-minute rate limit (free tier), not computing.
              </>
            ) : (
              'No rate-limit waits in this run.'
            )}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-rule text-left text-xs text-ink-3">
                  <th scope="col" className="py-1.5 pr-3 font-semibold">
                    Stage
                  </th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-semibold">
                    Time
                  </th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-semibold">
                    Waiting
                  </th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-semibold">
                    Calls
                  </th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-semibold">
                    Tokens in / out
                  </th>
                  <th scope="col" className="py-1.5 text-right font-semibold">
                    Retries
                  </th>
                </tr>
              </thead>
              <tbody className="figures">
                {STAGES.filter((s) => s.id !== 'done').map((s) => {
                  const st = state.stages.find((x) => x.id === s.id)!
                  const wait = sumSegments(timeline.segments, 'wait', s.id)
                  return (
                    <tr key={s.id} className="border-b border-rule last:border-0">
                      <th scope="row" className="py-1.5 pr-3 text-left font-sans font-bold">
                        {s.label}
                        {s.role && <span className="block font-sans text-xs font-normal text-ink-3">{models[s.role]}</span>}
                      </th>
                      <td className="py-1.5 pr-3 text-right">{formatSeconds(st.seconds)}</td>
                      <td className="py-1.5 pr-3 text-right">{wait ? <WaitCell seconds={wait} of={st.seconds} /> : '–'}</td>
                      <td className="py-1.5 pr-3 text-right">{st.usage.calls || '–'}</td>
                      <td className="py-1.5 pr-3 text-right">
                        {st.usage.calls ? `${formatInt(st.usage.tokens_in)} / ${formatInt(st.usage.tokens_out)}` : '–'}
                      </td>
                      <td className="py-1.5 text-right">{st.usage.retries || '–'}</td>
                    </tr>
                  )
                })}
                <tr className="border-t-2 border-rule-strong">
                  <th scope="row" className="py-1.5 pr-3 text-left font-sans font-bold">
                    Total
                  </th>
                  <td className="py-1.5 pr-3 text-right font-semibold">{formatSeconds(total)}</td>
                  <td className="py-1.5 pr-3 text-right font-semibold">{waited ? formatSeconds(waited) : '–'}</td>
                  <td className="py-1.5 pr-3 text-right font-semibold">{usage.calls}</td>
                  <td className="py-1.5 pr-3 text-right font-semibold">
                    {formatTokens(usage.tokens_in)} / {formatTokens(usage.tokens_out)}
                  </td>
                  <td className="py-1.5 text-right font-semibold">{usage.retries}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section aria-labelledby="sum-models">
          <h3 id="sum-models" className="mb-3 text-base font-extrabold">
            Models
          </h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            {(['draft', 'decompose', 'verify'] as const).map((role) => (
              <div key={role} className="contents">
                <dt className="font-bold capitalize">{role === 'verify' ? 'Judge' : role === 'draft' ? 'Drafter' : 'Decomposer'}</dt>
                <dd>
                  <span className="figures">{models[role] ?? '–'}</span>
                  <span className="text-ink-3"> · {familyOf(models[role])}</span>
                </dd>
              </div>
            ))}
            <dt className="font-bold">Embedder</dt>
            <dd className="figures">{state.config?.embedding.model ?? '–'}</dd>
          </dl>
          <p className="mt-3 text-sm text-ink-2 text-pretty">
            {sameFamily
              ? 'Warning: the judge comes from the same model family as the drafter.'
              : 'The judge comes from a different model family than the drafter, so it is not grading its own writing.'}
          </p>
        </section>

        <section aria-labelledby="sum-config">
          <h3 id="sum-config" className="mb-3 text-base font-extrabold">
            Configuration
          </h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="font-bold">File</dt>
            <dd className="figures">{state.configFile ?? '–'}</dd>
            <dt className="font-bold">Draft retrieval</dt>
            <dd>top {a?.retriever.top_k_per_doc ?? '?'} passages per document</dd>
            <dt className="font-bold">Claim retrieval</dt>
            <dd>top {a?.verifier.retriever.top_k_per_doc ?? '?'} per document, for each claim</dd>
            <dt className="font-bold">Chunks</dt>
            <dd>
              {state.config?.indexing.chunker.chunk_size ?? '?'} words, {Math.round((state.config?.indexing.chunker.overlap_ratio ?? 0) * 100)}%
              overlap
            </dd>
          </dl>
          {state.config && (
            <details className="group mt-3">
              <summary className="cursor-pointer list-none text-sm font-semibold text-ink-2 transition-colors hover:text-ink">
                Full configuration snapshot <span className="text-ink-3 group-open:hidden">(show)</span>
              </summary>
              <pre className="figures mt-2 max-h-80 overflow-auto rounded-md bg-sunk p-3 text-xs leading-relaxed text-ink-2">
                {JSON.stringify(state.config, null, 2)}
              </pre>
            </details>
          )}
        </section>
      </div>
    </>
  )
}

function WaitCell({ seconds, of }: { seconds: number; of: number }) {
  const share = of ? Math.min(1, seconds / of) : 0
  return (
    <span className="inline-flex items-center justify-end gap-2">
      <span className="relative hidden h-2 w-10 overflow-hidden rounded-sm bg-sunk sm:inline-block" aria-hidden>
        <span className="hatch absolute inset-y-0 left-0" style={{ width: `${share * 100}%` }} />
      </span>
      {formatSeconds(seconds)}
    </span>
  )
}
