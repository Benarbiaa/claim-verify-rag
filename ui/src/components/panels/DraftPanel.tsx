import { useEffect, useRef, useState } from 'react'
import { type AnsweringState, modelsByRole, splitCitations } from '@/lib/answering'
import { formatSeconds, formatTokens, shortDoc } from '@/lib/format'
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

function CitationChip({ cite, active, onSelect }: { cite: Cited; active: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      title={`Show the passage: ${cite.filename}${cite.chunk != null ? `, chunk #${cite.chunk}` : ''}`}
      className={cn(
        'mx-0.5 inline-flex translate-y-[-0.08em] items-center gap-1 rounded-[5px] border px-1.5 py-px align-baseline text-[0.78em] font-semibold whitespace-nowrap transition-[background-color,border-color,transform] duration-150 ease-out active:scale-[0.96]',
        active ? 'border-supported bg-supported-wash text-supported-ink' : 'border-rule-strong bg-sheet text-ink-2 hover:border-ink-3 hover:text-ink',
      )}
    >
      {shortDoc(cite.filename)}
      {cite.chunk != null && <span className="figures font-normal opacity-80">#{cite.chunk}</span>}
    </button>
  )
}

export function DraftPanel({ state }: { state: AnsweringState }) {
  const [selected, setSelected] = useState<Cited | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!selected) return
    listRef.current
      ?.querySelector(`[data-passage="${CSS.escape(`${selected.filename}#${selected.chunk ?? ''}`)}"], [data-doc="${CSS.escape(selected.filename)}"]`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selected])

  const draft = state.draft
  if (!draft)
    return (
      <>
        <PanelHeading title="Draft">The drafter writes an answer from the retrieved passages, citing each one it uses.</PanelHeading>
        <Pending label="Writing the draft" />
      </>
    )

  const stage = state.stages.find((s) => s.id === 'draft')!
  const model = modelsByRole(state.config).draft
  const words = draft.text.split(/\s+/).filter(Boolean).length
  const isSelected = (filename: string, chunk?: number) =>
    selected?.filename === filename && (selected.chunk == null || selected.chunk === chunk)

  const blocks = draft.text.split(/\n{2,}/)
  return (
    <>
      <PanelHeading
        title="The draft answer"
        aside={
          <p className="figures text-xs text-ink-3">
            {model} · {words} words · {formatTokens(stage.usage.tokens_in + stage.usage.tokens_out)} tokens · {formatSeconds(stage.seconds)}
          </p>
        }
      >
        Written by the drafter from the passages on the right. Its citations are only a starting point: each sentence is
        checked again against every source in the next steps. Click a citation to see its passage.
      </PanelHeading>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <article className="max-w-[70ch] text-[1.05rem] leading-[1.7] text-ink">
          {blocks.map((block, i) => {
            const lines = block.split('\n')
            const bullets = lines.every((l) => /^\s*[*-]\s+/.test(l))
            const render = (text: string) =>
              splitCitations(text).map((piece, j) =>
                piece.kind === 'text' ? (
                  <Inline key={j} text={piece.text} />
                ) : (
                  <CitationChip
                    key={j}
                    cite={piece}
                    active={isSelected(piece.filename, piece.chunk)}
                    onSelect={() => setSelected(isSelected(piece.filename, piece.chunk) ? null : piece)}
                  />
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
        <aside aria-label="Passages given to the drafter" className="min-w-0">
          <h3 className="mb-2 text-sm font-bold text-ink-2">Passages given to the drafter ({draft.passages.length})</h3>
          <div ref={listRef} className="flex max-h-[min(60vh,40rem)] flex-col gap-2 overflow-y-auto pr-1">
            {draft.passages.map((p) => (
              <div key={`${p.filename}#${p.chunk_index}`} data-passage={`${p.filename}#${p.chunk_index}`} data-doc={p.filename}>
                <PassageBlock passage={p} showDoc lines={3} highlight={isSelected(p.filename, p.chunk_index)} />
              </div>
            ))}
          </div>
        </aside>
      </div>
    </>
  )
}
