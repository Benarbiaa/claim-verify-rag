import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router'
import { cn } from '@/lib/utils'

type Theme = 'light' | 'dark'

function storedTheme(): Theme | null {
  try {
    const saved = localStorage.getItem('theme')
    return saved === 'light' || saved === 'dark' ? saved : null
  } catch {
    return null // storage blocked: follow the system
  }
}

const systemTheme = (): Theme => (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')

/** Follows the system theme until the viewer picks one with the toggle. */
export function useTheme() {
  const [chosen, setChosen] = useState<Theme | null>(storedTheme)
  const [system, setSystem] = useState<Theme>(systemTheme)
  useEffect(() => {
    const query = window.matchMedia?.('(prefers-color-scheme: dark)')
    const onChange = () => setSystem(systemTheme())
    query?.addEventListener('change', onChange)
    return () => query?.removeEventListener('change', onChange)
  }, [])
  const theme = chosen ?? system
  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])
  const choose = (next: Theme) => {
    setChosen(next)
    try {
      localStorage.setItem('theme', next)
    } catch {
      // applied for this visit only
    }
  }
  return [theme, choose] as const
}

function Wordmark() {
  // The mark is a claim row: two sources agree, one disagrees.
  return (
    <span className="flex items-center gap-2.5">
      <svg width="30" height="14" viewBox="0 0 30 14" aria-hidden className="shrink-0">
        <circle cx="5" cy="7" r="4.5" fill="var(--supported)" />
        <circle cx="15" cy="7" r="4.5" fill="var(--supported)" />
        <rect x="21.5" y="3.5" width="7" height="7" rx="1" transform="rotate(45 25 7)" fill="var(--contradicted)" />
      </svg>
      <span className="hidden text-[0.95rem] font-extrabold tracking-[-0.02em] min-[400px]:inline">claim-verify-rag</span>
    </span>
  )
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'rounded-md px-2.5 py-1.5 text-sm font-medium text-ink-2 transition-colors duration-150 hover:text-ink',
    isActive && 'bg-sunk text-ink',
  )

export function AppShell() {
  const [theme, setTheme] = useTheme()
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-rule bg-paper/92 backdrop-blur-sm">
        <div className="mx-auto flex h-12 max-w-[1760px] items-center gap-6 px-4 sm:px-6">
          <NavLink to="/" aria-label="claim-verify-rag, latest run" className="rounded-md">
            <Wordmark />
          </NavLink>
          <nav className="flex items-center gap-1" aria-label="Main">
            <NavLink to="/runs" className={navClass}>
              Runs
            </NavLink>
            <NavLink to="/live" className={navClass}>
              Ask<span className="hidden sm:inline"> a question</span>
            </NavLink>
          </nav>
          <button
            type="button"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="ml-auto inline-flex size-8 items-center justify-center rounded-md text-ink-2 transition-[transform,color] duration-150 ease-out hover:text-ink active:scale-[0.96]"
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            title={theme === 'dark' ? 'Light theme (projector)' : 'Dark theme'}
          >
            {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </div>
      </header>
      <main className="flex flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  )
}
