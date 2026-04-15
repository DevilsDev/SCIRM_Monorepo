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
import { useTranslation } from 'react-i18next';
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
    labelKey: 'common.overview',
    fallbackLabel: 'Overview',
    items: [
      { to: '/dashboard', tKey: 'nav.dashboard', fallback: 'Dashboard', icon: HomeIcon },
      { to: '/risks', tKey: 'nav.risks', fallback: 'Risks', icon: ShieldExclamationIcon },
      { to: '/alerts', tKey: 'nav.alerts', fallback: 'Alerts', icon: BellAlertIcon },
    ],
  },
  {
    labelKey: 'common.supplyChainGroup',
    fallbackLabel: 'Supply Chain',
    items: [
      { to: '/suppliers', tKey: 'nav.suppliers', fallback: 'Suppliers', icon: TruckIcon },
      { to: '/components', tKey: 'nav.components', fallback: 'Components', icon: CubeIcon },
      { to: '/supply-chain', tKey: 'nav.supplyChain', fallback: 'Network Map', icon: MapIcon },
    ],
  },
  {
    labelKey: 'common.intelligence',
    fallbackLabel: 'Intelligence',
    items: [
      { to: '/predictions', tKey: 'nav.predictions', fallback: 'Predictions', icon: ChartBarSquareIcon },
      { to: '/events', tKey: 'nav.events', fallback: 'Risk Events', icon: BoltIcon },
      { to: '/intelligence', tKey: 'nav.intelFeed', fallback: 'Intel Feed', icon: NewspaperIcon },
    ],
  },
  {
    labelKey: 'common.operations',
    fallbackLabel: 'Operations',
    items: [
      { to: '/simulator', tKey: 'nav.simulator', fallback: 'Simulator', icon: CpuChipIcon },
      { to: '/procurement', tKey: 'nav.procurement', fallback: 'Procurement', icon: ShoppingCartIcon },
      { to: '/assessments/new', tKey: 'nav.newAssessment', fallback: 'New Assessment', icon: PlusCircleIcon },
      { to: '/recommendations', tKey: 'nav.recommendations', fallback: 'Recommendations', icon: LightBulbIcon },
    ],
  },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  useKeyboardShortcuts();
  const { t } = useTranslation();

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
            <div key={group.labelKey}>
              <p className="px-3 mb-1 text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{t(group.labelKey, group.fallbackLabel)}</p>
              <div className="space-y-0.5">
                {group.items.map(({ to, tKey, fallback, icon: Icon }) => (
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
                    {t(tKey, fallback)}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* User */}
        <div className="p-3 border-t border-gray-800">
          <p className="text-xs text-gray-300 truncate mb-2">{user?.email}</p>
          <div className="flex items-center gap-1">
            <NavLink
              to="/settings"
              data-compact=""
              className="flex-1 text-center text-xs py-1.5 rounded-md text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
            >
              {t('common.settings', 'Settings')}
            </NavLink>
            <span className="text-gray-700 text-xs">|</span>
            <button
              onClick={logout}
              data-compact=""
              className="flex-1 text-center text-xs py-1.5 rounded-md text-gray-400 hover:text-red-400 hover:bg-gray-800 transition-colors"
            >
              {t('common.signOut', 'Sign out')}
            </button>
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
