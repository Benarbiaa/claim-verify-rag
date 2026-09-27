import { FlaskConical } from 'lucide-react'

/** Marks runs built by tests/fixtures: real passages, hand-written verdicts. */
export function FixtureTag() {
  return (
    <span
      title="Test data: real passages from the corpus, verdicts written by hand to show every case"
      className="inline-flex items-center gap-1 rounded border border-dashed border-rule-strong px-1.5 py-px text-xs font-semibold text-ink-3"
    >
      <FlaskConical className="size-3" aria-hidden />
      test data
    </span>
  )
}
