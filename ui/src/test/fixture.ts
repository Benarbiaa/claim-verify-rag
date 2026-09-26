import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { PipelineEvent } from '@/lib/types'

/** The answering run of tests/fixtures (all five verdicts, llm_waiting events). */
export function fixtureEvents(): PipelineEvent[] {
  const path = resolve(__dirname, '../../../tests/fixtures/runs/20260101_090000_answering/events.jsonl')
  return readFileSync(path, 'utf-8')
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line))
}
