'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { getYearlySummary, getMerchantAnalysis, getAccounts, getDateRangeSummary, getNetWorth } from '@/lib/api';
import { Account, NetWorthData } from '@/lib/types';

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
  const [netWorth, setNetWorth] = useState<NetWorthData | null>(null);

  // Date range filter - initialize from URL params
  const [startDate, setStartDate] = useState(searchParams.get('start_date') || defaultStartDate);
  const [endDate, setEndDate] = useState(searchParams.get('end_date') || defaultEndDate);

  // Bar chart mode: 'expense', 'income', 'net'
  const [chartMode, setChartMode] = useState<'expense' | 'income' | 'net'>('expense');

  // Filter panel state
  const [filtersExpanded, setFiltersExpanded] = useState(false);

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
      const merchantData = await getMerchantAnalysis(startDate, endDate, 100);
      setTopMerchants(merchantData.top_merchants || []);

      // Net worth data from brokerage accounts
      try {
        const netWorthData = await getNetWorth();
        setNetWorth(netWorthData);
      } catch {
        // Net worth data is optional - don't fail if no brokerage accounts exist
        setNetWorth(null);
      }
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

        {/* Filters with Collapsible Panel */}
        <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-3xl border border-white/50 overflow-hidden mb-10">
          {/* Filter Header - Always visible */}
          <div
            className="px-8 py-5 bg-gradient-to-r from-gray-50/80 to-white/80 border-b border-gray-100 cursor-pointer hover:bg-gray-50/90 transition-colors"
            onClick={() => setFiltersExpanded(!filtersExpanded)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center bg-indigo-100 transition-transform duration-200 ${filtersExpanded ? 'rotate-90' : ''}`}>
                  <span className="text-indigo-600 text-sm font-bold">▶</span>
                </div>
                <div>
                  <h3 className="text-lg font-bold text-gray-900">Filters & Date Range</h3>
                  <p className="text-sm text-gray-500">{dateRangeLabel}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {selectedAccount && (
                  <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
                    {accounts.find(a => a.id === selectedAccount)?.name || 'Account filtered'}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Quick Date Presets - Always visible */}
          <div className="px-8 py-4 bg-gray-50/50 border-b border-gray-100">
            <div className="flex flex-wrap gap-2">
              {[
                { value: 'ytd', label: 'Year to Date' },
                { value: 'year', label: `Full ${new Date().getFullYear()}` },
                { value: 'last-year', label: `${new Date().getFullYear() - 1}` },
                { value: 'q1', label: 'Q1' },
                { value: 'q2', label: 'Q2' },
                { value: 'q3', label: 'Q3' },
                { value: 'q4', label: 'Q4' },
                { value: 'last-30', label: 'Last 30 Days' },
                { value: 'last-90', label: 'Last 90 Days' },
              ].map((preset) => {
                const handlePresetClick = () => {
                  const today = new Date();
                  const year = today.getFullYear();
                  switch (preset.value) {
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
                };

                return (
                  <button
                    key={preset.value}
                    onClick={handlePresetClick}
                    className="px-4 py-2 text-sm font-semibold text-gray-600 bg-white hover:bg-indigo-50 hover:text-indigo-700 rounded-xl transition-all border border-gray-200 hover:border-indigo-300 shadow-sm"
                  >
                    {preset.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Expanded Filter Content */}
          {filtersExpanded && (
            <div className="p-8">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Date Range */}
                <div className="md:col-span-2">
                  <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">
                    Custom Date Range
                  </label>
                  <div className="flex items-center gap-4">
                    <input
                      type="date"
                      id="start-date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className="flex-1 px-4 py-3 bg-white border-2 border-gray-200 rounded-xl shadow-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-500 text-sm font-medium transition-all hover:border-indigo-300"
                    />
                    <span className="text-gray-400 font-medium">to</span>
                    <input
                      type="date"
                      id="end-date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="flex-1 px-4 py-3 bg-white border-2 border-gray-200 rounded-xl shadow-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-500 text-sm font-medium transition-all hover:border-indigo-300"
                    />
                  </div>
                </div>

                {/* Account Filter */}
                {accounts.length > 0 && (
                  <div>
                    <label htmlFor="account-filter" className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">
                      Account
                    </label>
                    <select
                      id="account-filter"
                      value={selectedAccount}
                      onChange={(e) => setSelectedAccount(e.target.value)}
                      className="block w-full px-4 py-3 bg-white border-2 border-gray-200 rounded-xl shadow-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-500 text-sm font-medium transition-all hover:border-indigo-300"
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
          )}
        </div>

        {/* Main Stats Cards */}
        {(() => {
          // Calculate days in range for daily average
          const start = new Date(startDate);
          const end = new Date(endDate);
          const daysInRange = Math.max(1, Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1);
          const dailyAvgSpend = (summary?.total_spend || 0) / daysInRange;
          const categoryCount = summary?.category_breakdown?.length || 0;

          return (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4 mb-10">
              {/* Total Spend */}
              <div className="group relative overflow-hidden bg-gradient-to-br from-rose-500 to-pink-600 rounded-2xl shadow-xl hover:shadow-rose-500/40 transform hover:-translate-y-1 transition-all duration-300">
                <div className="absolute top-0 right-0 w-24 h-24 bg-white/10 rounded-full -mr-12 -mt-12"></div>
                <div className="relative px-6 py-6">
                  <div className="flex items-center justify-between mb-3">
                    <dt className="text-xs font-bold text-white/80 uppercase tracking-wider">Total Spend</dt>
                    <span className="text-2xl">💸</span>
                  </div>
                  <dd className="text-3xl font-black text-white mb-2">
                    ${(summary?.total_spend || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </dd>
                  <div className="flex items-center gap-2 text-sm text-white/70">
                    <span className="font-medium">${dailyAvgSpend.toFixed(0)}/day avg</span>
                  </div>
                </div>
              </div>

              {/* Total Income */}
              <div className="group relative overflow-hidden bg-gradient-to-br from-emerald-500 to-teal-600 rounded-2xl shadow-xl hover:shadow-emerald-500/40 transform hover:-translate-y-1 transition-all duration-300">
                <div className="absolute top-0 right-0 w-24 h-24 bg-white/10 rounded-full -mr-12 -mt-12"></div>
                <div className="relative px-6 py-6">
                  <div className="flex items-center justify-between mb-3">
                    <dt className="text-xs font-bold text-white/80 uppercase tracking-wider">Income</dt>
                    <span className="text-2xl">💰</span>
                  </div>
                  <dd className="text-3xl font-black text-white mb-2">
                    ${(summary?.total_income || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </dd>
                  <div className="flex items-center gap-2 text-sm text-white/70">
                    <span className="font-medium">In selected range</span>
                  </div>
                </div>
              </div>

              {/* Net */}
              <div className={`group relative overflow-hidden rounded-2xl shadow-xl transform hover:-translate-y-1 transition-all duration-300 ${
                (summary?.net || 0) >= 0
                  ? 'bg-gradient-to-br from-blue-500 to-indigo-600 hover:shadow-blue-500/40'
                  : 'bg-gradient-to-br from-orange-500 to-red-600 hover:shadow-orange-500/40'
              }`}>
                <div className="absolute top-0 right-0 w-24 h-24 bg-white/10 rounded-full -mr-12 -mt-12"></div>
                <div className="relative px-6 py-6">
                  <div className="flex items-center justify-between mb-3">
                    <dt className="text-xs font-bold text-white/80 uppercase tracking-wider">Net Savings</dt>
                    <span className="text-2xl">{(summary?.net || 0) >= 0 ? '📈' : '📉'}</span>
                  </div>
                  <dd className="text-3xl font-black text-white mb-2">
                    {(summary?.net || 0) >= 0 ? '+' : ''}{(summary?.net || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </dd>
                  <div className="flex items-center gap-2 text-sm text-white/70">
                    <span className="font-medium">
                      {(summary?.net || 0) >= 0 ? 'Saved this period' : 'Overspent this period'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Summary Stats */}
              <div className="group relative overflow-hidden bg-gradient-to-br from-slate-700 to-slate-900 rounded-2xl shadow-xl hover:shadow-slate-500/40 transform hover:-translate-y-1 transition-all duration-300">
                <div className="absolute top-0 right-0 w-24 h-24 bg-white/5 rounded-full -mr-12 -mt-12"></div>
                <div className="relative px-6 py-6">
                  <div className="flex items-center justify-between mb-3">
                    <dt className="text-xs font-bold text-white/80 uppercase tracking-wider">Quick Stats</dt>
                    <span className="text-2xl">📊</span>
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-white/70">Categories</span>
                      <span className="text-lg font-bold text-white">{categoryCount}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-white/70">Days</span>
                      <span className="text-lg font-bold text-white">{daysInRange}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-white/70">Year Total</span>
                      <span className="text-lg font-bold text-white">${((yearlySummary?.total_spend || 0) / 1000).toFixed(1)}k</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Net Worth - only show if brokerage data exists */}
              {netWorth && netWorth.current_total > 0 && (
                <Link href="/net-worth" className="block">
                  <div className="group relative overflow-hidden bg-gradient-to-br from-violet-500 to-purple-700 rounded-2xl shadow-xl hover:shadow-violet-500/40 transform hover:-translate-y-1 transition-all duration-300 cursor-pointer">
                    <div className="absolute top-0 right-0 w-24 h-24 bg-white/10 rounded-full -mr-12 -mt-12"></div>
                    <div className="relative px-6 py-6">
                      <div className="flex items-center justify-between mb-3">
                        <dt className="text-xs font-bold text-white/80 uppercase tracking-wider">Net Worth</dt>
                        <span className="text-2xl">🏦</span>
                      </div>
                      <dd className="text-3xl font-black text-white mb-2">
                        ${netWorth.current_total.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                      </dd>
                      <div className="flex items-center gap-2 text-sm text-white/70">
                        <span className="font-medium">{netWorth.accounts.length} account{netWorth.accounts.length !== 1 ? 's' : ''}</span>
                        <span className="text-white/50">·</span>
                        <span className="font-medium group-hover:text-white transition-colors">View details &rarr;</span>
                      </div>
                    </div>
                  </div>
                </Link>
              )}
            </div>
          );
        })()}

        {/* Yearly Bar Chart */}
        {yearlySummary?.monthly_data && yearlySummary.monthly_data.length > 0 && (() => {
          // Get the value based on chart mode
          const getValue = (m: typeof yearlySummary.monthly_data[0]) => {
            switch (chartMode) {
              case 'expense': return m.total_spend;
              case 'income': return m.total_income;
              case 'net': return m.net;
            }
          };

          // For net mode, we need to handle negative values
          const values = yearlySummary.monthly_data.map(m => getValue(m));
          const maxValue = Math.max(...values.map(v => Math.abs(v)), 1);
          const hasNegative = chartMode === 'net' && values.some(v => v < 0);

          const chartHeight = 200; // pixels
          const startMonth = parseInt(startDate.split('-')[1]);
          const endMonth = parseInt(endDate.split('-')[1]);
          const startYear = parseInt(startDate.split('-')[0]);
          const endYear = parseInt(endDate.split('-')[0]);

          const chartTitles = {
            expense: `${selectedYear} Spending`,
            income: `${selectedYear} Income`,
            net: `${selectedYear} Net (Income - Expense)`,
          };

          const barColors = {
            expense: {
              active: 'bg-gradient-to-t from-rose-600 to-pink-500 shadow-lg shadow-rose-500/30 group-hover:from-rose-500 group-hover:to-pink-400',
              inactive: 'bg-gradient-to-t from-gray-300 to-gray-400 group-hover:from-rose-400 group-hover:to-pink-400',
            },
            income: {
              active: 'bg-gradient-to-t from-emerald-600 to-teal-500 shadow-lg shadow-emerald-500/30 group-hover:from-emerald-500 group-hover:to-teal-400',
              inactive: 'bg-gradient-to-t from-gray-300 to-gray-400 group-hover:from-emerald-400 group-hover:to-teal-400',
            },
            net: {
              positive: 'bg-gradient-to-t from-blue-600 to-indigo-500 shadow-lg shadow-blue-500/30 group-hover:from-blue-500 group-hover:to-indigo-400',
              negative: 'bg-gradient-to-b from-orange-600 to-red-500 shadow-lg shadow-orange-500/30 group-hover:from-orange-500 group-hover:to-red-400',
              inactive: 'bg-gradient-to-t from-gray-300 to-gray-400 group-hover:from-blue-400 group-hover:to-indigo-400',
            },
          };

          return (
            <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-3xl border border-white/50 p-8 mb-10">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
                <h3 className="text-2xl font-bold text-gray-900">{chartTitles[chartMode]}</h3>
                <div className="flex rounded-xl bg-gray-100 p-1 relative z-20">
                  <button
                    onClick={() => setChartMode('expense')}
                    className={`px-4 py-2 text-sm font-semibold rounded-lg transition-all ${
                      chartMode === 'expense'
                        ? 'bg-white text-rose-600 shadow-md'
                        : 'text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    Expense
                  </button>
                  <button
                    onClick={() => setChartMode('income')}
                    className={`px-4 py-2 text-sm font-semibold rounded-lg transition-all ${
                      chartMode === 'income'
                        ? 'bg-white text-emerald-600 shadow-md'
                        : 'text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    Income
                  </button>
                  <button
                    onClick={() => setChartMode('net')}
                    className={`px-4 py-2 text-sm font-semibold rounded-lg transition-all ${
                      chartMode === 'net'
                        ? 'bg-white text-blue-600 shadow-md'
                        : 'text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    Net
                  </button>
                </div>
              </div>
              <div className={`flex items-end justify-between gap-2 ${hasNegative ? 'items-center' : ''}`} style={{ height: `${chartHeight}px` }}>
                {yearlySummary.monthly_data.map((monthData) => {
                  const value = getValue(monthData);
                  const barHeight = Math.max((Math.abs(value) / maxValue) * (hasNegative ? chartHeight / 2 : chartHeight), 4);
                  const isNegative = value < 0;

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

                  // Determine bar color based on mode and value
                  let barColorClass = '';
                  if (chartMode === 'net') {
                    if (isInRange) {
                      barColorClass = isNegative ? barColors.net.negative : barColors.net.positive;
                    } else {
                      barColorClass = barColors.net.inactive;
                    }
                  } else {
                    barColorClass = isInRange ? barColors[chartMode].active : barColors[chartMode].inactive;
                  }

                  return (
                    <div
                      key={monthData.month}
                      onClick={handleBarClick}
                      className="flex-1 flex flex-col items-center group cursor-pointer"
                    >
                      {/* Upper half (positive bars or all bars in non-net mode) */}
                      <div
                        className="relative flex items-end justify-center w-full"
                        style={{ height: hasNegative ? `${chartHeight / 2}px` : `${chartHeight}px` }}
                      >
                        {(!hasNegative || !isNegative) && (
                          <div className="relative">
                            <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200 absolute -top-8 left-1/2 transform -translate-x-1/2 bg-gray-900 text-white text-xs font-bold px-3 py-2 rounded-lg whitespace-nowrap z-30 pointer-events-none">
                              {chartMode === 'net' && value < 0 ? '-' : ''}${Math.abs(value).toFixed(0)}
                              <div className="absolute bottom-0 left-1/2 transform -translate-x-1/2 translate-y-full">
                                <div className="border-8 border-transparent border-t-gray-900"></div>
                              </div>
                            </div>
                            <div
                              className={`w-10 rounded-t-lg transition-all duration-300 ${barColorClass}`}
                              style={{ height: `${barHeight}px` }}
                            ></div>
                          </div>
                        )}
                      </div>
                      {/* Baseline for net mode */}
                      {hasNegative && (
                        <div className="w-full h-px bg-gray-400"></div>
                      )}
                      {/* Lower half (negative bars in net mode) */}
                      {hasNegative && (
                        <div
                          className="relative flex items-start justify-center w-full"
                          style={{ height: `${chartHeight / 2}px` }}
                        >
                          {isNegative && (
                            <div className="relative">
                              <div
                                className={`w-10 rounded-b-lg transition-all duration-300 ${barColorClass}`}
                                style={{ height: `${barHeight}px` }}
                              ></div>
                              <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200 absolute -bottom-8 left-1/2 transform -translate-x-1/2 bg-gray-900 text-white text-xs font-bold px-3 py-2 rounded-lg whitespace-nowrap z-30 pointer-events-none">
                                -${Math.abs(value).toFixed(0)}
                                <div className="absolute top-0 left-1/2 transform -translate-x-1/2 -translate-y-full">
                                  <div className="border-8 border-transparent border-b-gray-900"></div>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                      <div className={`mt-3 text-sm font-bold ${isInRange ? (chartMode === 'expense' ? 'text-rose-600' : chartMode === 'income' ? 'text-emerald-600' : 'text-blue-600') : 'text-gray-600'} group-hover:text-indigo-600 transition-colors`}>
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
              <div className="space-y-5 max-h-[600px] overflow-y-auto pr-2">
                {[...summary.category_breakdown].sort((a, b) => b.amount - a.amount).map((category, index) => {
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
              <div className="space-y-4 max-h-[600px] overflow-y-auto pr-2">
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

        {/* Quick Insights Section */}
        {summary?.category_breakdown && summary.category_breakdown.length > 0 && (() => {
          const sortedCategories = [...summary.category_breakdown].sort((a, b) => b.amount - a.amount);
          const topCategory = sortedCategories[0];
          const topMerchant = topMerchants[0];
          const savingsRate = summary.total_income > 0
            ? ((summary.net / summary.total_income) * 100).toFixed(1)
            : '0';

          // Calculate days in range
          const start = new Date(startDate);
          const end = new Date(endDate);
          const daysInRange = Math.max(1, Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1);
          const dailyAvgSpend = summary.total_spend / daysInRange;

          return (
            <div className="bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-pink-500/10 backdrop-blur-xl rounded-3xl border border-white/50 p-8 mb-10">
              <h3 className="text-xl font-bold text-gray-900 mb-6 flex items-center gap-2">
                <span>💡</span> Quick Insights
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Top Category */}
                {topCategory && (
                  <div className="bg-white/80 rounded-2xl p-5 border border-gray-100">
                    <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Top Category</div>
                    <div className="text-lg font-bold text-gray-900">{topCategory.category || 'Uncategorized'}</div>
                    <div className="text-sm text-gray-600 mt-1">
                      ${topCategory.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })} ({topCategory.percentage.toFixed(1)}%)
                    </div>
                  </div>
                )}

                {/* Top Merchant */}
                {topMerchant && (
                  <div className="bg-white/80 rounded-2xl p-5 border border-gray-100">
                    <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Top Merchant</div>
                    <div className="text-lg font-bold text-gray-900 truncate">{topMerchant.merchant}</div>
                    <div className="text-sm text-gray-600 mt-1">
                      ${topMerchant.total.toLocaleString('en-US', { minimumFractionDigits: 2 })} ({topMerchant.count} txns)
                    </div>
                  </div>
                )}

                {/* Savings Rate */}
                <div className="bg-white/80 rounded-2xl p-5 border border-gray-100">
                  <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Savings Rate</div>
                  <div className={`text-lg font-bold ${parseFloat(savingsRate) >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                    {parseFloat(savingsRate) >= 0 ? '+' : ''}{savingsRate}%
                  </div>
                  <div className="text-sm text-gray-600 mt-1">
                    {parseFloat(savingsRate) >= 20 ? 'Great job saving!' : parseFloat(savingsRate) >= 0 ? 'Keep it up!' : 'Spending exceeds income'}
                  </div>
                </div>

                {/* Daily Average */}
                <div className="bg-white/80 rounded-2xl p-5 border border-gray-100">
                  <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Daily Average</div>
                  <div className="text-lg font-bold text-gray-900">
                    ${dailyAvgSpend.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <div className="text-sm text-gray-600 mt-1">
                    Over {daysInRange} days
                  </div>
                </div>
              </div>
            </div>
          );
        })()}

        {/* Empty State */}
        {(!summary?.category_breakdown || summary.category_breakdown.length === 0) && (
          <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-3xl border border-white/50 p-16 text-center">
            <div className="text-6xl mb-6">📊</div>
            <h3 className="text-2xl font-bold text-gray-900 mb-3">No transactions yet</h3>
            <p className="text-gray-600 mb-8 text-lg max-w-md mx-auto">Get started by importing your transaction data to see your spending insights</p>
            <a
              href="/imports"
              className="inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-bold text-lg rounded-2xl hover:from-indigo-700 hover:to-purple-700 transform hover:scale-105 transition-all duration-200 shadow-2xl hover:shadow-indigo-500/50"
            >
              <span>📤</span> Import Transactions
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
