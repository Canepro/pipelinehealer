import { Link, useLocation } from 'react-router-dom'
import { Activity, LayoutDashboard, Settings, Zap } from 'lucide-react'
import clsx from 'clsx'

interface LayoutProps {
  children: React.ReactNode
}

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Activities', href: '/activities', icon: Activity },
  { name: 'Settings', href: '/settings', icon: Settings },
]

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <div className="hidden md:flex md:w-64 md:flex-col">
        <div className="flex flex-col flex-grow pt-5 border-r border-slate-700/40 bg-slate-900/95 overflow-y-auto">
          {/* Logo */}
          <div className="flex items-center flex-shrink-0 px-4">
            <Zap className="h-7 w-7 text-sky-400" />
            <span className="ml-2 text-xl font-semibold tracking-tight text-white">
              PipelineHealer
            </span>
          </div>

          {/* Navigation */}
          <div className="mt-8 flex-grow flex flex-col">
            <nav className="flex-1 px-3 space-y-1.5">
              {navigation.map((item) => {
                const isActive = location.pathname === item.href
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    className={clsx(
                      isActive
                        ? 'bg-slate-800/85 text-white border border-slate-600/60'
                        : 'text-slate-300 hover:bg-slate-800/60 hover:text-white border border-transparent',
                      'group flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-colors'
                    )}
                  >
                    <item.icon
                      className={clsx(
                        isActive ? 'text-sky-300' : 'text-slate-400 group-hover:text-slate-200',
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
          <div className="flex-shrink-0 flex border-t border-slate-700/50 p-4">
            <div className="flex items-center">
              <div className="ml-3">
                <p className="text-xs font-medium text-slate-300">
                  AI Dev Days Hackathon 2026
                </p>
                <p className="text-xs text-slate-400">
                  Microsoft Agent Framework
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile header */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-10 flex items-center justify-between h-16 bg-slate-900 border-b border-slate-700/50 px-4">
        <div className="flex items-center">
          <Zap className="h-7 w-7 text-sky-400" />
          <span className="ml-2 text-xl font-semibold text-white tracking-tight">
            PipelineHealer
          </span>
        </div>
      </div>

      {/* Main content */}
      <div className="flex flex-col flex-1">
        <main className="flex-1 md:pt-0 pt-16">
          <div className="py-6">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 md:px-8">
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
