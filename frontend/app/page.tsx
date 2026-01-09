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
  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1);

  useEffect(() => {
    loadData();
  }, [selectedAccount, selectedYear, selectedMonth]);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);

      // Load accounts
      const accountsData = await getAccounts();
      setAccounts(accountsData.accounts || []);

      // Load monthly summary
      const summaryData = await getMonthlySummary(
        selectedYear,
        selectedMonth,
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

  const monthName = new Date(selectedYear, selectedMonth - 1).toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  });

  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const years = Array.from({ length: 5 }, (_, i) => now.getFullYear() - i);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">Dashboard</h1>
        <p className="text-lg text-gray-600">{monthName}</p>
      </div>

      {/* Filters */}
      <div className="bg-white shadow-lg rounded-xl border border-gray-200 p-6 mb-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Month Selector */}
          <div>
            <label htmlFor="month-filter" className="block text-sm font-semibold text-gray-700 mb-2">
              Month
            </label>
            <select
              id="month-filter"
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(Number(e.target.value))}
              className="block w-full px-4 py-3 border-2 border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-base transition-all"
            >
              {months.map((month, index) => (
                <option key={month} value={index + 1}>
                  {month}
                </option>
              ))}
            </select>
          </div>

          {/* Year Selector */}
          <div>
            <label htmlFor="year-filter" className="block text-sm font-semibold text-gray-700 mb-2">
              Year
            </label>
            <select
              id="year-filter"
              value={selectedYear}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              className="block w-full px-4 py-3 border-2 border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-base transition-all"
            >
              {years.map((year) => (
                <option key={year} value={year}>
                  {year}
                </option>
              ))}
            </select>
          </div>

          {/* Account Filter */}
          {accounts.length > 0 && (
            <div>
              <label htmlFor="account-filter" className="block text-sm font-semibold text-gray-700 mb-2">
                Account
              </label>
              <select
                id="account-filter"
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                className="block w-full px-4 py-3 border-2 border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-base transition-all"
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
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3 mb-8">
        {/* Total Spend */}
        <div className="bg-white overflow-hidden shadow-lg rounded-xl border border-gray-200 hover:shadow-xl transition-shadow">
          <div className="px-6 py-6">
            <dt className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-2">Total Spending</dt>
            <dd className="text-4xl font-bold text-gray-900">
              ${summary?.total_spend?.toFixed(2) || '0.00'}
            </dd>
            <div className="mt-3 text-xs text-gray-500">This month</div>
          </div>
        </div>

        {/* Total Income */}
        <div className="bg-gradient-to-br from-green-50 to-emerald-50 overflow-hidden shadow-lg rounded-xl border border-green-200 hover:shadow-xl transition-shadow">
          <div className="px-6 py-6">
            <dt className="text-sm font-medium text-green-700 uppercase tracking-wide mb-2">Total Income</dt>
            <dd className="text-4xl font-bold text-green-600">
              ${summary?.total_income?.toFixed(2) || '0.00'}
            </dd>
            <div className="mt-3 text-xs text-green-600">This month</div>
          </div>
        </div>

        {/* Net */}
        <div className={`overflow-hidden shadow-lg rounded-xl border hover:shadow-xl transition-shadow ${
          (summary?.net || 0) >= 0
            ? 'bg-gradient-to-br from-blue-50 to-indigo-50 border-blue-200'
            : 'bg-gradient-to-br from-red-50 to-pink-50 border-red-200'
        }`}>
          <div className="px-6 py-6">
            <dt className={`text-sm font-medium uppercase tracking-wide mb-2 ${
              (summary?.net || 0) >= 0 ? 'text-blue-700' : 'text-red-700'
            }`}>Net</dt>
            <dd className={`text-4xl font-bold ${
              (summary?.net || 0) >= 0 ? 'text-blue-600' : 'text-red-600'
            }`}>
              ${summary?.net?.toFixed(2) || '0.00'}
            </dd>
            <div className={`mt-3 text-xs ${
              (summary?.net || 0) >= 0 ? 'text-blue-600' : 'text-red-600'
            }`}>Income - Spending</div>
          </div>
        </div>
      </div>

      {/* Category Breakdown */}
      {summary?.category_breakdown && summary.category_breakdown.length > 0 && (
        <div className="bg-white shadow-lg rounded-xl border border-gray-200">
          <div className="px-6 py-6">
            <h3 className="text-2xl font-bold text-gray-900 mb-6">Category Breakdown</h3>
            <div className="space-y-6">
              {summary.category_breakdown.map((category) => (
                <div key={category.category} className="p-4 bg-gray-50 rounded-lg">
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-base font-semibold text-gray-800">
                      {category.category || 'Uncategorized'}
                    </span>
                    <div className="text-right">
                      <div className="text-base font-bold text-gray-900">
                        ${category.amount.toFixed(2)}
                      </div>
                      <div className="text-sm text-gray-500">
                        {category.percentage.toFixed(1)}%
                      </div>
                    </div>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-3 mb-2">
                    <div
                      className="bg-gradient-to-r from-indigo-500 to-purple-600 h-3 rounded-full transition-all duration-500"
                      style={{ width: `${category.percentage}%` }}
                    ></div>
                  </div>
                  <div className="text-sm text-gray-600">
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
