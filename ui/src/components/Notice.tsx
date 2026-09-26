import { Link } from 'react-router'
import { cn } from '@/lib/utils'

export function Notice({
  title,
  body,
  tone,
  back,
  action,
}: {
  title: string
  body?: React.ReactNode
  tone?: 'error'
  back?: boolean
  action?: React.ReactNode
}) {
  return (
    <div className="mx-auto w-full max-w-[64ch] px-4 py-16 sm:px-6">
      <h1 className={cn('text-2xl font-extrabold tracking-[-0.02em]', tone === 'error' && 'text-error-ink')}>{title}</h1>
      {body && <p className="mt-2 text-ink-2 text-pretty">{body}</p>}
      {(back || action) && (
        <p className="mt-5 flex gap-4 text-sm font-semibold underline underline-offset-4">
          {action}
          {back && <Link to="/runs">All runs</Link>}
        </p>
      )}
    </div>
  )
}
