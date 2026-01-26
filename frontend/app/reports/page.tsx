'use client';

import React, { useState, useEffect } from 'react';
import {
  getYoYComparison,
  getYoYMonthlyComparison,
  getSpendingVelocity,
  exportReport,
  getAccounts,
} from '@/lib/api';
import {
  YoYComparisonResponse,
  YoYMonthlyComparisonResponse,
  SpendingVelocityResponse,
  Account,
} from '@/lib/types';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

export default function ReportsPage() {
  // State
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Report data
  const [yoyData, setYoyData] = useState<YoYComparisonResponse | null>(null);
  const [velocityData, setVelocityData] = useState<SpendingVelocityResponse | null>(null);
  const [monthlyComparison, setMonthlyComparison] = useState<YoYMonthlyComparisonResponse | null>(null);

  // Report settings
  const currentYear = new Date().getFullYear();
  const [year1, setYear1] = useState(currentYear - 1);
  const [year2, setYear2] = useState(currentYear);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1);

  // Export settings
  const [exportFormat, setExportFormat] = useState<'csv' | 'excel' | 'pdf'>('csv');
  const [exportStartDate, setExportStartDate] = useState(`${currentYear}-01-01`);
  const [exportEndDate, setExportEndDate] = useState(new Date().toISOString().split('T')[0]);

  // Active tab
  const [activeTab, setActiveTab] = useState<'yoy' | 'velocity' | 'export'>('yoy');

  // Load data on mount
  useEffect(() => {
    loadInitialData();
  }, []);

  // Reload reports when year/account changes
  useEffect(() => {
    if (!loading) {
      loadReports();
    }
  }, [year1, year2, selectedAccount]);

  async function loadInitialData() {
    try {
      setLoading(true);
      setError(null);

      const accountsData = await getAccounts();
      setAccounts(accountsData.accounts || []);

      await loadReports();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  async function loadReports() {
    try {
      setError(null);
      const accountId = selectedAccount || undefined;

      const [yoy, velocity, monthly] = await Promise.all([
        getYoYComparison(year1, year2, accountId),
        getSpendingVelocity(12, accountId),
        getYoYMonthlyComparison(selectedMonth, year1, year2, accountId),
      ]);

      setYoyData(yoy);
      setVelocityData(velocity);
      setMonthlyComparison(monthly);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load reports');
    }
  }

  async function handleMonthChange(month: number) {
    setSelectedMonth(month);
    try {
      const monthly = await getYoYMonthlyComparison(month, year1, year2, selectedAccount || undefined);
      setMonthlyComparison(monthly);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load monthly comparison');
    }
  }

  async function handleExport() {
    try {
      setExporting(true);
      setError(null);
      await exportReport({
        format: exportFormat,
        start_date: exportStartDate,
        end_date: exportEndDate,
        account_id: selectedAccount || undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export report');
    } finally {
      setExporting(false);
    }
  }

  function formatCurrency(amount: number): string {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
  }

  function formatChange(change: number, changePct: number): React.ReactNode {
    const isPositive = change > 0;
    const color = isPositive ? 'text-red-600' : 'text-green-600';
    const arrow = isPositive ? '↑' : '↓';

    return (
      <span className={color}>
        {arrow} {formatCurrency(Math.abs(change))} ({Math.abs(changePct).toFixed(1)}%)
      </span>
    );
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">Reports</h1>
        <div className="flex items-center gap-4">
          <select
            value={selectedAccount}
            onChange={(e) => setSelectedAccount(e.target.value)}
            className="border rounded-lg px-3 py-2"
          >
            <option value="">All Accounts</option>
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('yoy')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'yoy'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Year-over-Year
          </button>
          <button
            onClick={() => setActiveTab('velocity')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'velocity'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Spending Trends
          </button>
          <button
            onClick={() => setActiveTab('export')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'export'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Export
          </button>
        </nav>
      </div>

      {/* Year-over-Year Tab */}
      {activeTab === 'yoy' && yoyData && (
        <div className="space-y-6">
          {/* Year Selection */}
          <div className="flex items-center gap-4 bg-white p-4 rounded-lg border">
            <label className="text-sm font-medium text-gray-700">Compare:</label>
            <select
              value={year1}
              onChange={(e) => setYear1(Number(e.target.value))}
              className="border rounded px-3 py-1.5"
            >
              {Array.from({ length: 10 }, (_, i) => currentYear - i).map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
            <span className="text-gray-500">vs</span>
            <select
              value={year2}
              onChange={(e) => setYear2(Number(e.target.value))}
              className="border rounded px-3 py-1.5"
            >
              {Array.from({ length: 10 }, (_, i) => currentYear - i).map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>

          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white rounded-lg border p-4">
              <div className="text-sm text-gray-500">{year1} Total Spending</div>
              <div className="text-2xl font-bold text-gray-900">{formatCurrency(yoyData.year1_total_spend)}</div>
            </div>
            <div className="bg-white rounded-lg border p-4">
              <div className="text-sm text-gray-500">{year2} Total Spending</div>
              <div className="text-2xl font-bold text-gray-900">{formatCurrency(yoyData.year2_total_spend)}</div>
            </div>
            <div className="bg-white rounded-lg border p-4">
              <div className="text-sm text-gray-500">Change</div>
              <div className="text-2xl font-bold">
                {formatChange(yoyData.spend_change, yoyData.spend_change_pct)}
              </div>
            </div>
          </div>

          {/* Monthly Comparison Table */}
          <div className="bg-white rounded-lg border overflow-hidden">
            <div className="px-6 py-4 border-b">
              <h3 className="font-semibold text-gray-900">Monthly Comparison</h3>
            </div>
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Month</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">{year1}</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">{year2}</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Change</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {yoyData.monthly_comparison.map((m) => (
                  <tr key={m.month} className="hover:bg-gray-50">
                    <td className="px-6 py-3 whitespace-nowrap text-gray-900">{m.month_name}</td>
                    <td className="px-6 py-3 whitespace-nowrap text-right text-gray-600">
                      {formatCurrency(m.year1_spend)}
                    </td>
                    <td className="px-6 py-3 whitespace-nowrap text-right text-gray-600">
                      {formatCurrency(m.year2_spend)}
                    </td>
                    <td className="px-6 py-3 whitespace-nowrap text-right">
                      {m.year1_spend > 0 ? formatChange(m.change, m.change_pct) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Month Detail Section */}
          <div className="bg-white rounded-lg border">
            <div className="px-6 py-4 border-b flex items-center justify-between">
              <h3 className="font-semibold text-gray-900">Category Comparison by Month</h3>
              <select
                value={selectedMonth}
                onChange={(e) => handleMonthChange(Number(e.target.value))}
                className="border rounded px-3 py-1.5"
              >
                {MONTHS.map((name, i) => (
                  <option key={i} value={i + 1}>{name}</option>
                ))}
              </select>
            </div>
            {monthlyComparison && monthlyComparison.category_comparison.length > 0 && (
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Category</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">{year1}</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">{year2}</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Change</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {monthlyComparison.category_comparison.slice(0, 10).map((c) => (
                    <tr key={c.category} className="hover:bg-gray-50">
                      <td className="px-6 py-3 whitespace-nowrap text-gray-900">{c.category}</td>
                      <td className="px-6 py-3 whitespace-nowrap text-right text-gray-600">
                        {formatCurrency(c.year1_amount)}
                      </td>
                      <td className="px-6 py-3 whitespace-nowrap text-right text-gray-600">
                        {formatCurrency(c.year2_amount)}
                      </td>
                      <td className="px-6 py-3 whitespace-nowrap text-right">
                        {c.year1_amount > 0 ? formatChange(c.change, c.change_pct) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Spending Trends Tab */}
      {activeTab === 'velocity' && velocityData && (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-lg border p-4">
              <div className="text-sm text-gray-500">Avg Monthly Spending</div>
              <div className="text-2xl font-bold text-gray-900">
                {formatCurrency(velocityData.avg_monthly_spend)}
              </div>
            </div>
            <div className="bg-white rounded-lg border p-4">
              <div className="text-sm text-gray-500">Avg Monthly Income</div>
              <div className="text-2xl font-bold text-green-600">
                {formatCurrency(velocityData.avg_monthly_income)}
              </div>
            </div>
            <div className="bg-white rounded-lg border p-4">
              <div className="text-sm text-gray-500">Avg Monthly Net</div>
              <div className={`text-2xl font-bold ${velocityData.avg_monthly_net >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {formatCurrency(velocityData.avg_monthly_net)}
              </div>
            </div>
            <div className="bg-white rounded-lg border p-4">
              <div className="text-sm text-gray-500">Trend</div>
              <div className={`text-2xl font-bold ${
                velocityData.trend_direction === 'increasing' ? 'text-red-600' :
                velocityData.trend_direction === 'decreasing' ? 'text-green-600' :
                'text-gray-600'
              }`}>
                {velocityData.trend_direction === 'increasing' ? '↑ Increasing' :
                 velocityData.trend_direction === 'decreasing' ? '↓ Decreasing' :
                 velocityData.trend_direction === 'stable' ? '→ Stable' : 'N/A'}
              </div>
            </div>
          </div>

          {/* Monthly Chart (simple bar representation) */}
          <div className="bg-white rounded-lg border p-6">
            <h3 className="font-semibold text-gray-900 mb-4">Last 12 Months</h3>
            <div className="space-y-3">
              {velocityData.monthly_data.map((m) => {
                const maxSpend = Math.max(...velocityData.monthly_data.map(d => d.total_spend));
                const widthPct = maxSpend > 0 ? (m.total_spend / maxSpend) * 100 : 0;

                return (
                  <div key={`${m.year}-${m.month}`} className="flex items-center gap-4">
                    <div className="w-20 text-sm text-gray-600">{m.month_name}</div>
                    <div className="flex-1 bg-gray-100 rounded-full h-6 relative">
                      <div
                        className="bg-indigo-500 h-6 rounded-full"
                        style={{ width: `${widthPct}%` }}
                      />
                      <span className="absolute right-2 top-0 h-6 flex items-center text-sm text-gray-700">
                        {formatCurrency(m.total_spend)}
                      </span>
                    </div>
                    <div className={`w-24 text-sm text-right ${m.net >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {formatCurrency(m.net)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Export Tab */}
      {activeTab === 'export' && (
        <div className="bg-white rounded-lg border p-6 max-w-lg">
          <h3 className="font-semibold text-gray-900 mb-6">Export Report</h3>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Format</label>
              <select
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value as 'csv' | 'excel' | 'pdf')}
                className="w-full border rounded-lg px-3 py-2"
              >
                <option value="csv">CSV (Simple spreadsheet)</option>
                <option value="excel">Excel (Multi-sheet with details)</option>
                <option value="pdf">PDF (Formatted report)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Start Date</label>
              <input
                type="date"
                value={exportStartDate}
                onChange={(e) => setExportStartDate(e.target.value)}
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">End Date</label>
              <input
                type="date"
                value={exportEndDate}
                onChange={(e) => setExportEndDate(e.target.value)}
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Account</label>
              <select
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                className="w-full border rounded-lg px-3 py-2"
              >
                <option value="">All Accounts</option>
                {accounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {acc.name}
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={handleExport}
              disabled={exporting}
              className="w-full mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {exporting ? (
                <>
                  <span className="animate-spin">&#x21bb;</span>
                  Generating...
                </>
              ) : (
                <>Download Report</>
              )}
            </button>
          </div>

          <div className="mt-6 text-sm text-gray-500">
            <p className="font-medium mb-2">Format Details:</p>
            <ul className="list-disc pl-5 space-y-1">
              <li><strong>CSV:</strong> Simple format with summary and transaction list</li>
              <li><strong>Excel:</strong> Multiple sheets with summary, categories, transactions, and monthly trends</li>
              <li><strong>PDF:</strong> Formatted report with tables and visual styling</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
