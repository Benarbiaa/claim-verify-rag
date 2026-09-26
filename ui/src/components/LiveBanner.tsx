import { AlertOctagon, CheckCircle2, Loader2, WifiOff } from 'lucide-react'
import { Link } from 'react-router'
import type { LiveFailure, LiveStatus } from '@/lib/live'
import { cn } from '@/lib/utils'

const FAILURE_TITLE: Record<string, string> = {
  daily_limit: 'Daily limit reached',
  request_too_large: 'Request too large',
  gave_up: 'An LLM call kept failing',
  provider_error: 'The provider rejected a request',
  database: 'Database error',
  unexpected: 'The run stopped',
}

export function LiveBanner({ status, failure }: { status: LiveStatus; failure: LiveFailure | null }) {
  if (status === 'failed' && failure)
    return (
      <div role="alert" className="flex gap-3 rounded-lg bg-error-wash px-4 py-3">
        <AlertOctagon className="mt-0.5 size-5 shrink-0 text-error-ink" aria-hidden />
        <div className="text-sm">
          <p className="font-bold text-ink">{FAILURE_TITLE[failure.kind] ?? 'The run stopped'}</p>
          <p className="mt-0.5 text-ink-2">{failure.message}</p>
          <p className="mt-1 text-ink-3">Everything up to this point is recorded and can be replayed from the runs list.</p>
        </div>
      </div>
    )
  const lost = status === 'lost'
  return (
    <div className={cn('flex items-center gap-2.5 text-sm font-semibold', lost ? 'text-error-ink' : 'text-ink-2')}>
      {status === 'finished' ? (
        <CheckCircle2 className="size-4" aria-hidden />
      ) : lost ? (
        <WifiOff className="size-4" aria-hidden />
      ) : (
        <Loader2 className="size-4 animate-spin" aria-hidden />
      )}
      {status === 'connecting' && 'Connecting to the run…'}
      {status === 'running' && 'Live: the page updates as each stage finishes.'}
      {status === 'finished' && 'Finished. The run is recorded and can be replayed without API calls.'}
      {lost && (
        <>
          The server no longer knows this run (it may have restarted).{' '}
          <Link to="/runs" className="underline">
            Open the runs list
          </Link>
        </>
      )}
    </div>
  )
}
