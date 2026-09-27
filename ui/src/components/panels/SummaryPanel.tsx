import { type AnsweringState, modelsByRole, totalUsage } from '@/lib/answering'
import { formatSeconds, formatTokens, plural } from '@/lib/format'
import { type Timeline, sumSegments } from '@/lib/timeline'
import { VERDICT_LABELS } from '@/lib/types'
import { VERDICT_TEXT, VerdictMark } from '../verdict'
import { PanelHeading, Pending } from './common'

export function SummaryPanel({ state, timeline }: { state: AnsweringState; timeline: Timeline }) {
  const verdicts = Object.values(state.verdicts)
  if (!state.claims)
    return (
      <>
        <PanelHeading step="5" title="Summary" />
        <Pending label="Available once the claims are checked" />
      </>
    )

  const total = timeline.total
  const waited = sumSegments(timeline.segments, 'wait')
  const usage = totalUsage(state)
  const models = modelsByRole(state.config)

  return (
    <>
      <PanelHeading step="5" title="Summary" />
      <div className="grid gap-6 md:grid-cols-3">
        <Block title="Verdicts">
          <ul className="space-y-1.5">
            {VERDICT_LABELS.map((l) => {
              const n = verdicts.filter((v) => v.verdict.verdict === l).length
              return (
                <li key={l} className={n ? '' : 'opacity-45'}>
                  <span className="flex items-center gap-2">
                    <VerdictMark verdict={l} size={16} />
                    <span className="figures w-5 font-bold">{n}</span>
                    <span className="text-sm">{VERDICT_TEXT[l].label.toLowerCase()}</span>
                  </span>
                </li>
              )
            })}
          </ul>
        </Block>

        <Block title="Time">
          <p className="figures text-2xl font-extrabold">{formatSeconds(total)}</p>
          {waited > 0 && (
            <>
              <div className="mt-2 flex h-2.5 overflow-hidden rounded-full bg-sunk" aria-hidden>
                <span className="bg-ink-2" style={{ width: `${((total - waited) / total) * 100}%` }} />
                <span className="hatch flex-1" />
              </div>
              <p className="mt-1.5 text-sm text-ink-2">{Math.round((waited / total) * 100)}% spent waiting on the free tier's rate limit.</p>
            </>
          )}
          <p className="figures mt-2 text-sm text-ink-3">
            {plural(usage.calls, 'LLM call')} · {formatTokens(usage.tokens_in + usage.tokens_out)} tokens
          </p>
        </Block>

        <Block title="Models">
          <dl className="space-y-1.5 text-sm">
            <div>
              <dt className="inline font-bold">Writes the answer: </dt>
              <dd className="inline">{models.draft ?? '–'}</dd>
            </div>
            <div>
              <dt className="inline font-bold">Checks the claims: </dt>
              <dd className="inline">{models.verify ?? '–'}</dd>
            </div>
          </dl>
          <p className="mt-2 text-sm text-ink-3">Two different model families, so the checker doesn't grade its own work.</p>
        </Block>
      </div>

      {state.config && (
        <details className="group mt-6">
          <summary className="cursor-pointer text-sm font-semibold text-ink-3 hover:text-ink">Technical details</summary>
          <pre className="mt-2 max-h-80 overflow-auto rounded-md bg-sunk p-3 font-mono text-xs leading-relaxed text-ink-2">
            {JSON.stringify({ config_file: state.configFile, usage_per_stage: Object.fromEntries(state.stages.map((s) => [s.id, s.usage])), config: state.config }, null, 2)}
          </pre>
        </details>
      )}
    </>
  )
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-rule bg-sheet p-5">
      <h3 className="mb-3 text-sm font-bold text-ink-3">{title}</h3>
      {children}
    </section>
  )
}
