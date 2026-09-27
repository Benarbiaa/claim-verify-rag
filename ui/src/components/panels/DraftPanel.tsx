import { useState } from 'react'
import { type AnsweringState, splitCitations } from '@/lib/answering'
import { shortDoc } from '@/lib/format'
import { cn } from '@/lib/utils'
import { PassageBlock } from '../Passage'
import { PanelHeading, Pending } from './common'

type Cited = { filename: string; chunk?: number }

/** **bold** inside a run of text */
function Inline({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
        part.startsWith('**') && part.endsWith('**') ? (
          <strong key={i} className="font-bold text-ink">
            {part.slice(2, -2)}
          </strong>
        ) : (
          part
        ),
      )}
    </>
  )
}

export function DraftPanel({ state }: { state: AnsweringState }) {
  const [selected, setSelected] = useState<Cited | null>(null)
  const draft = state.draft
  if (!draft)
    return (
      <>
        <PanelHeading step="2" title="Answer" />
        <Pending label="Writing…" />
      </>
    )

  const same = (a: Cited | null, filename: string, chunk?: number) => a?.filename === filename && a.chunk === chunk
  const passage =
    selected &&
    (draft.passages.find((p) => p.filename === selected.filename && p.chunk_index === selected.chunk) ??
      draft.passages.find((p) => p.filename === selected.filename))

  return (
    <>
      <PanelHeading step="2" title="Answer">
        Written from the passages. Click a source tag to read it.
      </PanelHeading>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <article className="max-w-[68ch] text-[1.05rem] leading-[1.7] text-ink">
          {draft.text.split(/\n{2,}/).map((block, i) => {
            const lines = block.split('\n')
            const bullets = lines.every((l) => /^\s*[*-]\s+/.test(l))
            const render = (text: string) =>
              splitCitations(text).map((piece, j) =>
                piece.kind === 'text' ? (
                  <Inline key={j} text={piece.text} />
                ) : (
                  <button
                    key={j}
                    type="button"
                    onClick={() => setSelected(same(selected, piece.filename, piece.chunk) ? null : piece)}
                    aria-pressed={same(selected, piece.filename, piece.chunk)}
                    className={cn(
                      'mx-0.5 inline-flex translate-y-[-0.08em] items-center rounded-[5px] border px-1.5 py-px align-baseline text-[0.78em] font-semibold whitespace-nowrap transition-[background-color,border-color] duration-150',
                      same(selected, piece.filename, piece.chunk)
                        ? 'border-supported bg-supported-wash text-supported-ink'
                        : 'border-rule-strong bg-sheet text-ink-2 hover:border-ink-3 hover:text-ink',
                    )}
                  >
                    {shortDoc(piece.filename)}
                  </button>
                ),
              )
            return bullets ? (
              <ul key={i} className="my-3 list-disc space-y-2 pl-5 marker:text-ink-3">
                {lines.map((l, j) => (
                  <li key={j}>{render(l.replace(/^\s*[*-]\s+/, ''))}</li>
                ))}
              </ul>
            ) : (
              <p key={i} className="my-3 text-pretty">
                {render(block)}
              </p>
            )
          })}
        </article>
        <aside aria-label="Selected source" className="min-w-0 lg:pt-3">
          {passage ? (
            <PassageBlock key={`${passage.filename}${passage.chunk_index}`} passage={passage} showDoc highlight lines={14} />
          ) : (
            <p className="rounded-lg border border-dashed border-rule-strong px-4 py-6 text-center text-sm text-ink-3">
              Click a source tag in the answer to read its passage here.
            </p>
          )}
        </aside>
      </div>
    </>
  )
}
