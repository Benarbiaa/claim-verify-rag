import type { AnsweringState } from '@/lib/answering'
import { shortDoc } from '@/lib/format'
import type { Passage } from '@/lib/types'
import { PassageBlock } from '../Passage'
import { PanelHeading, Pending } from './common'

export function RetrievePanel({ state }: { state: AnsweringState }) {
  const k = state.config?.answering.retriever.top_k_per_doc
  if (!state.passages)
    return (
      <>
        <PanelHeading step="1" title="Passages found" />
        <Pending label="Searching…" />
      </>
    )

  const groups = new Map<string, Passage[]>()
  for (const p of [...state.passages].sort((a, b) => b.score - a.score)) {
    groups.set(p.filename, [...(groups.get(p.filename) ?? []), p])
  }

  return (
    <>
      <PanelHeading step="1" title="Passages found">
        The best {k ?? 'k'} from each document, so every source is heard.
      </PanelHeading>
      <div className="grid gap-x-5 gap-y-6" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 16rem), 1fr))' }}>
        {[...groups.entries()].map(([filename, passages]) => (
          <section key={filename} aria-label={filename} className="min-w-0">
            <h3 className="mb-2 truncate font-extrabold" title={filename}>
              {shortDoc(filename)}
            </h3>
            <div className="flex flex-col gap-2">
              {passages.map((p) => (
                <PassageBlock key={p.chunk_index} passage={p} lines={4} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  )
}
