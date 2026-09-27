import { cn } from '@/lib/utils'

/** A panel's title says what the panel is for; `step` matches the step's number in the pipeline bar. */
export function PanelHeading({
  step,
  title,
  children,
  aside,
}: {
  step?: string
  title: string
  children?: React.ReactNode
  aside?: React.ReactNode
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
      <div className="max-w-[72ch]">
        <h2 className="flex items-center gap-2.5 text-xl font-extrabold tracking-[-0.02em] text-balance">
          {step && (
            <span className="figures inline-flex h-7 min-w-7 items-center justify-center rounded-full bg-ink px-2 text-sm text-sheet">
              {step}
            </span>
          )}
          {title}
        </h2>
        {children && <p className="mt-1 text-sm text-ink-2 text-pretty">{children}</p>}
      </div>
      {aside}
    </div>
  )
}

/** Placeholder while a step has not produced its output yet. */
export function Pending({ label, className }: { label: string; className?: string }) {
  return (
    <div className={cn('hatch flex min-h-40 items-center justify-center rounded-lg border border-dashed border-rule-strong', className)}>
      <span className="rounded-md bg-paper px-3 py-1.5 text-sm font-medium text-ink-2">{label}</span>
    </div>
  )
}
