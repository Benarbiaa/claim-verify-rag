// Live mode: the events of a running pipeline, pushed by the API as Server-Sent Events.

import { useEffect, useState } from 'react'
import type { PipelineEvent } from './types'

export type LiveStatus = 'connecting' | 'running' | 'finished' | 'failed' | 'lost'

export interface LiveFailure {
  kind: string
  message: string
}

export function useLiveEvents(runId: string | undefined, enabled: boolean) {
  const [events, setEvents] = useState<PipelineEvent[]>([])
  const [status, setStatus] = useState<LiveStatus>('connecting')
  const [failure, setFailure] = useState<LiveFailure | null>(null)

  useEffect(() => {
    if (!runId || !enabled) return
    setEvents([])
    setStatus('connecting')
    setFailure(null)
    const source = new EventSource(`/api/live/${runId}/stream`)
    let closed = false
    // the server sends every event again on (re)connection: start from scratch each time
    source.onopen = () => {
      setEvents([])
      setStatus('running')
    }
    source.addEventListener('pipeline', (m) => setEvents((list) => [...list, JSON.parse((m as MessageEvent).data)]))
    source.addEventListener('end', () => {
      closed = true
      setStatus('finished')
      source.close()
    })
    source.addEventListener('failed', (m) => {
      closed = true
      setFailure(JSON.parse((m as MessageEvent).data))
      setStatus('failed')
      source.close()
    })
    source.onerror = () => {
      if (closed) return
      // EventSource retries by itself; a closed source means the server no longer knows this run
      if (source.readyState === EventSource.CLOSED) setStatus('lost')
    }
    return () => source.close()
  }, [runId, enabled])

  return { events, status, failure }
}
