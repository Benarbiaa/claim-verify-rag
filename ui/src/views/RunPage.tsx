import { useEffect, useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { useRun } from '@/lib/api'
import { useLiveEvents } from '@/lib/live'
import { useReplay } from '@/lib/replay'
import { buildTimeline } from '@/lib/timeline'
import type { RunDetail } from '@/lib/types'
import { AnsweringRun } from './AnsweringRun'
import { IndexingRun } from './IndexingRun'
import { Notice } from '@/components/Notice'

export function RunPage() {
  const { runId } = useParams()
  const [params] = useSearchParams()
  const liveRequested = params.get('live') === '1'
  const { data, error, isLoading } = useRun(liveRequested ? undefined : runId)

  if (liveRequested && runId) return <LiveRun runId={runId} />
  if (isLoading) return <Notice title="Loading the run…" />
  if (error || !data) return <Notice title="This run could not be opened" tone="error" body={(error as Error)?.message} back />
  if (data.summary.status === 'running') return <LiveRun runId={data.summary.run_id} />
  if (data.summary.pipeline === 'indexing') return <IndexingRun detail={data} />
  return <ReplayRun detail={data} />
}

function ReplayRun({ detail }: { detail: RunDetail }) {
  const [params, setParams] = useSearchParams()
  const events = detail.events
  const offsets = useMemo(() => buildTimeline(events, 'answering').offsets, [events])
  const cueParam = params.get('cue')
  const initial = cueParam != null ? Math.max(0, Math.min(events.length, Number(cueParam) || 0)) : events.length
  const replay = useReplay(events, offsets, initial)

  // the position is part of the address: a paused cue can be shared or reloaded
  useEffect(() => {
    if (replay.playing) return
    const next = new URLSearchParams(params)
    if (replay.cursor >= events.length) next.delete('cue')
    else next.set('cue', String(replay.cursor))
    if (next.toString() !== params.toString()) setParams(next, { replace: true })
  }, [replay.cursor, replay.playing, events.length, params, setParams])

  if (!events.length) return <Notice title="This run has no events yet" back />
  return <AnsweringRun summary={detail.summary} events={events} replay={replay} />
}

function LiveRun({ runId }: { runId: string }) {
  const { events, status, failure } = useLiveEvents(runId, true)
  const summary = { run_id: runId, source: 'recorded', pipeline: 'answering', status: 'running' } as const
  if (status === 'lost' && !events.length)
    return (
      <Notice
        title="This live run is not running on the server"
        body="It may have finished before the server restarted. Its events are recorded: open it from the runs list to replay it."
        action={<Link to={`/runs/${runId}`}>Open the recorded run</Link>}
      />
    )
  return <AnsweringRun summary={summary} events={events} live={{ status, failure }} />
}
