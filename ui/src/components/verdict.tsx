// The verdict language: a shape, a label and a colour, never colour alone.
// Wells are round (a conclusion about the sources); error is a hatched square (no conclusion).

import { useId } from 'react'
import type { Stance } from '@/lib/answering'
import type { VerdictLabel } from '@/lib/types'
import { cn } from '@/lib/utils'

export const VERDICT_TEXT: Record<VerdictLabel, { label: string; meaning: string; ink: string; wash: string }> = {
  supported: {
    label: 'Supported',
    meaning: 'A source supports the claim, none contradicts it.',
    ink: 'text-supported-ink',
    wash: 'bg-supported-wash',
  },
  contradicted: {
    label: 'Contradicted',
    meaning: 'The sources contradict the claim, none supports it.',
    ink: 'text-contradicted-ink',
    wash: 'bg-contradicted-wash',
  },
  contested: {
    label: 'Contested',
    meaning: 'The sources disagree with each other: at least one on each side.',
    ink: 'text-ink',
    wash: 'bg-sunk',
  },
  unverifiable: {
    label: 'Unverifiable',
    meaning: 'No source addresses the claim.',
    ink: 'text-unverifiable-ink',
    wash: 'bg-sunk',
  },
  error: {
    label: 'Error',
    meaning: "The judge's answer was unusable. Not a conclusion about the sources; a retry can fix it.",
    ink: 'text-error-ink',
    wash: 'bg-error-wash',
  },
}

export function VerdictMark({ verdict, size = 18, className }: { verdict: VerdictLabel | 'pending'; size?: number; className?: string }) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const common = { width: size, height: size, viewBox: '0 0 20 20', className: cn('shrink-0', className), 'aria-hidden': true }
  switch (verdict) {
    case 'supported':
      return (
        <svg {...common}>
          <circle cx="10" cy="10" r="9" fill="var(--supported)" />
          <path d="M5.8 10.4l2.8 2.8 5.6-6.1" fill="none" stroke="var(--sheet)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    case 'contradicted':
      return (
        <svg {...common}>
          <circle cx="10" cy="10" r="9" fill="var(--contradicted)" />
          <path d="M6.6 6.6l6.8 6.8M13.4 6.6l-6.8 6.8" stroke="var(--sheet)" strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      )
    case 'contested':
      return (
        <svg {...common}>
          <clipPath id={`well-${uid}`}>
            <circle cx="10" cy="10" r="9" />
          </clipPath>
          <g clipPath={`url(#well-${uid})`}>
            <path d="M0 0H20L0 20Z" fill="var(--supported)" />
            <path d="M20 0V20H0Z" fill="var(--contradicted)" />
            <path d="M19 1L1 19" stroke="var(--sheet)" strokeWidth="1.8" />
          </g>
        </svg>
      )
    case 'unverifiable':
      return (
        <svg {...common}>
          <circle cx="10" cy="10" r="8" fill="none" stroke="var(--unverifiable)" strokeWidth="2" />
          <path
            d="M7.9 8a2.2 2.2 0 1 1 3.2 2c-.7.4-1.1.8-1.1 1.6"
            fill="none"
            stroke="var(--unverifiable-ink)"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
          <circle cx="10" cy="14.2" r="1.05" fill="var(--unverifiable-ink)" />
        </svg>
      )
    case 'error':
      return (
        <svg {...common}>
          <pattern id={`err-${uid}`} width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="4" height="4" fill="var(--error-wash)" />
            <rect width="1.6" height="4" fill="var(--error)" />
          </pattern>
          <rect x="1.5" y="1.5" width="17" height="17" rx="2.5" fill={`url(#err-${uid})`} stroke="var(--error)" strokeWidth="1.5" />
          <rect x="8.6" y="5" width="2.8" height="6.4" rx="1.2" fill="var(--error-ink)" />
          <circle cx="10" cy="14.4" r="1.5" fill="var(--error-ink)" />
        </svg>
      )
    case 'pending':
      return (
        <svg {...common}>
          <pattern id={`pend-${uid}`} width="3.5" height="3.5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="1.2" height="3.5" fill="var(--hatch)" />
          </pattern>
          <circle cx="10" cy="10" r="8.5" fill={`url(#pend-${uid})`} stroke="var(--rule-strong)" strokeWidth="1" strokeDasharray="2 2" />
        </svg>
      )
  }
}

export function VerdictLabelText({ verdict, className }: { verdict: VerdictLabel; className?: string }) {
  return <span className={cn('font-bold', VERDICT_TEXT[verdict].ink, className)}>{VERDICT_TEXT[verdict].label}</span>
}

export function VerdictTag({ verdict, size = 18, className }: { verdict: VerdictLabel; size?: number; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap', className)}>
      <VerdictMark verdict={verdict} size={size} />
      <VerdictLabelText verdict={verdict} />
    </span>
  )
}

/** One cell of the plate: what a source said about a claim. Circle = for, diamond = against. */
export function StanceMark({ stance, size = 16 }: { stance: Stance; size?: number }) {
  const common = { width: size, height: size, viewBox: '0 0 16 16', 'aria-hidden': true, className: 'shrink-0' }
  switch (stance) {
    case 'supports':
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6.5" fill="var(--supported)" />
        </svg>
      )
    case 'contradicts':
      return (
        <svg {...common}>
          <rect x="3.2" y="3.2" width="9.6" height="9.6" rx="1.2" transform="rotate(45 8 8)" fill="var(--contradicted)" />
        </svg>
      )
    case 'silent':
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="4" fill="none" stroke="var(--ink-3)" strokeWidth="1.4" />
        </svg>
      )
    case 'not_read':
      return (
        <svg {...common}>
          <path d="M5.5 8h5" stroke="var(--rule-strong)" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      )
  }
}

export const STANCE_TEXT: Record<Stance, string> = {
  supports: 'supports the claim',
  contradicts: 'contradicts the claim',
  silent: 'read by the judge, says nothing about the claim',
  not_read: 'not retrieved for this claim',
}
