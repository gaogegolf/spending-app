'use client';

import { useEffect, useState } from 'react';
import { getMonthlySummary, getYearlySummary, getMerchantAnalysis, getAccounts } from '@/lib/api';
import { Account } from '@/lib/types';

interface MonthlySummary {
  total_spend: number;
  total_income: number;
  net: number;
  category_breakdown: Array<{
    category: string;
    amount: number;
    percentage: number;
    count: number;
  }>;
}

interface YearlySummary {
  year: number;
  total_spend: number;
  total_income: number;
  monthly_data: Array<{
    month: number;
    month_name: string;
    total_spend: number;
    total_income: number;
    net: number;
    transaction_count: number;
  }>;
}

interface MerchantData {
  merchant: string;
  total: number;
  count: number;
  avg_amount: number;
}

export default function Dashboard() {
  const [summary, setSummary] = useState<MonthlySummary | null>(null);
  const [yearlySummary, setYearlySummary] = useState<YearlySummary | null>(null);
  const [topMerchants, setTopMerchants] = useState<MerchantData[]>([]);
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

      const accountsData = await getAccounts();
      setAccounts(accountsData.accounts || []);

      const summaryData = await getMonthlySummary(
        selectedYear,
        selectedMonth,
        selectedAccount || undefined
      );
      setSummary(summaryData);

      const yearlyData = await getYearlySummary(
        selectedYear,
        selectedAccount || undefined
      );
      setYearlySummary(yearlyData);

      const firstDay = new Date(selectedYear, selectedMonth - 1, 1).toISOString().split('T')[0];
      const lastDay = new Date(selectedYear, selectedMonth, 0).toISOString().split('T')[0];
      const merchantData = await getMerchantAnalysis(firstDay, lastDay, 10);
      setTopMerchants(merchantData.top_merchants || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
          <div className="flex flex-col items-center justify-center space-y-4">
            <div className="w-16 h-16 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
            <p className="text-xl font-semibold text-gray-700 animate-pulse">Loading your dashboard...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
          <div className="bg-white rounded-2xl shadow-2xl border border-red-200 p-8">
            <h3 className="text-xl font-bold text-gray-900 mb-2">Oops! Something went wrong</h3>
            <p className="text-gray-600 mb-4">{error}</p>
            <button
              onClick={loadData}
              className="px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-xl hover:from-indigo-700 hover:to-purple-700 transform hover:scale-105 transition-all duration-200 shadow-lg"
            >
              Try Again
            </button>
          </div>
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

  const ytdSpend = yearlySummary?.monthly_data
    .filter(m => m.month <= selectedMonth)
    .reduce((sum, m) => sum + m.total_spend, 0) || 0;

  const prevMonth = selectedMonth === 1 ? 12 : selectedMonth - 1;
  const prevMonthData = yearlySummary?.monthly_data.find(m => m.month === prevMonth);
  const currentMonthSpend = summary?.total_spend || 0;
  const prevMonthSpend = prevMonthData?.total_spend || 0;
  const spendChange = prevMonthSpend > 0
    ? ((currentMonthSpend - prevMonthSpend) / prevMonthSpend) * 100
    : 0;


  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100 pb-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header with Gradient */}
        <div className="mb-10">
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-3xl transform -skew-y-1 shadow-2xl"></div>
            <div className="relative bg-gradient-to-r from-indigo-600 to-purple-600 rounded-3xl shadow-2xl p-8">
              <div>
                <h1 className="text-5xl font-black text-white mb-2 tracking-tight">
                  Financial Dashboard
                </h1>
                <p className="text-2xl text-indigo-100 font-medium">{monthName}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Filters with Glass Effect */}
        <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-3xl border border-white/50 p-8 mb-10">
          <h3 className="text-xl font-bold text-gray-900 mb-6">Filters</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <label htmlFor="month-filter" className="block text-sm font-bold text-gray-700 mb-3">
                Month
              </label>
              <select
                id="month-filter"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(Number(e.target.value))}
                className="block w-full px-5 py-4 bg-white border-2 border-gray-200 rounded-2xl shadow-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/30 focus:border-indigo-500 text-base font-medium transition-all hover:border-indigo-300"
              >
                {months.map((month, index) => (
                  <option key={month} value={index + 1}>
                    {month}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="year-filter" className="block text-sm font-bold text-gray-700 mb-3">
                Year
              </label>
              <select
                id="year-filter"
                value={selectedYear}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
                className="block w-full px-5 py-4 bg-white border-2 border-gray-200 rounded-2xl shadow-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/30 focus:border-indigo-500 text-base font-medium transition-all hover:border-indigo-300"
              >
                {years.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </div>

            {accounts.length > 0 && (
              <div>
                <label htmlFor="account-filter" className="block text-sm font-bold text-gray-700 mb-3">
                  Account
                </label>
                <select
                  id="account-filter"
                  value={selectedAccount}
                  onChange={(e) => setSelectedAccount(e.target.value)}
                  className="block w-full px-5 py-4 bg-white border-2 border-gray-200 rounded-2xl shadow-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/30 focus:border-indigo-500 text-base font-medium transition-all hover:border-indigo-300"
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

        {/* Main Stats Cards */}
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-10">
          {/* Total Spend */}
          <div className="group relative overflow-hidden bg-gradient-to-br from-rose-500 to-pink-600 rounded-3xl shadow-2xl hover:shadow-rose-500/50 transform hover:-translate-y-2 transition-all duration-300">
            <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16"></div>
            <div className="absolute bottom-0 left-0 w-24 h-24 bg-white/10 rounded-full -ml-12 -mb-12"></div>
            <div className="relative px-8 py-10">
              <dt className="text-sm font-bold text-white/80 uppercase tracking-wider mb-6">This Month</dt>
              <dd className="text-5xl font-black text-white mb-4">
                ${summary?.total_spend?.toFixed(2) || '0.00'}
              </dd>
              {spendChange !== 0 && (
                <div className={`inline-flex items-center px-4 py-2 rounded-xl text-sm font-bold ${
                  spendChange > 0
                    ? 'bg-red-900/30 text-white'
                    : 'bg-green-900/30 text-white'
                }`}>
                  {spendChange > 0 ? '↑' : '↓'} {Math.abs(spendChange).toFixed(1)}% vs last month
                </div>
              )}
            </div>
          </div>

          {/* Total Income */}
          <div className="group relative overflow-hidden bg-gradient-to-br from-emerald-500 to-teal-600 rounded-3xl shadow-2xl hover:shadow-emerald-500/50 transform hover:-translate-y-2 transition-all duration-300">
            <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16"></div>
            <div className="absolute bottom-0 left-0 w-24 h-24 bg-white/10 rounded-full -ml-12 -mb-12"></div>
            <div className="relative px-8 py-8">
              <dt className="text-sm font-bold text-white/80 uppercase tracking-wider mb-4">Income</dt>
              <dd className="text-5xl font-black text-white mb-3">
                ${summary?.total_income?.toFixed(2) || '0.00'}
              </dd>
              <div className="text-sm font-semibold text-white/70">This month</div>
            </div>
          </div>

          {/* Net */}
          <div className={`group relative overflow-hidden rounded-3xl shadow-2xl transform hover:-translate-y-2 transition-all duration-300 ${
            (summary?.net || 0) >= 0
              ? 'bg-gradient-to-br from-blue-500 to-indigo-600 hover:shadow-blue-500/50'
              : 'bg-gradient-to-br from-orange-500 to-red-600 hover:shadow-orange-500/50'
          }`}>
            <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16"></div>
            <div className="absolute bottom-0 left-0 w-24 h-24 bg-white/10 rounded-full -ml-12 -mb-12"></div>
            <div className="relative px-8 py-8">
              <dt className="text-sm font-bold text-white/80 uppercase tracking-wider mb-4">Net</dt>
              <dd className="text-5xl font-black text-white mb-3">
                ${summary?.net?.toFixed(2) || '0.00'}
              </dd>
              <div className="text-sm font-semibold text-white/70">Income - Spending</div>
            </div>
          </div>

          {/* YTD Spending */}
          <div className="group relative overflow-hidden bg-gradient-to-br from-purple-500 to-violet-600 rounded-3xl shadow-2xl hover:shadow-purple-500/50 transform hover:-translate-y-2 transition-all duration-300">
            <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16"></div>
            <div className="absolute bottom-0 left-0 w-24 h-24 bg-white/10 rounded-full -ml-12 -mb-12"></div>
            <div className="relative px-8 py-8">
              <dt className="text-sm font-bold text-white/80 uppercase tracking-wider mb-4">YTD Spending</dt>
              <dd className="text-5xl font-black text-white mb-3">
                ${ytdSpend.toFixed(2)}
              </dd>
              <div className="text-sm font-semibold text-white/70">Year to date</div>
            </div>
          </div>
        </div>

        {/* Yearly Spending Bar Chart */}
        {yearlySummary?.monthly_data && yearlySummary.monthly_data.length > 0 && (() => {
          const maxYearSpend = Math.max(...yearlySummary.monthly_data.map(m => m.total_spend), 1);
          const chartHeight = 200; // pixels

          return (
            <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-3xl border border-white/50 p-8 mb-10">
              <h3 className="text-2xl font-bold text-gray-900 mb-8">{selectedYear} Spending</h3>
              <div className="flex items-end justify-between gap-2" style={{ height: `${chartHeight}px` }}>
                {yearlySummary.monthly_data.map((monthData) => {
                  const barHeight = Math.max((monthData.total_spend / maxYearSpend) * chartHeight, 4);
                  const isCurrentMonth = monthData.month === selectedMonth;

                  return (
                    <div key={monthData.month} className="flex-1 flex flex-col items-center group">
                      <div className="relative flex items-end justify-center w-full" style={{ height: `${chartHeight}px` }}>
                        <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200 absolute -top-14 left-1/2 transform -translate-x-1/2 bg-gray-900 text-white text-xs font-bold px-3 py-2 rounded-lg whitespace-nowrap z-10">
                          ${monthData.total_spend.toFixed(0)}
                          <div className="text-gray-400 text-xs">{monthData.transaction_count} txns</div>
                          <div className="absolute bottom-0 left-1/2 transform -translate-x-1/2 translate-y-full">
                            <div className="border-8 border-transparent border-t-gray-900"></div>
                          </div>
                        </div>
                        <div
                          className={`w-full max-w-10 rounded-t-lg transition-all duration-300 cursor-pointer ${
                            isCurrentMonth
                              ? 'bg-gradient-to-t from-indigo-600 to-purple-500 shadow-lg shadow-indigo-500/30'
                              : 'bg-gradient-to-t from-gray-300 to-gray-400 group-hover:from-indigo-400 group-hover:to-purple-400'
                          }`}
                          style={{ height: `${barHeight}px` }}
                        ></div>
                      </div>
                      <div className={`mt-3 text-sm font-bold ${isCurrentMonth ? 'text-indigo-600' : 'text-gray-600'}`}>
                        {monthData.month_name.substring(0, 3)}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })()}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-10">
          {/* Category Breakdown */}
          {summary?.category_breakdown && summary.category_breakdown.length > 0 && (
            <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-3xl border border-white/50 p-8">
              <h3 className="text-2xl font-bold text-gray-900 mb-8">Categories</h3>
              <div className="space-y-5">
                {[...summary.category_breakdown].sort((a, b) => b.amount - a.amount).slice(0, 8).map((category, index) => {
                  const gradients = [
                    'from-blue-500 to-cyan-500',
                    'from-purple-500 to-pink-500',
                    'from-green-500 to-emerald-500',
                    'from-orange-500 to-red-500',
                    'from-yellow-500 to-amber-500',
                    'from-indigo-500 to-blue-500',
                    'from-teal-500 to-cyan-500',
                    'from-rose-500 to-pink-500',
                  ];
                  const gradient = gradients[index % gradients.length];

                  return (
                    <div key={category.category} className="group p-5 bg-white/50 backdrop-blur-sm rounded-2xl hover:bg-white hover:shadow-xl transition-all duration-300 border border-gray-100">
                      <div className="flex justify-between items-center mb-3">
                        <span className="text-base font-bold text-gray-900">
                          {category.category || 'Uncategorized'}
                        </span>
                        <div className="text-right">
                          <div className="text-xl font-black text-gray-900">
                            ${category.amount.toFixed(2)}
                          </div>
                          <div className="text-sm font-semibold text-gray-500">
                            {category.percentage.toFixed(1)}%
                          </div>
                        </div>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden shadow-inner">
                        <div
                          className={`bg-gradient-to-r ${gradient} h-3 rounded-full transition-all duration-700 ease-out`}
                          style={{ width: `${category.percentage}%` }}
                        ></div>
                      </div>
                      <div className="mt-3 text-sm font-semibold text-gray-600">
                        {category.count} transaction{category.count !== 1 ? 's' : ''}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Top Merchants */}
          {topMerchants.length > 0 && (
            <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-3xl border border-white/50 p-8">
              <h3 className="text-2xl font-bold text-gray-900 mb-8">Top Merchants</h3>
              <div className="space-y-4">
                {topMerchants.map((merchant, index) => {
                  const medalColors = [
                    'from-yellow-400 to-yellow-600',
                    'from-gray-300 to-gray-500',
                    'from-orange-400 to-orange-600',
                  ];
                  const rankColor = index < 3 ? medalColors[index] : 'from-indigo-400 to-indigo-600';

                  return (
                    <div key={merchant.merchant} className="group flex items-center gap-5 p-5 bg-white/50 backdrop-blur-sm rounded-2xl hover:bg-white hover:shadow-xl transition-all duration-300 border border-gray-100">
                      <div className={`flex-shrink-0 w-10 h-10 bg-gradient-to-br ${rankColor} rounded-xl flex items-center justify-center shadow-lg`}>
                        <span className="text-white font-bold text-base">#{index + 1}</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-base font-bold text-gray-900 truncate mb-1">
                          {merchant.merchant}
                        </div>
                        <div className="text-sm font-semibold text-gray-600">
                          {merchant.count} · Avg ${merchant.avg_amount.toFixed(2)}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-2xl font-black text-gray-900">
                          ${merchant.total.toFixed(2)}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Empty State */}
        {(!summary?.category_breakdown || summary.category_breakdown.length === 0) && (
          <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-3xl border border-white/50 p-16 text-center">
            <h3 className="text-2xl font-bold text-gray-900 mb-3">No transactions yet</h3>
            <p className="text-gray-600 mb-8 text-lg">Get started by importing your transaction data</p>
            <a
              href="/imports"
              className="inline-flex items-center px-8 py-4 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-bold text-lg rounded-2xl hover:from-indigo-700 hover:to-purple-700 transform hover:scale-105 transition-all duration-200 shadow-2xl hover:shadow-indigo-500/50"
            >
              Import Transactions
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
