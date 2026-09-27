import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useRuns } from '@/lib/api'
import { formatRunDate, formatSeconds, plural } from '@/lib/format'
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

  return (
    <div className="mx-auto w-full max-w-[1760px] px-4 pt-6 pb-16 sm:px-6">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-[-0.025em]">Runs</h1>
          <p className="mt-1 text-sm text-ink-2">Click a run to replay it.</p>
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
            <Link to="/live" className="font-semibold underline">
              Ask a question
            </Link>{' '}
            to create one.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-rule bg-sheet">
          <table className="w-full min-w-[40rem] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-rule text-xs text-ink-3">
                <th scope="col" className="py-2.5 pl-4 font-semibold">
                  Date
                </th>
                <th scope="col" className="py-2.5 pr-4 font-semibold">
                  Question
                </th>
                <th scope="col" className="py-2.5 pr-4 font-semibold">
                  Result
                </th>
                <th scope="col" className="py-2.5 pr-4 font-semibold">
                  Duration
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
                      <Status run={run} />
                      {run.source === 'fixture' && <FixtureTag />}
                    </span>
                  </td>
                  <td className="max-w-[44ch] py-3 pr-4">
                    {run.pipeline === 'answering' ? (
                      <span className="line-clamp-2 text-ink">{run.questions?.join(' · ') || '–'}</span>
                    ) : (
                      <span className="text-ink-3">Indexing the corpus</span>
                    )}
                  </td>
                  <td className="py-3 pr-4">
                    <Result run={run} />
                  </td>
                  <td className="py-3 pr-4">
                    <Duration run={run} />
                  </td>
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
    return <span className="text-ink-2">{run.chunks != null ? plural(run.chunks, 'chunk') : '–'}</span>
  const counts = run.verdict_counts ?? {}
  const labels = VERDICT_LABELS.filter((l) => counts[l])
  if (!labels.length) return <span className="text-ink-3">–</span>
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {labels.map((l) => (
        <span key={l} className="inline-flex items-center gap-1" title={VERDICT_TEXT[l].label}>
          <VerdictMark verdict={l} size={15} />
          <span className="figures font-semibold">{counts[l]}</span>
          <span className="sr-only">{VERDICT_TEXT[l].label}</span>
        </span>
      ))}
    </span>
  )
}

function Duration({ run }: { run: RunSummary }) {
  return <span className="figures text-ink-2">{formatSeconds(run.seconds ?? 0)}</span>
}
