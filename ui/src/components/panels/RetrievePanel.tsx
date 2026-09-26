import { shortDoc, sourceKind } from '@/lib/format'
import type { AnsweringState } from '@/lib/answering'
import type { Passage } from '@/lib/types'
import { PassageBlock } from '../Passage'
import { PanelHeading, Pending } from './common'

export function RetrievePanel({ state }: { state: AnsweringState }) {
  const k = state.config?.answering.retriever.top_k_per_doc
  const kVerify = state.config?.answering.verifier.retriever.top_k_per_doc
  if (!state.passages)
    return (
      <>
        <PanelHeading title="Retrieve">Searching the corpus for passages about the question…</PanelHeading>
        <Pending label="Retrieving passages" />
      </>
    )

  const groups = new Map<string, Passage[]>()
  for (const p of [...state.passages].sort((a, b) => b.score - a.score)) {
    groups.set(p.filename, [...(groups.get(p.filename) ?? []), p])
  }

  return (
    <>
      <PanelHeading title={`${state.passages.length} passages from ${groups.size} documents`}>
        The best {k ?? 'k'} passages <strong className="font-bold text-ink">from each document</strong>, not the best{' '}
        {state.passages.length} overall: every source is heard, so a paper that disagrees cannot be crowded out. The judge does
        the same for each claim{kVerify != null && <> (top {kVerify} per document)</>}.
      </PanelHeading>
      <div className="grid gap-x-5 gap-y-6" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 17rem), 1fr))' }}>
        {[...groups.entries()].map(([filename, passages]) => (
          <section key={filename} aria-label={filename} className="min-w-0">
            <header className="mb-2 border-b border-rule pb-2">
              <h3 className="flex items-baseline gap-2">
                <span className="text-base font-extrabold">{shortDoc(filename)}</span>
                <span className="text-xs text-ink-3">{sourceKind(passages[0].source_type)}</span>
              </h3>
              <p className="figures truncate text-xs text-ink-3" title={filename}>
                {filename}
              </p>
            </header>
            <div className="flex flex-col gap-2">
              {passages.map((p) => (
                <PassageBlock key={p.chunk_index} passage={p} lines={5} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  )
}
