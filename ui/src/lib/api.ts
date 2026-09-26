import { useQuery } from '@tanstack/react-query'
import type { LiveInfo, RunDetail, RunSummary } from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new ApiError(0, 'The API is not reachable. Start it with: python -m claimverify.api.server')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, body?.detail ?? `${response.status} ${response.statusText}`)
  }
  return response.json()
}

export const useRuns = () =>
  useQuery({ queryKey: ['runs'], queryFn: () => request<RunSummary[]>('/api/runs'), refetchInterval: 15_000 })

export const useRun = (runId: string | undefined) =>
  useQuery({
    queryKey: ['run', runId],
    queryFn: () => request<RunDetail>(`/api/runs/${runId}`),
    enabled: !!runId,
    staleTime: Infinity,
  })

export const useLiveInfo = () => useQuery({ queryKey: ['live'], queryFn: () => request<LiveInfo>('/api/live') })

export const startLiveRun = (question: string, configFile: string) =>
  request<{ run_id: string }>('/api/live', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, config_file: configFile }),
  })
