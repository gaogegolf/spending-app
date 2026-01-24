'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';

const navLinks = [
  { href: '/', label: 'Dashboard' },
  { href: '/net-worth', label: 'Net Worth' },
  { href: '/accounts', label: 'Accounts' },
  { href: '/imports', label: 'Import' },
  { href: '/transactions', label: 'Transactions' },
  { href: '/subscriptions', label: 'Subscriptions' },
  { href: '/reports', label: 'Reports' },
  { href: '/merchant-categories', label: 'Merchants' },
  { href: '/rules', label: 'Rules' },
];

export default function Navigation() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <nav className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16 gap-4">
          <div className="flex min-w-0 flex-1">
            <div className="flex-shrink-0 flex items-center">
              <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg flex items-center justify-center">
                <span className="text-white text-2xl">&#128176;</span>
              </div>
            </div>
            <div className="hidden sm:ml-6 sm:flex sm:space-x-1 overflow-x-auto">
              {navLinks.map((link) => {
                const isActive = pathname === link.href;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`inline-flex items-center px-2 py-2 border-b-2 text-sm font-medium transition-colors whitespace-nowrap ${
                      isActive
                        ? 'border-indigo-500 text-indigo-600'
                        : 'border-transparent text-gray-600 hover:border-gray-300 hover:text-gray-900'
                    }`}
                  >
                    {link.label}
                  </Link>
                );
              })}
            </div>
          </div>

          {/* User menu */}
          <div className="flex-shrink-0 flex items-center space-x-3">
            {user && (
              <>
                <span className="text-sm text-gray-600">
                  {user.username}
                </span>
                <button
                  onClick={logout}
                  className="text-sm text-gray-600 hover:text-gray-900 px-3 py-1.5 rounded border border-gray-300 hover:border-gray-400 transition-colors"
                >
                  Logout
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
