import { Play } from 'lucide-react'
import { type AnsweringState, modelsByRole } from '@/lib/answering'
import { VerdictMark } from '../verdict'

export function IntroPanel({ state, onPlay }: { state: AnsweringState; onPlay?: () => void }) {
  const models = modelsByRole(state.config)
  const k = state.config?.answering.retriever.top_k_per_doc
  const steps = [
    ['Retrieve', `Search every document of the corpus and keep the best ${k ?? 'k'} passages of each.`],
    ['Draft', `${models.draft ?? 'An LLM'} writes an answer from those passages, with citations.`],
    ['Decompose', 'The answer is split into short claims that can each be checked on their own.'],
    ['Verify', `${models.verify ?? 'A judge'}, from another model family, re-checks every claim against every source.`],
  ]
  return (
    <div className="grid items-start gap-10 py-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="max-w-[46ch]">
        <p className="text-[clamp(1.5rem,1.1rem+1.3vw,2.4rem)] leading-[1.12] font-extrabold tracking-[-0.03em] text-balance">
          The pipeline answers the question, then fact-checks its own answer, sentence by sentence.
        </p>
        <p className="mt-4 text-base leading-relaxed text-ink-2 text-pretty">
          This is a recorded run: replaying it makes no API call. The timeline above is to scale, including the time spent
          waiting on the provider's rate limit.
        </p>
        {onPlay && (
          <button
            type="button"
            onClick={onPlay}
            className="mt-6 inline-flex h-12 items-center gap-2.5 rounded-xl bg-ink px-6 text-lg font-bold text-sheet shadow-lift transition-transform duration-150 ease-out active:scale-[0.97]"
          >
            <Play className="size-5 fill-current" />
            Play the run
          </button>
        )}
      </div>
      <div>
        <ol className="divide-y divide-rule border-y border-rule">
          {steps.map(([title, text]) => (
            <li key={title} className="grid grid-cols-[7.5rem_1fr] gap-4 py-3">
              <span className="font-extrabold">{title}</span>
              <span className="text-ink-2 text-pretty">{text}</span>
            </li>
          ))}
        </ol>
        <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-sm text-ink-2" aria-label="Possible verdicts">
          <span className="inline-flex items-center gap-1.5">
            <VerdictMark verdict="supported" size={16} /> supported
          </span>
          <span className="inline-flex items-center gap-1.5">
            <VerdictMark verdict="contradicted" size={16} /> contradicted
          </span>
          <span className="inline-flex items-center gap-1.5">
            <VerdictMark verdict="contested" size={16} /> contested: the sources disagree
          </span>
          <span className="inline-flex items-center gap-1.5">
            <VerdictMark verdict="unverifiable" size={16} /> unverifiable
          </span>
          <span className="inline-flex items-center gap-1.5">
            <VerdictMark verdict="error" size={16} /> error: unusable answer from the judge
          </span>
        </div>
      </div>
    </div>
  )
}
