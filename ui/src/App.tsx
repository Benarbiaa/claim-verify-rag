import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { useRuns } from '@/lib/api'
import { AppShell } from '@/components/AppShell'
import { Notice } from '@/components/Notice'
import { TooltipProvider } from '@/components/ui/tooltip'
import { LivePage } from '@/views/LivePage'
import { RunPage } from '@/views/RunPage'
import { RunsList } from '@/views/RunsList'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

/** The demo's first screen: the latest recorded answering run, ready to replay from the start. */
function Home() {
  const { data, error, isLoading } = useRuns()
  if (isLoading) return <Notice title="Loading…" />
  if (error) return <Notice title="The API is not reachable" tone="error" body={(error as Error).message} />
  const answering = (data ?? []).filter((r) => r.pipeline === 'answering' && r.status === 'finished')
  const latest = answering.find((r) => r.source === 'recorded') ?? answering[0]
  return <Navigate to={latest ? `/runs/${latest.run_id}?cue=0` : '/runs'} replace />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={250} skipDelayDuration={400}>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Home />} />
              <Route path="runs" element={<RunsList />} />
              <Route path="runs/:runId" element={<RunPage />} />
              <Route path="live" element={<LivePage />} />
              <Route path="*" element={<Notice title="Nothing here" back />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  )
}
