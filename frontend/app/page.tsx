'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { getYearlySummary, getMerchantAnalysis, getAccounts, getDateRangeSummary } from '@/lib/api';
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
  const router = useRouter();
  const searchParams = useSearchParams();

  // Initialize from URL params or defaults
  const now = new Date();
  const defaultStartDate = `${now.getFullYear()}-01-01`;
  const defaultEndDate = `${now.getFullYear()}-12-31`;

  const [summary, setSummary] = useState<MonthlySummary | null>(null);
  const [yearlySummary, setYearlySummary] = useState<YearlySummary | null>(null);
  const [topMerchants, setTopMerchants] = useState<MerchantData[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>(searchParams.get('account_id') || '');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Date range filter - initialize from URL params
  const [startDate, setStartDate] = useState(searchParams.get('start_date') || defaultStartDate);
  const [endDate, setEndDate] = useState(searchParams.get('end_date') || defaultEndDate);

  // Update URL when filters change (separate effect to avoid loops)
  useEffect(() => {
    const params = new URLSearchParams();
    if (startDate !== defaultStartDate) params.set('start_date', startDate);
    if (endDate !== defaultEndDate) params.set('end_date', endDate);
    if (selectedAccount) params.set('account_id', selectedAccount);

    const queryString = params.toString();
    const newUrl = queryString ? `/?${queryString}` : '/';

    // Only update if URL actually changed
    if (window.location.search !== (queryString ? `?${queryString}` : '')) {
      router.replace(newUrl, { scroll: false });
    }
  }, [startDate, endDate, selectedAccount, defaultStartDate, defaultEndDate, router]);

  useEffect(() => {
    loadData();
  }, [selectedAccount, startDate, endDate]);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);

      const accountsData = await getAccounts();
      setAccounts(accountsData.accounts || []);

      // Load date range summary
      const dateRangeData = await getDateRangeSummary(
        startDate,
        endDate,
        selectedAccount || undefined
      );
      setSummary({
        total_spend: dateRangeData.total_spend,
        total_income: dateRangeData.total_income,
        net: dateRangeData.net,
        category_breakdown: dateRangeData.category_breakdown,
      });

      // Load yearly for bar chart context
      const yearlyData = await getYearlySummary(
        parseInt(startDate.split('-')[0]),
        selectedAccount || undefined
      );
      setYearlySummary(yearlyData);

      // Merchant analysis for range
      const merchantData = await getMerchantAnalysis(startDate, endDate, 10);
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

  const dateRangeLabel = `${new Date(startDate + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} - ${new Date(endDate + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;

  const selectedYear = parseInt(startDate.split('-')[0]);

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
                <p className="text-2xl text-indigo-100 font-medium">{dateRangeLabel}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Filters with Glass Effect */}
        <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-3xl border border-white/50 p-8 mb-10">
          <h3 className="text-xl font-bold text-gray-900 mb-6">Filters</h3>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div>
              <label htmlFor="start-date" className="block text-sm font-bold text-gray-700 mb-3">
                Start Date
              </label>
              <input
                type="date"
                id="start-date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="block w-full px-5 py-4 bg-white border-2 border-gray-200 rounded-2xl shadow-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/30 focus:border-indigo-500 text-base font-medium transition-all hover:border-indigo-300"
              />
            </div>

            <div>
              <label htmlFor="end-date" className="block text-sm font-bold text-gray-700 mb-3">
                End Date
              </label>
              <input
                type="date"
                id="end-date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="block w-full px-5 py-4 bg-white border-2 border-gray-200 rounded-2xl shadow-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/30 focus:border-indigo-500 text-base font-medium transition-all hover:border-indigo-300"
              />
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

            <div>
              <label className="block text-sm font-bold text-gray-700 mb-3">
                Quick Select
              </label>
              <select
                onChange={(e) => {
                  const today = new Date();
                  const year = today.getFullYear();
                  switch (e.target.value) {
                    case 'ytd':
                      setStartDate(`${year}-01-01`);
                      setEndDate(today.toISOString().split('T')[0]);
                      break;
                    case 'year':
                      setStartDate(`${year}-01-01`);
                      setEndDate(`${year}-12-31`);
                      break;
                    case 'last-year':
                      setStartDate(`${year - 1}-01-01`);
                      setEndDate(`${year - 1}-12-31`);
                      break;
                    case 'q1':
                      setStartDate(`${year}-01-01`);
                      setEndDate(`${year}-03-31`);
                      break;
                    case 'q2':
                      setStartDate(`${year}-04-01`);
                      setEndDate(`${year}-06-30`);
                      break;
                    case 'q3':
                      setStartDate(`${year}-07-01`);
                      setEndDate(`${year}-09-30`);
                      break;
                    case 'q4':
                      setStartDate(`${year}-10-01`);
                      setEndDate(`${year}-12-31`);
                      break;
                    case 'last-30':
                      const d30 = new Date(today);
                      d30.setDate(d30.getDate() - 30);
                      setStartDate(d30.toISOString().split('T')[0]);
                      setEndDate(today.toISOString().split('T')[0]);
                      break;
                    case 'last-90':
                      const d90 = new Date(today);
                      d90.setDate(d90.getDate() - 90);
                      setStartDate(d90.toISOString().split('T')[0]);
                      setEndDate(today.toISOString().split('T')[0]);
                      break;
                  }
                }}
                className="block w-full px-5 py-4 bg-white border-2 border-gray-200 rounded-2xl shadow-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/30 focus:border-indigo-500 text-base font-medium transition-all hover:border-indigo-300"
                defaultValue=""
              >
                <option value="" disabled>Select preset...</option>
                <option value="ytd">Year to Date</option>
                <option value="year">Full Year {new Date().getFullYear()}</option>
                <option value="last-year">Last Year {new Date().getFullYear() - 1}</option>
                <option value="q1">Q1 (Jan-Mar)</option>
                <option value="q2">Q2 (Apr-Jun)</option>
                <option value="q3">Q3 (Jul-Sep)</option>
                <option value="q4">Q4 (Oct-Dec)</option>
                <option value="last-30">Last 30 Days</option>
                <option value="last-90">Last 90 Days</option>
              </select>
            </div>
          </div>
        </div>

        {/* Main Stats Cards */}
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-10">
          {/* Total Spend */}
          <div className="group relative overflow-hidden bg-gradient-to-br from-rose-500 to-pink-600 rounded-3xl shadow-2xl hover:shadow-rose-500/50 transform hover:-translate-y-2 transition-all duration-300">
            <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16"></div>
            <div className="absolute bottom-0 left-0 w-24 h-24 bg-white/10 rounded-full -ml-12 -mb-12"></div>
            <div className="relative px-8 py-10">
              <dt className="text-sm font-bold text-white/80 uppercase tracking-wider mb-6">Total Spend</dt>
              <dd className="text-5xl font-black text-white mb-4">
                ${summary?.total_spend?.toFixed(2) || '0.00'}
              </dd>
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
              <div className="text-sm font-semibold text-white/70">In selected range</div>
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

          {/* Range Total */}
          <div className="group relative overflow-hidden bg-gradient-to-br from-purple-500 to-violet-600 rounded-3xl shadow-2xl hover:shadow-purple-500/50 transform hover:-translate-y-2 transition-all duration-300">
            <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16"></div>
            <div className="absolute bottom-0 left-0 w-24 h-24 bg-white/10 rounded-full -ml-12 -mb-12"></div>
            <div className="relative px-8 py-8">
              <dt className="text-sm font-bold text-white/80 uppercase tracking-wider mb-4">{selectedYear} Total</dt>
              <dd className="text-5xl font-black text-white mb-3">
                ${(yearlySummary?.total_spend || 0).toFixed(2)}
              </dd>
              <div className="text-sm font-semibold text-white/70">Full year spending</div>
            </div>
          </div>
        </div>

        {/* Yearly Spending Bar Chart */}
        {yearlySummary?.monthly_data && yearlySummary.monthly_data.length > 0 && (() => {
          const maxYearSpend = Math.max(...yearlySummary.monthly_data.map(m => m.total_spend), 1);
          const chartHeight = 200; // pixels
          const startMonth = parseInt(startDate.split('-')[1]);
          const endMonth = parseInt(endDate.split('-')[1]);
          const startYear = parseInt(startDate.split('-')[0]);
          const endYear = parseInt(endDate.split('-')[0]);

          return (
            <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-3xl border border-white/50 p-8 mb-10">
              <h3 className="text-2xl font-bold text-gray-900 mb-8">{selectedYear} Spending</h3>
              <div className="flex items-end justify-between gap-2" style={{ height: `${chartHeight}px` }}>
                {yearlySummary.monthly_data.map((monthData) => {
                  const barHeight = Math.max((monthData.total_spend / maxYearSpend) * chartHeight, 4);
                  // Highlight months that fall within the selected date range
                  const isInRange = selectedYear >= startYear && selectedYear <= endYear &&
                    ((selectedYear === startYear && selectedYear === endYear && monthData.month >= startMonth && monthData.month <= endMonth) ||
                     (selectedYear === startYear && selectedYear < endYear && monthData.month >= startMonth) ||
                     (selectedYear > startYear && selectedYear === endYear && monthData.month <= endMonth) ||
                     (selectedYear > startYear && selectedYear < endYear));

                  const handleBarClick = () => {
                    // Calculate first and last day of the month
                    const monthStart = `${selectedYear}-${String(monthData.month).padStart(2, '0')}-01`;
                    const lastDay = new Date(selectedYear, monthData.month, 0).getDate();
                    const monthEnd = `${selectedYear}-${String(monthData.month).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;

                    const params = new URLSearchParams({
                      start_date: monthStart,
                      end_date: monthEnd,
                    });
                    if (selectedAccount) {
                      params.set('account_id', selectedAccount);
                    }
                    router.push(`/transactions?${params.toString()}`);
                  };

                  return (
                    <div
                      key={monthData.month}
                      onClick={handleBarClick}
                      className="flex-1 flex flex-col items-center group cursor-pointer"
                    >
                      <div className="relative flex items-end justify-center w-full" style={{ height: `${chartHeight}px` }}>
                        <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200 absolute -top-14 left-1/2 transform -translate-x-1/2 bg-gray-900 text-white text-xs font-bold px-3 py-2 rounded-lg whitespace-nowrap z-10">
                          ${monthData.total_spend.toFixed(0)}
                          <div className="text-gray-400 text-xs">{monthData.transaction_count} txns</div>
                          <div className="text-indigo-300 text-xs">Click to view</div>
                          <div className="absolute bottom-0 left-1/2 transform -translate-x-1/2 translate-y-full">
                            <div className="border-8 border-transparent border-t-gray-900"></div>
                          </div>
                        </div>
                        <div
                          className={`w-full max-w-10 rounded-t-lg transition-all duration-300 ${
                            isInRange
                              ? 'bg-gradient-to-t from-indigo-600 to-purple-500 shadow-lg shadow-indigo-500/30 group-hover:from-indigo-500 group-hover:to-purple-400'
                              : 'bg-gradient-to-t from-gray-300 to-gray-400 group-hover:from-indigo-400 group-hover:to-purple-400'
                          }`}
                          style={{ height: `${barHeight}px` }}
                        ></div>
                      </div>
                      <div className={`mt-3 text-sm font-bold ${isInRange ? 'text-indigo-600' : 'text-gray-600'} group-hover:text-indigo-600 transition-colors`}>
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

                  const handleCategoryClick = () => {
                    const params = new URLSearchParams({
                      start_date: startDate,
                      end_date: endDate,
                    });
                    if (category.category) {
                      params.set('category', category.category);
                    }
                    if (selectedAccount) {
                      params.set('account_id', selectedAccount);
                    }
                    router.push(`/transactions?${params.toString()}`);
                  };

                  return (
                    <div
                      key={category.category}
                      onClick={handleCategoryClick}
                      className="group p-5 bg-white/50 backdrop-blur-sm rounded-2xl hover:bg-white hover:shadow-xl transition-all duration-300 border border-gray-100 cursor-pointer"
                    >
                      <div className="flex justify-between items-center mb-3">
                        <span className="text-base font-bold text-gray-900 group-hover:text-indigo-600 transition-colors">
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
                      <div className="mt-3 text-sm font-semibold text-gray-600 flex items-center justify-between">
                        <span>{category.count} transaction{category.count !== 1 ? 's' : ''}</span>
                        <span className="text-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity">View &rarr;</span>
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

                  const handleMerchantClick = () => {
                    const params = new URLSearchParams({
                      start_date: startDate,
                      end_date: endDate,
                      description: merchant.merchant,
                    });
                    if (selectedAccount) {
                      params.set('account_id', selectedAccount);
                    }
                    router.push(`/transactions?${params.toString()}`);
                  };

                  return (
                    <div
                      key={merchant.merchant}
                      onClick={handleMerchantClick}
                      className="group flex items-center gap-5 p-5 bg-white/50 backdrop-blur-sm rounded-2xl hover:bg-white hover:shadow-xl transition-all duration-300 border border-gray-100 cursor-pointer"
                    >
                      <div className={`flex-shrink-0 w-10 h-10 bg-gradient-to-br ${rankColor} rounded-xl flex items-center justify-center shadow-lg`}>
                        <span className="text-white font-bold text-base">#{index + 1}</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-base font-bold text-gray-900 truncate mb-1 group-hover:text-indigo-600 transition-colors">
                          {merchant.merchant}
                        </div>
                        <div className="text-sm font-semibold text-gray-600">
                          {merchant.count} · Avg ${merchant.avg_amount.toFixed(2)}
                        </div>
                      </div>
                      <div className="text-right flex flex-col items-end">
                        <div className="text-2xl font-black text-gray-900">
                          ${merchant.total.toFixed(2)}
                        </div>
                        <span className="text-indigo-500 text-sm opacity-0 group-hover:opacity-100 transition-opacity">View &rarr;</span>
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
