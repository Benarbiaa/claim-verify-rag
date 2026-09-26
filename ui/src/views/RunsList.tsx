import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useRuns } from '@/lib/api'
import { formatRunDate, formatSeconds, formatTokens, plural } from '@/lib/format'
import { type RunSummary, VERDICT_LABELS } from '@/lib/types'
import { cn } from '@/lib/utils'
import { FixtureTag } from '@/components/FixtureNote'
import { Notice } from '@/components/Notice'
import { VERDICT_TEXT, VerdictMark } from '@/components/verdict'

type Filter = 'all' | 'answering' | 'indexing'

export function RunsList() {
  const { data, error, isLoading } = useRuns()
  const [filter, setFilter] = useState<Filter>('all')
  const navigate = useNavigate()

  if (isLoading) return <Notice title="Loading runs…" />
  if (error) return <Notice title="The runs could not be loaded" tone="error" body={(error as Error).message} />
  const runs = (data ?? []).filter((r) => filter === 'all' || r.pipeline === filter)
  const longest = Math.max(1, ...runs.map((r) => r.seconds ?? 0))

  return (
    <div className="mx-auto w-full max-w-[1760px] px-4 pt-6 pb-16 sm:px-6">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-[-0.025em]">Runs</h1>
          <p className="mt-1 text-sm text-ink-2">
            Every pipeline run recorded in <span className="figures">runs/</span>. Opening one replays it from its events, with no API
            call.
          </p>
        </div>
        <div role="radiogroup" aria-label="Show" className="flex rounded-lg bg-sunk p-0.5 text-sm">
          {(['all', 'answering', 'indexing'] as Filter[]).map((f) => (
            <button
              key={f}
              role="radio"
              aria-checked={filter === f}
              onClick={() => setFilter(f)}
              className={cn(
                'rounded-md px-3 py-1 font-semibold text-ink-2 capitalize transition-colors duration-150',
                filter === f && 'bg-sheet text-ink shadow-[0_1px_2px_rgb(0_0_0/0.12)]',
              )}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {runs.length === 0 ? (
        <div className="rounded-lg border border-dashed border-rule-strong px-6 py-10 text-ink-2">
          <p className="font-bold text-ink">No runs yet.</p>
          <p className="mt-1 text-sm">
            Index the corpus, then answer a question from the terminal or from{' '}
            <Link to="/live" className="font-semibold underline">
              Ask a question
            </Link>
            :
          </p>
          <pre className="figures mt-3 overflow-x-auto rounded-md bg-sunk p-3 text-xs text-ink-2">
            python -m claimverify.indexing.ingest --corpus_dir ./data/corpus{'\n'}python -m claimverify.answering.pipeline --query "…"
          </pre>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-rule bg-sheet">
          <table className="w-full min-w-[56rem] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-rule text-xs text-ink-3">
                <th scope="col" className="py-2.5 pl-4 font-semibold">
                  Run
                </th>
                <th scope="col" className="py-2.5 pr-4 font-semibold">
                  Question or corpus
                </th>
                <th scope="col" className="py-2.5 pr-4 font-semibold">
                  Result
                </th>
                <th scope="col" className="py-2.5 pr-4 font-semibold">
                  Duration <span className="font-normal">(hatched: waiting)</span>
                </th>
                <th scope="col" className="py-2.5 pr-4 text-right font-semibold">
                  Tokens
                </th>
                <th scope="col" className="py-2.5 pr-4 font-semibold">
                  Config
                </th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.run_id}
                  onClick={() => navigate(`/runs/${run.run_id}`)}
                  className="cursor-pointer border-b border-rule align-top transition-colors duration-150 last:border-0 hover:bg-sunk/60"
                >
                  <td className="py-3 pl-4 pr-4">
                    <Link to={`/runs/${run.run_id}`} className="font-bold whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      {formatRunDate(run.run_id)}
                    </Link>
                    <span className="mt-0.5 flex items-center gap-2 text-xs text-ink-3">
                      <span className="capitalize">{run.pipeline}</span>
                      <Status run={run} />
                      {run.source === 'fixture' && <FixtureTag />}
                    </span>
                  </td>
                  <td className="max-w-[44ch] py-3 pr-4">
                    {run.pipeline === 'answering' ? (
                      <span className="line-clamp-2 text-ink">{run.questions?.join(' · ') || '–'}</span>
                    ) : (
                      <span className="text-ink">
                        <span className="figures">{run.corpus_dir ?? 'corpus'}</span>
                      </span>
                    )}
                  </td>
                  <td className="py-3 pr-4">
                    <Result run={run} />
                  </td>
                  <td className="py-3 pr-4">
                    <Duration run={run} longest={longest} />
                  </td>
                  <td className="figures py-3 pr-4 text-right whitespace-nowrap">
                    {run.usage?.calls ? formatTokens(run.usage.tokens_in + run.usage.tokens_out) : '–'}
                    {run.usage?.retries ? <span className="block text-xs text-ink-3">{plural(run.usage.retries, 'retry', 'retries')}</span> : null}
                  </td>
                  <td className="figures py-3 pr-4 text-xs text-ink-2">{run.config_file ?? '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Status({ run }: { run: RunSummary }) {
  if (run.status === 'finished') return null
  const text = { running: 'running', incomplete: 'stopped before the end', failed: 'failed', unreadable: 'unreadable' }[run.status]
  return <span className={cn('font-semibold', run.status === 'running' ? 'text-supported-ink' : 'text-error-ink')}>{text}</span>
}

function Result({ run }: { run: RunSummary }) {
  if (run.pipeline === 'indexing')
    return (
      <span className="text-ink-2">
        {run.documents != null ? plural(run.documents, 'document') : '–'} → {run.chunks != null ? plural(run.chunks, 'chunk') : '–'}
      </span>
    )
  const counts = run.verdict_counts ?? {}
  const total = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0)
  if (!total) return <span className="text-ink-3">no verdict</span>
  return (
    <span className="flex flex-col gap-1">
      <span className="flex flex-wrap gap-0.5" aria-hidden>
        {VERDICT_LABELS.flatMap((l) => Array.from({ length: counts[l] ?? 0 }, (_, i) => <VerdictMark key={`${l}${i}`} verdict={l} size={13} />))}
      </span>
      <span className="text-xs text-ink-2">
        {VERDICT_LABELS.filter((l) => counts[l])
          .map((l) => `${counts[l]} ${VERDICT_TEXT[l].label.toLowerCase()}`)
          .join(', ')}
      </span>
    </span>
  )
}

function Duration({ run, longest }: { run: RunSummary; longest: number }) {
  const seconds = run.seconds ?? 0
  const waited = Math.min(seconds, run.usage?.waited_seconds ?? 0)
  return (
    <span className="flex flex-col gap-1">
      <span className="relative block h-2 w-40 max-w-full rounded-sm bg-sunk" aria-hidden>
        <span className="absolute inset-y-0 left-0 rounded-sm bg-ink-2" style={{ width: `${(seconds / longest) * 100}%` }}>
          {waited > 0 && <span className="hatch absolute inset-y-0 right-0 bg-sheet" style={{ width: `${(waited / seconds) * 100}%` }} />}
        </span>
      </span>
      <span className="figures text-xs text-ink-2">
        {formatSeconds(seconds)}
        {waited > 0 && <span className="text-ink-3"> · {formatSeconds(waited)} waiting</span>}
      </span>
    </span>
  )
}
