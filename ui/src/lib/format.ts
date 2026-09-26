export function formatSeconds(s: number | undefined | null): string {
  if (s == null || Number.isNaN(s)) return '–'
  if (s < 10) return `${s.toFixed(1)} s`
  if (s < 60) return `${Math.round(s)} s`
  const m = Math.floor(s / 60)
  const rest = Math.round(s - m * 60)
  return rest ? `${m} min ${rest} s` : `${m} min`
}

export function formatTokens(n: number | undefined | null): string {
  if (n == null) return '–'
  if (n < 1000) return `${n}`
  return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}K`
}

export const formatInt = (n: number) => n.toLocaleString('en-US')

/** "vectara-semantic-chunking-naacl2025.pdf" -> "Vectara" (the plate's column header). */
export function shortDoc(filename: string): string {
  const stem = filename.replace(/\.[a-z0-9]+$/i, '')
  const first = stem.split(/[-_\s]/)[0]
  if (first === first.toUpperCase()) return first
  return first.charAt(0).toUpperCase() + first.slice(1)
}

export function sourceKind(sourceType: string | undefined): string {
  if (!sourceType) return 'source'
  if (sourceType === 'peer_reviewed_paper') return 'paper'
  if (sourceType === 'blog_post') return 'blog post'
  return sourceType.replace(/_/g, ' ')
}

/** "20260926_155834_answering" -> Date (UTC, as the run ids are) */
export function runDate(runId: string): Date | null {
  const m = runId.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/)
  if (!m) return null
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]))
}

export function formatRunDate(runId: string): string {
  const d = runDate(runId)
  if (!d) return runId
  return d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`
}

/** "llm_judge:qwen/qwen3.8-27b" -> "qwen/qwen3.8-27b" */
export const modelOf = (verifier: string) => verifier.replace(/^[a-z_]+:/, '')

/** Model family, to show that the judge is not the drafter. */
export function familyOf(model: string | undefined): string {
  if (!model) return ''
  const vendor = model.split('/')[0].toLowerCase()
  const families: Record<string, string> = {
    openai: 'OpenAI',
    qwen: 'Alibaba Qwen',
    'meta-llama': 'Meta Llama',
    google: 'Google',
    mistralai: 'Mistral',
    deepseek: 'DeepSeek',
    moonshotai: 'Moonshot',
  }
  return families[vendor] ?? vendor
}
