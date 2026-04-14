import { NavLink, Outlet } from 'react-router-dom';
import {
  HomeIcon,
  ShieldExclamationIcon,
  PlusCircleIcon,
  LightBulbIcon,
  TruckIcon,
  BellAlertIcon,
  MapIcon,
  ChartBarSquareIcon,
  BoltIcon,
  NewspaperIcon,
  CpuChipIcon,
  ShoppingCartIcon,
  CubeIcon,
  SunIcon,
  MoonIcon,
} from '@heroicons/react/24/outline';
import clsx from 'clsx';
import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import OnboardingWizard from './OnboardingWizard';
import { useTheme } from '../contexts/ThemeContext';
import ChatPanel from './ChatPanel';
import GlobalSearch from './GlobalSearch';
import NotificationBell from './NotificationBell';
import Breadcrumbs from './Breadcrumbs';

const navGroups = [
  {
    label: 'Overview',
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: HomeIcon },
      { to: '/risks', label: 'Risks', icon: ShieldExclamationIcon },
      { to: '/alerts', label: 'Alerts', icon: BellAlertIcon },
    ],
  },
  {
    label: 'Supply Chain',
    items: [
      { to: '/suppliers', label: 'Suppliers', icon: TruckIcon },
      { to: '/components', label: 'Components', icon: CubeIcon },
      { to: '/supply-chain', label: 'Network Map', icon: MapIcon },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { to: '/predictions', label: 'Predictions', icon: ChartBarSquareIcon },
      { to: '/events', label: 'Risk Events', icon: BoltIcon },
      { to: '/intelligence', label: 'Intel Feed', icon: NewspaperIcon },
    ],
  },
  {
    label: 'Operations',
    items: [
      { to: '/simulator', label: 'Simulator', icon: CpuChipIcon },
      { to: '/procurement', label: 'Procurement', icon: ShoppingCartIcon },
      { to: '/assessments/new', label: 'New Assessment', icon: PlusCircleIcon },
      { to: '/recommendations', label: 'Recommendations', icon: LightBulbIcon },
    ],
  },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  useKeyboardShortcuts();

  const [showOnboarding, setShowOnboarding] = useState(() => !localStorage.getItem('scirm_onboarded'));

  return (
    <>
    {showOnboarding && <OnboardingWizard onComplete={() => setShowOnboarding(false)} />}
    <div className="flex h-screen bg-gray-50 dark:bg-gray-950">
      <a href="#main-content" className="skip-nav">Skip to main content</a>

      {/* Sidebar */}
      <aside className="w-60 bg-gray-900 dark:bg-gray-900 text-white flex flex-col shrink-0" role="navigation" aria-label="Main navigation">
        {/* Header */}
        <div className="p-4 pb-3">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h1 className="text-lg font-bold tracking-wide">SCIRM</h1>
              <p className="text-[10px] text-gray-400 -mt-0.5">Supply Chain Risk Mgmt</p>
            </div>
            <div className="flex items-center gap-1">
              <NotificationBell />
              <button onClick={toggleTheme} className="p-1.5 rounded-lg hover:bg-gray-700 transition-colors" aria-label="Toggle theme">
                {theme === 'dark' ? <SunIcon className="h-4 w-4 text-yellow-400" /> : <MoonIcon className="h-4 w-4 text-gray-400" />}
              </button>
            </div>
          </div>
          <GlobalSearch />
        </div>

        {/* Grouped navigation */}
        <nav className="flex-1 overflow-y-auto px-3 pb-3 space-y-4">
          {navGroups.map((group) => (
            <div key={group.label}>
              <p className="px-3 mb-1 text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{group.label}</p>
              <div className="space-y-0.5">
                {group.items.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      clsx(
                        'flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] font-medium transition-colors',
                        isActive
                          ? 'bg-gray-700 text-white'
                          : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                      )
                    }
                  >
                    <Icon className="h-4 w-4" />
                    {label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* User */}
        <div className="p-3 border-t border-gray-800">
          <p className="text-xs text-gray-300 truncate">{user?.email}</p>
          <div className="flex items-center gap-3 mt-1">
            <NavLink to="/settings" className="text-[10px] text-gray-500 hover:text-white transition-colors">Settings</NavLink>
            <button onClick={logout} className="text-[10px] text-gray-500 hover:text-white transition-colors">Sign out</button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main id="main-content" className="flex-1 overflow-auto bg-gray-50 dark:bg-gray-900 p-6" role="main" aria-label="Page content">
        <Breadcrumbs />
        <Outlet />
      </main>

      <ChatPanel />
    </div>
    </>
  );
}
