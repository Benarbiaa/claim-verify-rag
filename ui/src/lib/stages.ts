// Each pipeline step has its own colour, reused wherever that step appears (steps, time axis,
// panel titles). Indexing steps reuse the four colours in order; Clean shares Load's, as both
// prepare the text. Summary stays ink.

const SLOT: Record<string, 1 | 2 | 3 | 4> = {
  retrieve: 1,
  draft: 2,
  decompose: 3,
  verify: 4,
  load: 1,
  clean: 1,
  chunk: 2,
  embed: 3,
  store: 4,
}

/** CSS colour of a step, e.g. `var(--stage-2)`; ink for steps without a colour. */
export function stageColor(stage: string | undefined): string {
  const slot = stage ? SLOT[stage] : undefined
  return slot ? `var(--stage-${slot})` : 'var(--ink)'
}

/** A step's colour, partly transparent (hatches, ghosted marks). */
export function tint(color: string, percent = 55): string {
  return `color-mix(in oklab, ${color} ${percent}%, transparent)`
}

export const ANSWERING_STAGES = [
  { id: 'retrieve', label: 'Search' },
  { id: 'draft', label: 'Answer' },
  { id: 'decompose', label: 'Split' },
  { id: 'verify', label: 'Check' },
] as const
