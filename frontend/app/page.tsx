'use client';

import { useEffect, useState } from 'react';
import { getMonthlySummary, getAccounts } from '@/lib/api';
import { MonthlySummary, Account } from '@/lib/types';

export default function Dashboard() {
  const [summary, setSummary] = useState<MonthlySummary | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Get current month/year
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;

  useEffect(() => {
    loadData();
  }, [selectedAccount]);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);

      // Load accounts
      const accountsData = await getAccounts();
      setAccounts(accountsData.accounts || []);

      // Load monthly summary
      const summaryData = await getMonthlySummary(
        currentYear,
        currentMonth,
        selectedAccount || undefined
      );
      setSummary(summaryData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center">
          <p className="text-gray-500">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">Error: {error}</p>
          <button
            onClick={loadData}
            className="mt-2 text-sm text-red-600 hover:text-red-800 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  const monthName = new Date(currentYear, currentMonth - 1).toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-2 text-sm text-gray-600">{monthName}</p>
      </div>

      {/* Account Filter */}
      {accounts.length > 0 && (
        <div className="mb-6">
          <label htmlFor="account-filter" className="block text-sm font-medium text-gray-700 mb-2">
            Filter by Account
          </label>
          <select
            id="account-filter"
            value={selectedAccount}
            onChange={(e) => setSelectedAccount(e.target.value)}
            className="block w-full max-w-xs px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
          >
            <option value="">All Accounts</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-3 mb-8">
        {/* Total Spend */}
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">Total Spending</dt>
            <dd className="mt-1 text-3xl font-semibold text-gray-900">
              ${summary?.total_spend?.toFixed(2) || '0.00'}
            </dd>
          </div>
        </div>

        {/* Total Income */}
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">Total Income</dt>
            <dd className="mt-1 text-3xl font-semibold text-green-600">
              ${summary?.total_income?.toFixed(2) || '0.00'}
            </dd>
          </div>
        </div>

        {/* Net */}
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">Net</dt>
            <dd className={`mt-1 text-3xl font-semibold ${
              (summary?.net || 0) >= 0 ? 'text-green-600' : 'text-red-600'
            }`}>
              ${summary?.net?.toFixed(2) || '0.00'}
            </dd>
          </div>
        </div>
      </div>

      {/* Category Breakdown */}
      {summary?.category_breakdown && summary.category_breakdown.length > 0 && (
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Category Breakdown</h3>
            <div className="space-y-4">
              {summary.category_breakdown.map((category) => (
                <div key={category.category}>
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-sm font-medium text-gray-700">
                      {category.category || 'Uncategorized'}
                    </span>
                    <span className="text-sm text-gray-500">
                      ${category.amount.toFixed(2)} ({category.percentage.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-indigo-600 h-2 rounded-full"
                      style={{ width: `${category.percentage}%` }}
                    ></div>
                  </div>
                  <div className="mt-1 text-xs text-gray-500">
                    {category.count} transaction{category.count !== 1 ? 's' : ''}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {(!summary?.category_breakdown || summary.category_breakdown.length === 0) && (
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-12 text-center">
            <p className="text-gray-500">No transactions found for this period.</p>
            <a
              href="/imports"
              className="mt-4 inline-block text-indigo-600 hover:text-indigo-800"
            >
              Import transactions to get started
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
