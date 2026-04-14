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
} from '@heroicons/react/24/outline';
import clsx from 'clsx';
import { useAuth } from '../contexts/AuthContext';
import ChatPanel from './ChatPanel';

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: HomeIcon },
  { to: '/risks', label: 'Risks', icon: ShieldExclamationIcon },
  { to: '/suppliers', label: 'Suppliers', icon: TruckIcon },
  { to: '/supply-chain', label: 'Supply Chain', icon: MapIcon },
  { to: '/predictions', label: 'Predictions', icon: ChartBarSquareIcon },
  { to: '/events', label: 'Risk Events', icon: BoltIcon },
  { to: '/intelligence', label: 'Intel Feed', icon: NewspaperIcon },
  { to: '/simulator', label: 'Simulator', icon: CpuChipIcon },
  { to: '/procurement', label: 'Procurement', icon: ShoppingCartIcon },
  { to: '/alerts', label: 'Alerts', icon: BellAlertIcon },
  { to: '/assessments/new', label: 'New Assessment', icon: PlusCircleIcon },
  { to: '/recommendations', label: 'Recommendations', icon: LightBulbIcon },
];

export default function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="flex h-screen">
      <a href="#main-content" className="skip-nav">Skip to main content</a>

      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 text-white flex flex-col" role="navigation" aria-label="Main navigation">
        <div className="p-6">
          <h1 className="text-xl font-bold tracking-wide">SCIRM</h1>
          <p className="text-xs text-gray-400 mt-1">Supply Chain Risk Management</p>
        </div>

        <nav className="flex-1 px-3 space-y-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-gray-700 text-white'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                )
              }
            >
              <Icon className="h-5 w-5" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-gray-700">
          <p className="text-sm text-gray-300 truncate">{user?.email}</p>
          <button
            onClick={logout}
            className="mt-2 text-xs text-gray-400 hover:text-white transition-colors"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main id="main-content" className="flex-1 overflow-auto bg-gray-50 p-6" role="main" aria-label="Page content">
        <Outlet />
      </main>

      {/* Floating chat panel */}
      <ChatPanel />
    </div>
  );
}
