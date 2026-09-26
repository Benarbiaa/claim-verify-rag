import { FlaskConical } from 'lucide-react'

/** Shown on runs built by tests/fixtures: real passages, hand-written verdicts. */
export function FixtureNote() {
  return (
    <p className="mb-4 flex items-start gap-2 rounded-lg border border-dashed border-rule-strong px-3 py-2 text-sm text-ink-2">
      <FlaskConical className="mt-0.5 size-4 shrink-0 text-ink-3" aria-hidden />
      <span>
        <strong className="text-ink">Test fixture, not a real run.</strong> The passages are real chunks of the corpus; the draft,
        claims, verdicts and timings were written by hand to show every verdict, including <em>contested</em>.
      </span>
    </p>
  )
}

export function FixtureTag() {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-dashed border-rule-strong px-1.5 py-px text-[0.7rem] font-semibold text-ink-3">
      <FlaskConical className="size-3" aria-hidden />
      fixture
    </span>
  )
}
