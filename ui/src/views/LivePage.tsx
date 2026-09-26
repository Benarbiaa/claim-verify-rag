// Live mode: ask a real question. This is the only place in the UI that spends API quota,
// so the expected cost is shown before anything starts.

import { AlertTriangle, Coins, Play } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { startLiveRun, useLiveInfo, useRuns } from '@/lib/api'
import { formatInt, formatSeconds, formatTokens } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Notice } from '@/components/Notice'

// eval/smoke_questions.txt: one question per axis of the corpus
const EXAMPLES = [
  'Does semantic chunking improve retrieval performance compared to fixed-size chunking?',
  'What is the original definition of Retrieval-Augmented Generation?',
  'How does contextual retrieval reduce retrieval failure rate?',
  'What chunking method does LumberChunker use?',
]

export function LivePage() {
  const { data: info, error, isLoading } = useLiveInfo()
  const { data: runs } = useRuns()
  const navigate = useNavigate()
  const [question, setQuestion] = useState('')
  const [chosenConfig, setConfigFile] = useState<string>('')
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  // default: the first experiment config (tuned to the free tier's per-minute limits)
  const configFile =
    chosenConfig || (info?.configs?.find((c) => !c.error && c.file.startsWith('experiments/')) ?? info?.configs?.[0])?.file || ''

  if (isLoading) return <Notice title="Loading…" />
  if (error) return <Notice title="The API is not reachable" tone="error" body={(error as Error).message} />
  if (!info?.enabled)
    return (
      <Notice
        title="Live mode is turned off"
        body="The server was started with --no-live: this UI can only replay recorded runs, and cannot spend API quota."
        action={<Link to="/runs">Open a recorded run</Link>}
      />
    )

  const config = info.configs?.find((c) => c.file === configFile)
  const estimate = info.estimate!
  const recorded = (runs ?? []).filter((r) => r.pipeline === 'answering' && r.status === 'finished' && r.source === 'recorded')
  const typicalSeconds = recorded.length
    ? recorded.reduce((sum, r) => sum + (r.seconds ?? 0) / Math.max(1, r.questions?.length ?? 1), 0) / recorded.length
    : null
  const blockers = [
    ...(config?.error ? [`This config file is invalid: ${config.error}`] : []),
    ...(config?.missing_keys?.length ? [`Missing API key in .env: ${config.missing_keys.join(', ')}`] : []),
    ...(!info.database_configured ? ['DB_URL is not set in .env: the retriever needs the database.'] : []),
  ]
  const canStart = question.trim().length > 0 && !blockers.length && !starting && !info.running

  async function start() {
    setStarting(true)
    setStartError(null)
    try {
      const { run_id } = await startLiveRun(question.trim(), configFile)
      navigate(`/runs/${run_id}?live=1`)
    } catch (e) {
      setStartError((e as Error).message)
      setStarting(false)
    }
  }

  return (
    <div className="mx-auto grid w-full max-w-[1200px] gap-10 px-4 pt-8 pb-16 sm:px-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (canStart) start()
        }}
      >
        <h1 className="text-2xl font-extrabold tracking-[-0.025em]">Ask the corpus a question</h1>
        <p className="mt-1 text-ink-2 text-pretty">
          This runs the real pipeline: retrieval on your database, then the drafter, the decomposer and the judge through the API.
          The page follows each stage as it finishes.
        </p>

        <label htmlFor="question" className="mt-6 block text-sm font-bold">
          Question
        </label>
        <textarea
          id="question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          placeholder="e.g. Does semantic chunking improve retrieval performance?"
          className="mt-1.5 w-full resize-y rounded-lg border border-rule-strong bg-sheet px-3 py-2.5 text-[1.05rem] leading-snug text-ink placeholder:text-ink-3 focus:border-focus focus:outline-none focus-visible:outline-2"
        />
        <p className="mt-2 text-xs text-ink-3">The corpus and prompts are in English: ask in English.</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {EXAMPLES.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setQuestion(q)}
              className="rounded-md bg-sunk px-2.5 py-1 text-left text-xs text-ink-2 transition-[background-color,color,transform] duration-150 ease-out hover:bg-rule hover:text-ink active:scale-[0.98]"
            >
              {q}
            </button>
          ))}
        </div>

        <label htmlFor="config" className="mt-6 block text-sm font-bold">
          Configuration
        </label>
        <select
          id="config"
          value={configFile}
          onChange={(e) => setConfigFile(e.target.value)}
          className="figures mt-1.5 w-full rounded-lg border border-rule-strong bg-sheet px-3 py-2 text-sm text-ink"
        >
          {info.configs?.map((c) => (
            <option key={c.file} value={c.file}>
              {c.file}
            </option>
          ))}
        </select>
        {config?.models && (
          <p className="figures mt-1.5 text-xs text-ink-3">
            draft {config.models.draft} · decompose {config.models.decompose} · judge {config.models.verify}
          </p>
        )}

        {blockers.length > 0 && (
          <ul className="mt-4 space-y-1.5 rounded-lg bg-error-wash px-4 py-3 text-sm text-ink">
            {blockers.map((b) => (
              <li key={b} className="flex gap-2">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-error-ink" aria-hidden />
                {b}
              </li>
            ))}
          </ul>
        )}
        {info.running && (
          <p className="mt-4 text-sm text-ink-2">
            A live run is already in progress.{' '}
            <Link to={`/runs/${info.running}?live=1`} className="font-semibold underline">
              Follow it
            </Link>
          </p>
        )}
        {startError && (
          <p role="alert" className="mt-4 rounded-lg bg-error-wash px-4 py-3 text-sm text-ink">
            {startError}
          </p>
        )}

        <button
          type="submit"
          disabled={!canStart}
          className={cn(
            'mt-6 inline-flex h-12 items-center gap-2.5 rounded-xl bg-ink px-6 text-base font-bold text-sheet shadow-lift transition-[transform,opacity] duration-150 ease-out active:scale-[0.97]',
            !canStart && 'cursor-not-allowed opacity-40 shadow-none',
          )}
        >
          <Play className="size-4 fill-current" />
          {starting ? 'Starting…' : `Run it (about ${formatTokens(estimate.tokens_per_question)} tokens)`}
        </button>
      </form>

      <aside aria-labelledby="cost" className="self-start rounded-lg border border-rule bg-sheet p-5">
        <h2 id="cost" className="flex items-center gap-2 text-base font-extrabold">
          <Coins className="size-4 text-ink-3" aria-hidden />
          What it costs
        </h2>
        <dl className="mt-3 space-y-3 text-sm">
          <div>
            <dt className="text-ink-3">Tokens per question</dt>
            <dd className="figures text-xl font-semibold">~{formatInt(estimate.tokens_per_question)}</dd>
            <dd className="text-xs text-ink-3">
              {estimate.basis_runs
                ? `Average of ${estimate.basis_runs} recorded run${estimate.basis_runs > 1 ? 's' : ''}; most of it is the judge (one call per claim).`
                : 'Rough estimate: no recorded run to measure yet.'}
            </dd>
          </div>
          {typicalSeconds != null && (
            <div>
              <dt className="text-ink-3">Typical duration</dt>
              <dd className="figures text-xl font-semibold">{formatSeconds(typicalSeconds)}</dd>
              <dd className="text-xs text-ink-3">Mostly waiting on the per-minute rate limit. Waits are shown live with a countdown.</dd>
            </div>
          )}
          <div>
            <dt className="text-ink-3">Daily limit</dt>
            <dd className="text-sm text-ink-2">{estimate.daily_limit_note}</dd>
          </div>
        </dl>
        <p className="mt-4 border-t border-rule pt-3 text-xs text-ink-3 text-pretty">
          If the provider asks to wait longer than the config's max_wait_seconds (a daily limit), or a request is too large, the
          run stops with an explanation. Everything done until then is recorded.
        </p>
      </aside>
    </div>
  )
}
