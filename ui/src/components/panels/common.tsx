import { cn } from '@/lib/utils'

export function PanelHeading({ title, children, aside }: { title: string; children?: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
      <div className="max-w-[72ch]">
        <h2 className="text-xl font-extrabold tracking-[-0.02em] text-balance">{title}</h2>
        {children && <p className="mt-1 text-sm leading-relaxed text-ink-2 text-pretty">{children}</p>}
      </div>
      {aside}
    </div>
  )
}

/** Placeholder while a stage has not produced its output: hatched, like a well not yet assayed. */
export function Pending({ label, className }: { label: string; className?: string }) {
  return (
    <div className={cn('hatch flex min-h-40 items-center justify-center rounded-lg border border-dashed border-rule-strong', className)}>
      <span className="rounded-md bg-paper px-3 py-1.5 text-sm font-medium text-ink-2">{label}</span>
    </div>
  )
}

export function Figure({ label, value, note }: { label: string; value: React.ReactNode; note?: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-ink-3">{label}</dt>
      <dd className="figures mt-0.5 text-lg font-semibold">{value}</dd>
      {note && <dd className="text-xs text-ink-3">{note}</dd>}
    </div>
  )
}
