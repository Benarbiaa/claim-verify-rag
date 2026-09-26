// An indexing run: documents -> chunks -> embeddings -> stored, and a chunk explorer per document.

import { useMemo, useState } from 'react'
import { formatInt, formatRunDate, formatSeconds, plural, shortDoc, sourceKind } from '@/lib/format'
import { buildTimeline } from '@/lib/timeline'
import type { Chunk, EventOf, RunDetail } from '@/lib/types'
import { cn } from '@/lib/utils'
import { RunTimeline, type Step } from '@/components/RunTimeline'
import { FixtureNote } from '@/components/FixtureNote'
import { PanelHeading } from '@/components/panels/common'

const find = <T extends EventOf<any>['type']>(events: RunDetail['events'], type: T) =>
  events.find((e) => e.type === type) as EventOf<T> | undefined

export function IndexingRun({ detail }: { detail: RunDetail }) {
  const events = detail.events
  const timeline = useMemo(() => buildTimeline(events, 'indexing'), [events])
  const started = find(events, 'run_started')
  const loaded = find(events, 'documents_loaded')
  const built = find(events, 'chunks_built')
  const embedded = find(events, 'chunks_embedded')
  const stored = find(events, 'chunks_stored')
  const chunker = started?.config.indexing.chunker
  const [focus, setFocus] = useState('chunk')

  const chunksByDoc = useMemo(() => {
    const map = new Map<string, Chunk[]>()
    built?.chunks.forEach((c) => map.set(c.filename, [...(map.get(c.filename) ?? []), c]))
    return map
  }, [built])
  const docs = loaded?.documents ?? []
  const [selected, setSelected] = useState<{ file: string; index: number } | null>(null)
  const current =
    (selected && chunksByDoc.get(selected.file)?.find((c) => c.chunk_index === selected.index)) ?? built?.chunks[0] ?? null

  const steps: Step[] = [
    { id: 'load', label: 'Load', status: loaded ? 'done' : 'pending', figures: loaded ? [formatSeconds(loaded.seconds), plural(docs.length, 'document')] : [], span: 'load' },
    {
      id: 'chunk',
      label: 'Chunk',
      status: built ? 'done' : 'pending',
      figures: built ? [formatSeconds(built.seconds), plural(built.chunks.length, 'chunk')] : [],
      span: 'chunk',
    },
    {
      id: 'embed',
      label: 'Embed',
      status: embedded ? 'done' : 'pending',
      figures: embedded ? [formatSeconds(embedded.seconds), `${embedded.dimension} dimensions`] : [],
      note: started?.config.embedding.model,
      span: 'embed',
    },
    {
      id: 'store',
      label: 'Store',
      status: stored ? 'done' : 'pending',
      figures: stored ? [formatSeconds(stored.seconds), `${stored.count} rows`] : [],
      note: 'pgvector',
      span: 'store',
    },
  ]

  const overlapWords = chunker ? Math.floor(chunker.chunk_size * chunker.overlap_ratio) : 0

  return (
    <div className="mx-auto w-full max-w-[1760px] px-4 pt-5 pb-16 sm:px-6">
      <header className="mb-4">
        <h1 className="text-[clamp(1.35rem,1rem+1.1vw,2.1rem)] leading-tight font-extrabold tracking-[-0.025em]">
          Indexing {plural(docs.length, 'document')} into {plural(built?.chunks.length ?? 0, 'chunk')}
        </h1>
        <p className="figures mt-1.5 flex flex-wrap gap-x-3 text-xs text-ink-3">
          <span>{formatRunDate(detail.summary.run_id)}</span>
          {typeof started?.inputs.corpus_dir === 'string' && <span>{started.inputs.corpus_dir}</span>}
          <span>{detail.summary.run_id}</span>
        </p>
      </header>
      {detail.summary.source === 'fixture' && <FixtureNote />}

      <div className="mb-6 border-b border-rule pb-3">
        <RunTimeline steps={steps} timeline={timeline} reached={timeline.total} landed={[]} focused={focus} onFocus={setFocus} />
      </div>

      <PanelHeading title="Chunk explorer">
        Each document is cut into windows of {chunker?.chunk_size ?? '?'} words that overlap by{' '}
        {Math.round((chunker?.overlap_ratio ?? 0) * 100)}% ({overlapWords} words), so a sentence on a boundary is never lost. Each
        cell is one chunk, its width is its length. Select one to read it.
      </PanelHeading>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-4">
          {docs.map((d) => {
            const chunks = chunksByDoc.get(d.filename) ?? []
            const words = chunks.map((c) => c.text.split(/\s+/).length)
            return (
              <section key={d.doc_id} aria-label={d.filename}>
                <h3 className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-extrabold">{shortDoc(d.filename)}</span>
                  <span className="text-xs text-ink-3">{sourceKind(d.source_type)}</span>
                  <span className="figures text-xs text-ink-3">
                    {d.filename} · {formatInt(d.characters)} characters · {plural(chunks.length, 'chunk')}
                  </span>
                </h3>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {chunks.map((c, i) => {
                    const active = current?.chunk_id === c.chunk_id
                    return (
                      <button
                        key={c.chunk_id}
                        type="button"
                        onClick={() => setSelected({ file: c.filename, index: c.chunk_index })}
                        aria-pressed={active}
                        aria-label={`${shortDoc(c.filename)} chunk ${c.chunk_index}, ${words[i]} words`}
                        className={cn(
                          'figures h-8 rounded-[4px] text-[0.68rem] transition-[background-color,transform,color] duration-150 ease-out active:scale-[0.95]',
                          active ? 'bg-ink text-sheet' : 'bg-sunk text-ink-3 hover:bg-rule hover:text-ink',
                        )}
                        style={{ width: `${Math.max(1.6, (words[i] / (chunker?.chunk_size ?? 512)) * 3.2)}rem` }}
                      >
                        {c.chunk_index}
                      </button>
                    )
                  })}
                </div>
              </section>
            )
          })}
        </div>
        {current && (
          <article className="rounded-lg border border-rule bg-sheet p-4 xl:sticky xl:top-16" aria-label="Selected chunk">
            <h3 className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-lg font-extrabold">
                {shortDoc(current.filename)} · chunk #{current.chunk_index}
              </span>
              <span className="figures text-xs text-ink-3">
                {current.chunk_id} · {current.text.split(/\s+/).length} words
              </span>
            </h3>
            <ChunkText chunk={current} overlap={current.chunk_index > 0 ? overlapWords : 0} />
          </article>
        )}
      </div>
    </div>
  )
}

function ChunkText({ chunk, overlap }: { chunk: Chunk; overlap: number }) {
  const words = chunk.text.split(/(\s+)/)
  // split() keeps the separators: word i sits at index 2i
  const cut = overlap * 2
  return (
    <div className="mt-3 max-h-[60vh] overflow-y-auto pr-1">
      {overlap > 0 && <p className="mb-1 text-xs text-ink-3">The first {overlap} words are shared with the previous chunk (shaded).</p>}
      <p className="text-sm leading-relaxed text-ink-2 [overflow-wrap:anywhere]">
        {overlap > 0 && <span className="rounded-sm bg-sunk text-ink-3">{words.slice(0, cut).join('')}</span>}
        {words.slice(overlap > 0 ? cut : 0).join('')}
      </p>
    </div>
  )
}
