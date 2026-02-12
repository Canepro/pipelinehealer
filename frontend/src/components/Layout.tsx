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
        <div className="flex flex-col flex-grow pt-5 bg-gray-900 overflow-y-auto">
          {/* Logo */}
          <div className="flex items-center flex-shrink-0 px-4">
            <Zap className="h-8 w-8 text-azure-500" />
            <span className="ml-2 text-xl font-bold text-white">
              PipelineHealer
            </span>
          </div>

          {/* Navigation */}
          <div className="mt-8 flex-grow flex flex-col">
            <nav className="flex-1 px-2 space-y-1">
              {navigation.map((item) => {
                const isActive = location.pathname === item.href
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    className={clsx(
                      isActive
                        ? 'bg-gray-800 text-white'
                        : 'text-gray-300 hover:bg-gray-700 hover:text-white',
                      'group flex items-center px-3 py-2 text-sm font-medium rounded-lg transition-colors'
                    )}
                  >
                    <item.icon
                      className={clsx(
                        isActive ? 'text-azure-400' : 'text-gray-400 group-hover:text-gray-300',
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
          <div className="flex-shrink-0 flex border-t border-gray-800 p-4">
            <div className="flex items-center">
              <div className="ml-3">
                <p className="text-xs font-medium text-gray-400">
                  AI Dev Days Hackathon 2026
                </p>
                <p className="text-xs text-gray-500">
                  Microsoft Agent Framework
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile header */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-10 flex items-center justify-between h-16 bg-gray-900 px-4">
        <div className="flex items-center">
          <Zap className="h-8 w-8 text-azure-500" />
          <span className="ml-2 text-xl font-bold text-white">
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
