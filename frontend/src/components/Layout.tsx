import { Link, Outlet, useLocation } from 'react-router-dom'
import { Activity, LayoutDashboard, Menu, Settings, ShieldCheck, Zap } from 'lucide-react'
import clsx from 'clsx'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'

const navigation = [
  { name: 'Dashboard', href: '/app', icon: LayoutDashboard },
  { name: 'Activities', href: '/app/activities', icon: Activity },
  { name: 'Control Center', href: '/app/control-center', icon: ShieldCheck },
  { name: 'Settings', href: '/app/settings', icon: Settings },
]

export default function Layout() {
  const location = useLocation()
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false)

  useEffect(() => {
    setIsMobileNavOpen(false)
  }, [location.pathname])

  const currentPageTitle =
    navigation.find((item) =>
      item.href === '/app'
        ? location.pathname === '/app' || location.pathname === '/app/'
        : location.pathname.startsWith(item.href)
    )?.name || 'PipelineHealer'

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <div className="hidden md:flex md:w-64 md:flex-col">
        <div className="flex flex-col flex-grow pt-5 border-r border-[var(--ph-border)] bg-[color:var(--ph-bg-elevated)]/95 overflow-y-auto">
          {/* Logo */}
          <Link
            to="/"
            className="mx-3 flex items-center rounded-lg px-2 py-1.5 transition-colors hover:bg-slate-800/40"
          >
            <Zap className="h-7 w-7 text-azure-400" />
            <span className="ml-2 text-xl font-semibold tracking-tight text-slate-100">PipelineHealer</span>
          </Link>

          {/* Navigation */}
          <div className="mt-8 flex-grow flex flex-col">
            <nav className="flex-1 px-3 space-y-1.5">
              {navigation.map((item) => {
                const isActive =
                  item.href === '/app'
                    ? location.pathname === '/app' || location.pathname === '/app/'
                    : location.pathname.startsWith(item.href)
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    className={clsx(
                      isActive
                        ? 'bg-slate-800/55 text-slate-100 border border-slate-600/35'
                        : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200 border border-transparent',
                      'group flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-colors'
                    )}
                  >
                    <item.icon
                      className={clsx(
                        isActive ? 'text-azure-300' : 'text-slate-500 group-hover:text-slate-300',
                        'mr-3 flex-shrink-0 h-5 w-5'
                      )}
                    />
                    {item.name}
                  </Link>
                )
              })}
            </nav>
          </div>

          {/* Footer */}
          <div className="flex-shrink-0 flex border-t border-[var(--ph-border)] p-4">
            <div className="flex items-center">
              <div className="ml-3">
                <p className="text-xs font-medium text-slate-300/90">AI Dev Days Hackathon 2026</p>
                <p className="text-xs text-slate-500">Microsoft Agent Framework</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile header */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-20 flex items-center justify-between h-14 pt-[env(safe-area-inset-top)] bg-[color:var(--ph-bg-elevated)]/95 backdrop-blur border-b border-[var(--ph-border)] px-3">
        <div className="flex items-center gap-2 min-w-0">
          <Link to="/" className="flex items-center gap-2 rounded-md px-1 py-0.5 hover:bg-slate-800/50">
            <Zap className="h-5 w-5 text-azure-400 shrink-0" />
            <span className="text-sm font-semibold text-slate-100 tracking-tight">PipelineHealer</span>
          </Link>
          <span className="text-xs text-slate-400 truncate">{currentPageTitle}</span>
        </div>

        <Sheet open={isMobileNavOpen} onOpenChange={setIsMobileNavOpen}>
          <SheetTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Open navigation menu"
              className="text-slate-200 hover:bg-slate-800/60"
            >
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-azure-400" />
                PipelineHealer
              </SheetTitle>
              <SheetDescription>Navigate between dashboard, control center, activities, and settings.</SheetDescription>
            </SheetHeader>

            <nav className="space-y-1.5">
              {navigation.map((item) => {
                const isActive =
                  item.href === '/app'
                    ? location.pathname === '/app' || location.pathname === '/app/'
                    : location.pathname.startsWith(item.href)

                return (
                  <SheetClose asChild key={item.name}>
                    <Link
                      to={item.href}
                      className={clsx(
                        isActive
                          ? 'bg-slate-800/55 text-slate-100 border border-slate-600/35'
                          : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200 border border-transparent',
                        'group flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-colors'
                      )}
                    >
                      <item.icon
                        className={clsx(
                          isActive ? 'text-azure-300' : 'text-slate-500 group-hover:text-slate-300',
                          'mr-3 h-5 w-5 shrink-0'
                        )}
                      />
                      {item.name}
                    </Link>
                  </SheetClose>
                )
              })}
            </nav>
          </SheetContent>
        </Sheet>
      </div>

      {/* Main content */}
      <div className="min-w-0 flex flex-col flex-1">
        <main className="flex-1 md:pt-0 pt-[calc(3.5rem+env(safe-area-inset-top))]">
          <div className="py-8">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 md:px-8">
              <Outlet />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
