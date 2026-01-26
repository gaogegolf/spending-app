'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import {
  getNetWorth,
  getNetWorthByAccount,
  getAssetClassBreakdown,
  getHoldingsSnapshots,
  getSnapshotDetail,
  uploadBrokerageStatement,
  parseBrokerageStatement,
  commitBrokerageImport,
  deleteBrokerageAccount,
  updateAccount,
} from '@/lib/api';
import { HoldingsSnapshot, NetWorthData, NetWorthByAccountData, AssetClassBreakdown, Position, BrokerageParseResult } from '@/lib/types';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

export default function NetWorthPage() {
  const [netWorth, setNetWorth] = useState<NetWorthData | null>(null);
  const [netWorthByAccount, setNetWorthByAccount] = useState<NetWorthByAccountData | null>(null);
  const [assetBreakdown, setAssetBreakdown] = useState<AssetClassBreakdown | null>(null);
  const [snapshots, setSnapshots] = useState<HoldingsSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Chart state
  const [chartTab, setChartTab] = useState<'overview' | 'by-account' | 'by-asset'>('overview');
  const [timeRange, setTimeRange] = useState<'3M' | '6M' | '1Y' | 'ALL'>('ALL');
  const [hiddenAccounts, setHiddenAccounts] = useState<Set<string>>(new Set());

  // Import modal state
  const [showImportModal, setShowImportModal] = useState(false);
  const [importStep, setImportStep] = useState<'upload' | 'preview' | 'success'>('upload');
  const [importing, setImporting] = useState(false);
  const [parseResults, setParseResults] = useState<{ importId: string; result: BrokerageParseResult; filename: string }[]>([]);
  const [importProgress, setImportProgress] = useState<{ current: number; total: number; currentFile: string }>({ current: 0, total: 0, currentFile: '' });
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Snapshot detail modal
  const [selectedSnapshot, setSelectedSnapshot] = useState<HoldingsSnapshot | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Delete confirmation modal
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [accountToDelete, setAccountToDelete] = useState<{ id: string; name: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Expanded accounts in history section
  const [expandedAccounts, setExpandedAccounts] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const [netWorthData, netWorthByAccountData, assetBreakdownData, snapshotsData] = await Promise.all([
        getNetWorth(),
        getNetWorthByAccount(),
        getAssetClassBreakdown(),
        getHoldingsSnapshots(),
      ]);
      setNetWorth(netWorthData);
      setNetWorthByAccount(netWorthByAccountData);
      setAssetBreakdown(assetBreakdownData);
      setSnapshots(snapshotsData.snapshots || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    try {
      setImporting(true);
      setError(null);
      setImportProgress({ current: 0, total: files.length, currentFile: '' });

      const results: { importId: string; result: BrokerageParseResult; filename: string }[] = [];

      // Process each file sequentially
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        setImportProgress({ current: i + 1, total: files.length, currentFile: file.name });

        try {
          // Upload
          const uploadResult = await uploadBrokerageStatement(file);

          // Parse
          const parseData = await parseBrokerageStatement(uploadResult.import_id);

          // Handle multi-account statements (e.g., IBKR with multiple accounts)
          if (parseData.is_multi_account && parseData.accounts) {
            // Add each account as a separate result
            for (const accountResult of parseData.accounts) {
              results.push({
                importId: uploadResult.import_id,
                result: accountResult,
                filename: `${file.name} (${accountResult.account_identifier})`,
              });
            }
          } else {
            results.push({
              importId: uploadResult.import_id,
              result: parseData,
              filename: file.name,
            });
          }
        } catch (fileErr) {
          // Add error result for this file
          results.push({
            importId: '',
            result: {
              import_id: '',
              provider: 'unknown',
              account_type: 'OTHER',
              account_identifier: '',
              statement_date: null,
              total_value: 0,
              total_cash: 0,
              total_securities: 0,
              calculated_total: 0,
              is_reconciled: false,
              reconciliation_diff: 0,
              positions: [],
              warnings: [fileErr instanceof Error ? fileErr.message : 'Failed to parse file'],
            },
            filename: file.name,
          });
        }
      }

      setParseResults(results);
      setImportStep('preview');

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload statements');
    } finally {
      setImporting(false);
    }
  }

  async function handleCommitImport() {
    // Get valid imports (ones that were successfully parsed)
    const validImports = parseResults.filter(r => r.importId && r.result.positions && r.result.positions.length > 0);
    if (validImports.length === 0) return;

    // Deduplicate by importId (multi-account statements share the same importId)
    const uniqueImportIds = [...new Set(validImports.map(r => r.importId))];

    try {
      setImporting(true);
      setImportProgress({ current: 0, total: uniqueImportIds.length, currentFile: '' });

      // Commit each unique import sequentially
      for (let i = 0; i < uniqueImportIds.length; i++) {
        const importId = uniqueImportIds[i];
        const relatedFiles = validImports.filter(r => r.importId === importId);
        const filename = relatedFiles.length > 1
          ? `${relatedFiles.length} accounts`
          : relatedFiles[0]?.filename || 'Unknown';
        setImportProgress({ current: i + 1, total: uniqueImportIds.length, currentFile: filename });
        await commitBrokerageImport(importId, { createAccount: true });
      }

      setImportStep('success');
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to commit import');
    } finally {
      setImporting(false);
    }
  }

  function closeImportModal() {
    setShowImportModal(false);
    setImportStep('upload');
    setParseResults([]);
    setImportProgress({ current: 0, total: 0, currentFile: '' });
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }

  async function viewSnapshotDetail(snapshotId: string) {
    try {
      setLoadingDetail(true);
      const detail = await getSnapshotDetail(snapshotId);
      setSelectedSnapshot(detail);
      setShowDetailModal(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load snapshot');
    } finally {
      setLoadingDetail(false);
    }
  }

  function confirmDeleteAccount(accountId: string, accountName: string, e: React.MouseEvent) {
    e.stopPropagation(); // Prevent triggering the card click
    setAccountToDelete({ id: accountId, name: accountName });
    setShowDeleteModal(true);
  }

  async function handleDeleteAccount(permanent: boolean) {
    if (!accountToDelete) return;

    try {
      setDeleting(true);
      setError(null);
      if (permanent) {
        // Hard delete - remove account and all data
        await deleteBrokerageAccount(accountToDelete.id);
      } else {
        // Soft delete - just deactivate the account
        await updateAccount(accountToDelete.id, { is_active: false });
      }
      setShowDeleteModal(false);
      setAccountToDelete(null);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete account');
    } finally {
      setDeleting(false);
    }
  }

  function formatCurrency(value: number): string {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value);
  }

  function formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  function getAccountTypeIcon(type: string): string {
    switch (type) {
      case 'BROKERAGE': return '💼';
      case 'IRA_ROTH': return '🌟';
      case 'IRA_TRADITIONAL': return '📋';
      case 'RETIREMENT_401K': return '🏛️';
      case 'STOCK_PLAN': return '📊';
      case 'CHECKING': return '🏦';
      case 'SAVINGS': return '💰';
      default: return '📈';
    }
  }

  function getAccountTypeLabel(type: string): string {
    switch (type) {
      case 'BROKERAGE': return 'Brokerage';
      case 'IRA_ROTH': return 'Roth IRA';
      case 'IRA_TRADITIONAL': return 'Traditional IRA';
      case 'RETIREMENT_401K': return '401(k)';
      case 'STOCK_PLAN': return 'Stock Plan';
      case 'CHECKING': return 'Checking';
      case 'SAVINGS': return 'Savings';
      default: return type;
    }
  }

  // Filter data by time range
  function filterByTimeRange<T extends { date: string }>(data: T[]): T[] {
    if (timeRange === 'ALL' || data.length === 0) return data;

    const now = new Date();
    let cutoffDate: Date;

    switch (timeRange) {
      case '3M':
        cutoffDate = new Date(now.getFullYear(), now.getMonth() - 3, now.getDate());
        break;
      case '6M':
        cutoffDate = new Date(now.getFullYear(), now.getMonth() - 6, now.getDate());
        break;
      case '1Y':
        cutoffDate = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
        break;
      default:
        return data;
    }

    return data.filter(item => new Date(item.date) >= cutoffDate);
  }

  // Toggle account visibility
  function toggleAccountVisibility(accountId: string) {
    setHiddenAccounts(prev => {
      const newSet = new Set(prev);
      if (newSet.has(accountId)) {
        newSet.delete(accountId);
      } else {
        newSet.add(accountId);
      }
      return newSet;
    });
  }

  // Chart rendering functions
  function renderOverviewChart(history: { date: string; total: number }[]) {
    if (history.length === 0) return null;

    // If only 1 data point, show a single value display instead of a chart
    if (history.length === 1) {
      return (
        <div className="h-full flex items-center justify-center">
          <div className="text-center">
            <p className="text-3xl font-bold text-emerald-600">{formatCurrency(history[0].total)}</p>
            <p className="text-sm text-gray-500 mt-2">as of {formatDate(history[0].date)}</p>
            <p className="text-xs text-gray-400 mt-4">Import more statements to see trends over time</p>
          </div>
        </div>
      );
    }

    const maxValue = Math.max(...history.map(h => h.total));
    const minValue = Math.min(...history.map(h => h.total));

    // Start y-axis from 0 for accurate visual representation
    // Add 5% padding above max for visual breathing room
    const chartMin = 0;
    const chartMax = maxValue * 1.05;
    const chartRange = chartMax - chartMin;

    // Calculate chart height (200px for bars, rest for labels)
    const chartHeight = 200;

    return (
      <div className="h-full flex flex-col">
        {/* Y-axis labels */}
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>{formatCurrency(maxValue)}</span>
        </div>

        {/* Chart area - fixed height */}
        <div className="flex items-end gap-1" style={{ height: `${chartHeight}px` }}>
          {history.map((point, i) => {
            const heightPercent = ((point.total - chartMin) / chartRange) * 100;
            const barHeight = Math.max((heightPercent / 100) * chartHeight, 4);
            return (
              <div
                key={i}
                className="flex-1 flex flex-col justify-end h-full relative group"
              >
                {/* Tooltip */}
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 text-white text-xs rounded shadow-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                  <div className="font-semibold">{formatCurrency(point.total)}</div>
                  <div className="text-gray-300">{formatDate(point.date)}</div>
                  {/* Arrow */}
                  <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
                </div>
                <div
                  className="bg-gradient-to-t from-emerald-500 to-teal-400 rounded-t mx-0.5 transition-all hover:from-emerald-400 hover:to-teal-300 cursor-pointer"
                  style={{ height: `${barHeight}px` }}
                />
              </div>
            );
          })}
        </div>

        {/* Min value label */}
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          <span>{formatCurrency(0)}</span>
        </div>

        {/* X-axis labels */}
        <div className="flex justify-between text-xs text-gray-500 mt-2">
          {history.length > 0 && <span>{formatDate(history[0].date)}</span>}
          {history.length > 1 && <span>{formatDate(history[history.length - 1].date)}</span>}
        </div>
      </div>
    );
  }

  function renderByAccountChart(data: NetWorthByAccountData) {
    if (!data.history.length) return null;

    const maxTotal = Math.max(...data.history.map(h => h.total));
    const chartHeight = 200;

    // Colors for different accounts (gradient and solid versions)
    const accountColors = [
      { gradient: 'from-emerald-500 to-teal-500', solid: 'bg-emerald-500' },
      { gradient: 'from-blue-500 to-indigo-500', solid: 'bg-blue-500' },
      { gradient: 'from-purple-500 to-pink-500', solid: 'bg-purple-500' },
      { gradient: 'from-orange-500 to-amber-500', solid: 'bg-orange-500' },
      { gradient: 'from-rose-500 to-red-500', solid: 'bg-rose-500' },
    ];

    return (
      <div className="h-full flex flex-col">
        <div className="flex-1 flex items-end gap-2">
          {data.history.map((point, idx) => (
            <div key={idx} className="flex-1 flex flex-col items-center group relative">
              {/* Tooltip */}
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded shadow-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                <div className="font-semibold mb-1">{formatDate(point.date)}</div>
                <div className="font-bold text-emerald-400 mb-2">{formatCurrency(point.total)}</div>
                <div className="space-y-1 border-t border-gray-700 pt-2">
                  {point.accounts.map((acc) => {
                    const colorIdx = data.accounts.findIndex(a => a.account_id === acc.account_id);
                    return (
                      <div key={acc.account_id} className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-1.5">
                          <div className={`w-2 h-2 rounded ${accountColors[colorIdx % accountColors.length].solid}`} />
                          <span className="text-gray-300">{acc.account_name}</span>
                        </div>
                        <span className="font-medium">{formatCurrency(acc.value)}</span>
                      </div>
                    );
                  })}
                </div>
                {/* Arrow */}
                <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
              </div>
              <div className="w-full flex flex-col-reverse cursor-pointer" style={{ height: `${chartHeight}px` }}>
                {point.accounts.map((acc) => {
                  const height = (acc.value / maxTotal) * chartHeight;
                  const colorIdx = data.accounts.findIndex(a => a.account_id === acc.account_id);
                  return (
                    <div
                      key={acc.account_id}
                      className={`w-full bg-gradient-to-t ${accountColors[colorIdx % accountColors.length].gradient} transition-all group-hover:opacity-90`}
                      style={{ height: `${height}px` }}
                    />
                  );
                })}
              </div>
              <span className="text-xs text-gray-500 mt-1 truncate w-full text-center">
                {new Date(point.date).toLocaleDateString('en-US', { month: 'short' })}
              </span>
            </div>
          ))}
        </div>
        {/* Legend */}
        <div className="flex flex-wrap gap-3 mt-4 justify-center">
          {data.accounts.map((acc, idx) => (
            <div key={acc.account_id} className="flex items-center gap-1.5">
              <div className={`w-3 h-3 rounded bg-gradient-to-r ${accountColors[idx % accountColors.length].gradient}`} />
              <span className="text-xs text-gray-600">{acc.account_name}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  function renderAssetClassChart(data: AssetClassBreakdown) {
    const { current, history } = data;
    const chartHeight = 200;

    // Asset class colors
    const assetClassConfig = [
      { key: 'equity', label: 'Equity', color: 'bg-blue-500', gradient: 'from-blue-500 to-blue-600' },
      { key: 'fixed_income', label: 'Fixed Income', color: 'bg-green-500', gradient: 'from-green-500 to-green-600' },
      { key: 'cash', label: 'Cash', color: 'bg-amber-500', gradient: 'from-amber-500 to-amber-600' },
      { key: 'alternative', label: 'Alternative', color: 'bg-purple-500', gradient: 'from-purple-500 to-purple-600' },
      { key: 'unknown', label: 'Other', color: 'bg-gray-400', gradient: 'from-gray-400 to-gray-500' },
    ];

    // Find max total for scaling
    const maxTotal = Math.max(...history.map(h => h.total), current.total) || 1;

    // Get asset classes that have values in any period
    const activeAssetClasses = assetClassConfig.filter(ac =>
      history.some(h => (h as unknown as Record<string, number>)[ac.key] > 0) ||
      (current as unknown as Record<string, number>)[ac.key] > 0
    );

    return (
      <div className="h-full flex flex-col">
        {/* Stacked bar chart for history */}
        <div className="flex-1 flex items-end gap-2">
          {history.map((point, idx) => {
            const pointData = point as Record<string, number | string>;
            return (
              <div key={idx} className="flex-1 flex flex-col items-center group relative">
                {/* Tooltip */}
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded shadow-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                  <div className="font-semibold mb-1">{formatDate(point.date)}</div>
                  <div className="font-bold text-emerald-400 mb-2">{formatCurrency(point.total)}</div>
                  <div className="space-y-1 border-t border-gray-700 pt-2">
                    {activeAssetClasses.map((ac) => {
                      const value = pointData[ac.key] as number;
                      if (value <= 0) return null;
                      return (
                        <div key={ac.key} className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-1.5">
                            <div className={`w-2 h-2 rounded ${ac.color}`} />
                            <span className="text-gray-300">{ac.label}</span>
                          </div>
                          <span className="font-medium">{formatCurrency(value)}</span>
                        </div>
                      );
                    })}
                  </div>
                  {/* Arrow */}
                  <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
                </div>
                <div className="w-full flex flex-col-reverse cursor-pointer" style={{ height: `${chartHeight}px` }}>
                  {activeAssetClasses.map((ac) => {
                    const value = pointData[ac.key] as number;
                    const height = (value / maxTotal) * chartHeight;
                    return (
                      <div
                        key={ac.key}
                        className={`w-full bg-gradient-to-t ${ac.gradient} transition-all group-hover:opacity-90`}
                        style={{ height: `${height}px` }}
                      />
                    );
                  })}
                </div>
                <span className="text-xs text-gray-500 mt-1 truncate w-full text-center">
                  {new Date(point.date).toLocaleDateString('en-US', { month: 'short' })}
                </span>
              </div>
            );
          })}
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-4 mt-4 justify-center">
          {activeAssetClasses.map((ac) => (
            <div key={ac.key} className="flex items-center gap-1.5">
              <div className={`w-3 h-3 rounded ${ac.color}`} />
              <span className="text-xs text-gray-600">{ac.label}</span>
              <span className="text-xs font-semibold text-gray-900">
                {formatCurrency((current as Record<string, number>)[ac.key])}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg">
              <span className="text-2xl">💎</span>
            </div>
            <div>
              <h1 className="text-4xl font-black bg-gradient-to-r from-gray-900 via-emerald-900 to-teal-900 bg-clip-text text-transparent">
                Net Worth
              </h1>
              <p className="text-gray-600 mt-1">Track your total net worth across all accounts</p>
            </div>
          </div>
          <button
            onClick={() => setShowImportModal(true)}
            className="px-5 py-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-xl hover:from-emerald-700 hover:to-teal-700 transition-all font-semibold text-sm flex items-center gap-2 shadow-lg"
          >
            <span>+</span>
            Import Statement
          </button>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-6 bg-red-50 border-l-4 border-red-500 rounded-lg p-4 shadow-sm">
            <div className="flex items-start">
              <span className="text-red-500 text-xl mr-3">!</span>
              <p className="text-red-800">{error}</p>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="bg-white/70 backdrop-blur-xl shadow-xl rounded-2xl border border-white/50 p-12">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-emerald-200 border-t-emerald-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading investments...</p>
            </div>
          </div>
        )}

        {/* Net Worth Summary */}
        {!loading && netWorth && (() => {
          // Group accounts by category
          const cashTypes = ['CHECKING', 'SAVINGS'];
          const cashAccounts = netWorth.accounts.filter(a => cashTypes.includes(a.account_type));
          const investmentAccounts = netWorth.accounts.filter(a => !cashTypes.includes(a.account_type));
          const cashTotal = cashAccounts.reduce((sum, a) => sum + a.latest_value, 0);
          const investmentTotal = investmentAccounts.reduce((sum, a) => sum + a.latest_value, 0);
          const total = netWorth.current_total || 1;
          const cashPercent = (cashTotal / total) * 100;
          const investmentPercent = (investmentTotal / total) * 100;

          return (
          <div className="mb-8 space-y-4">
            {/* Total Net Worth Card */}
            <div className="bg-gradient-to-r from-emerald-600 to-teal-600 rounded-2xl shadow-xl p-6 text-white">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-emerald-100 text-sm font-medium uppercase tracking-wide">Total Net Worth</p>
                  <p className="text-4xl font-black mt-1">{formatCurrency(netWorth.current_total)}</p>
                </div>
                <div className="text-6xl opacity-20">💎</div>
              </div>

              {/* Allocation Bar */}
              {netWorth.accounts.length > 0 && (
                <div className="mt-6">
                  <div className="flex h-3 rounded-full overflow-hidden bg-white/20">
                    {investmentPercent > 0 && (
                      <div
                        className="bg-white/90 transition-all"
                        style={{ width: `${investmentPercent}%` }}
                        title={`Investments: ${formatCurrency(investmentTotal)}`}
                      />
                    )}
                    {cashPercent > 0 && (
                      <div
                        className="bg-amber-300 transition-all"
                        style={{ width: `${cashPercent}%` }}
                        title={`Cash: ${formatCurrency(cashTotal)}`}
                      />
                    )}
                  </div>
                  <div className="flex justify-between mt-2 text-xs">
                    <div className="flex items-center gap-4">
                      {investmentPercent > 0 && (
                        <div className="flex items-center gap-1.5">
                          <div className="w-2.5 h-2.5 rounded-full bg-white/90" />
                          <span>Investments {investmentPercent.toFixed(0)}%</span>
                        </div>
                      )}
                      {cashPercent > 0 && (
                        <div className="flex items-center gap-1.5">
                          <div className="w-2.5 h-2.5 rounded-full bg-amber-300" />
                          <span>Cash {cashPercent.toFixed(0)}%</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Category Cards Side by Side */}
            {netWorth.accounts.length > 0 && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Investments Card */}
                {investmentAccounts.length > 0 && (
                  <div className="bg-white/70 backdrop-blur-xl rounded-2xl shadow-lg border border-white/50 overflow-hidden">
                    <div className="bg-gradient-to-r from-emerald-500 to-teal-500 px-5 py-3 flex items-center justify-between">
                      <div className="flex items-center gap-2 text-white">
                        <span className="text-xl">📈</span>
                        <h3 className="font-bold">Investments</h3>
                      </div>
                      <span className="text-white font-bold text-lg">{formatCurrency(investmentTotal)}</span>
                    </div>
                    <div className="divide-y divide-gray-100">
                      {investmentAccounts.map((account) => (
                        <div
                          key={account.account_id}
                          className="px-5 py-3 flex items-center justify-between hover:bg-gray-50/50 transition-colors group"
                        >
                          <div className="flex items-center gap-3">
                            <span className="text-xl">{getAccountTypeIcon(account.account_type)}</span>
                            <div>
                              <p className="font-medium text-gray-900">{account.account_name}</p>
                              <p className="text-xs text-gray-500">{getAccountTypeLabel(account.account_type)} · {formatDate(account.statement_date)}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-gray-900">{formatCurrency(account.latest_value)}</span>
                            <button
                              onClick={(e) => confirmDeleteAccount(account.account_id, account.account_name, e)}
                              className="p-1.5 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all"
                              title="Delete account"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Cash Card */}
                {cashAccounts.length > 0 && (
                  <div className="bg-white/70 backdrop-blur-xl rounded-2xl shadow-lg border border-white/50 overflow-hidden">
                    <div className="bg-gradient-to-r from-amber-500 to-yellow-500 px-5 py-3 flex items-center justify-between">
                      <div className="flex items-center gap-2 text-white">
                        <span className="text-xl">💵</span>
                        <h3 className="font-bold">Cash</h3>
                      </div>
                      <span className="text-white font-bold text-lg">{formatCurrency(cashTotal)}</span>
                    </div>
                    <div className="divide-y divide-gray-100">
                      {cashAccounts.map((account) => (
                        <div
                          key={account.account_id}
                          className="px-5 py-3 flex items-center justify-between hover:bg-gray-50/50 transition-colors group"
                        >
                          <div className="flex items-center gap-3">
                            <span className="text-xl">{getAccountTypeIcon(account.account_type)}</span>
                            <div>
                              <p className="font-medium text-gray-900">{account.account_name}</p>
                              <p className="text-xs text-gray-500">{getAccountTypeLabel(account.account_type)} · {formatDate(account.statement_date)}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-gray-900">{formatCurrency(account.latest_value)}</span>
                            <button
                              onClick={(e) => confirmDeleteAccount(account.account_id, account.account_name, e)}
                              className="p-1.5 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all"
                              title="Delete account"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
          );
        })()}

        {/* Net Worth Charts */}
        {!loading && netWorth && netWorth.history.length > 0 && (
          <div className="mb-8">
            <div className="bg-white/70 backdrop-blur-xl rounded-2xl shadow-xl border border-white/50 p-6">
              {/* Chart Header with Tabs and Time Range */}
              <div className="flex flex-col gap-4 mb-6">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <h2 className="text-xl font-bold text-gray-900">Net Worth Trend</h2>
                  <div className="flex rounded-xl bg-gray-100 p-1">
                    <button
                      onClick={() => setChartTab('overview')}
                      className={`px-4 py-2 text-sm font-semibold rounded-lg transition-all ${
                        chartTab === 'overview'
                          ? 'bg-white text-emerald-600 shadow-md'
                          : 'text-gray-600 hover:text-gray-900'
                      }`}
                    >
                      Overview
                    </button>
                    <button
                      onClick={() => setChartTab('by-account')}
                      className={`px-4 py-2 text-sm font-semibold rounded-lg transition-all ${
                        chartTab === 'by-account'
                          ? 'bg-white text-blue-600 shadow-md'
                          : 'text-gray-600 hover:text-gray-900'
                      }`}
                    >
                      By Account
                    </button>
                    <button
                      onClick={() => setChartTab('by-asset')}
                      className={`px-4 py-2 text-sm font-semibold rounded-lg transition-all ${
                        chartTab === 'by-asset'
                          ? 'bg-white text-purple-600 shadow-md'
                          : 'text-gray-600 hover:text-gray-900'
                      }`}
                    >
                      By Asset Class
                    </button>
                  </div>
                </div>

                {/* Time Range Selector and Account Filters */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-2 border-t border-gray-100">
                  {/* Time Range */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 font-medium">Period:</span>
                    <div className="flex rounded-lg bg-gray-100 p-0.5">
                      {(['3M', '6M', '1Y', 'ALL'] as const).map((range) => (
                        <button
                          key={range}
                          onClick={() => setTimeRange(range)}
                          className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                            timeRange === range
                              ? 'bg-white text-gray-900 shadow-sm'
                              : 'text-gray-500 hover:text-gray-700'
                          }`}
                        >
                          {range}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Account Filters - Only show for By Account tab */}
                  {chartTab === 'by-account' && netWorthByAccount && netWorthByAccount.accounts.length > 1 && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs text-gray-500 font-medium">Show:</span>
                      {netWorthByAccount.accounts.map((acc) => (
                        <button
                          key={acc.account_id}
                          onClick={() => toggleAccountVisibility(acc.account_id)}
                          className={`px-2 py-1 text-xs font-medium rounded-md border transition-all ${
                            hiddenAccounts.has(acc.account_id)
                              ? 'bg-gray-100 text-gray-400 border-gray-200'
                              : 'bg-white text-gray-700 border-gray-300 shadow-sm'
                          }`}
                        >
                          {hiddenAccounts.has(acc.account_id) ? '○' : '●'} {acc.account_name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Overview Chart - Bar chart showing total net worth */}
              {chartTab === 'overview' && netWorth.history.length > 0 && (
                <div className="h-64">
                  {renderOverviewChart(filterByTimeRange(netWorth.history))}
                </div>
              )}

              {/* By Account Chart - Stacked bar showing each account */}
              {chartTab === 'by-account' && netWorthByAccount && netWorthByAccount.history.length > 0 && (
                <div className="h-64">
                  {renderByAccountChart({
                    ...netWorthByAccount,
                    history: filterByTimeRange(netWorthByAccount.history).map(point => ({
                      ...point,
                      accounts: point.accounts.filter(acc => !hiddenAccounts.has(acc.account_id)),
                      total: point.accounts
                        .filter(acc => !hiddenAccounts.has(acc.account_id))
                        .reduce((sum, acc) => sum + acc.value, 0),
                    })),
                    accounts: netWorthByAccount.accounts.filter(acc => !hiddenAccounts.has(acc.account_id)),
                  })}
                </div>
              )}

              {/* By Asset Class - Stacked bar chart */}
              {chartTab === 'by-asset' && assetBreakdown && (
                <div className="h-64">
                  {renderAssetClassChart({
                    ...assetBreakdown,
                    history: filterByTimeRange(assetBreakdown.history),
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Empty State */}
        {!loading && snapshots.length === 0 && (
          <div className="bg-white/70 backdrop-blur-xl shadow-xl rounded-2xl border border-white/50 p-12 text-center">
            <div className="text-6xl mb-4">📊</div>
            <h3 className="text-xl font-semibold text-gray-900 mb-2">No investment data yet</h3>
            <p className="text-gray-600 mb-6 max-w-md mx-auto">
              Import your first brokerage statement to start tracking your investments and net worth.
            </p>
            <button
              onClick={() => setShowImportModal(true)}
              className="px-6 py-3 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-xl hover:from-emerald-700 hover:to-teal-700 transition-all font-semibold shadow-lg"
            >
              Import Statement
            </button>
          </div>
        )}

        {/* Snapshots List - Grouped by Category then Account */}
        {!loading && snapshots.length > 0 && (() => {
          // Group snapshots by account
          const snapshotsByAccount = snapshots.reduce((acc, snapshot) => {
            if (!acc[snapshot.account_id]) {
              acc[snapshot.account_id] = {
                account_id: snapshot.account_id,
                account_name: snapshot.account_name,
                account_type: snapshot.account_type,
                snapshots: [],
              };
            }
            acc[snapshot.account_id].snapshots.push(snapshot);
            return acc;
          }, {} as Record<string, { account_id: string; account_name: string; account_type: string; snapshots: typeof snapshots }>);

          // Sort snapshots within each account by date (newest first)
          Object.values(snapshotsByAccount).forEach(account => {
            account.snapshots.sort((a, b) =>
              new Date(b.statement_date).getTime() - new Date(a.statement_date).getTime()
            );
          });

          const accountGroups = Object.values(snapshotsByAccount);

          // Separate by category
          const cashTypes = ['CHECKING', 'SAVINGS'];
          const investmentGroups = accountGroups.filter(g => !cashTypes.includes(g.account_type));
          const cashGroups = accountGroups.filter(g => cashTypes.includes(g.account_type));

          const investmentStatements = investmentGroups.reduce((sum, g) => sum + g.snapshots.length, 0);
          const cashStatements = cashGroups.reduce((sum, g) => sum + g.snapshots.length, 0);

          const toggleAccount = (accountId: string) => {
            setExpandedAccounts(prev => {
              const newSet = new Set(prev);
              if (newSet.has(accountId)) {
                newSet.delete(accountId);
              } else {
                newSet.add(accountId);
              }
              return newSet;
            });
          };

          const renderAccountGroup = (accountGroup: typeof accountGroups[0], accentColor: string) => {
            const isExpanded = expandedAccounts.has(accountGroup.account_id);
            const latestSnapshot = accountGroup.snapshots[0];
            const dotColor = accentColor === 'emerald' ? 'bg-emerald-500' : 'bg-amber-500';
            const hoverBg = accentColor === 'emerald' ? 'hover:bg-emerald-50/50' : 'hover:bg-amber-50/50';

            return (
              <div key={accountGroup.account_id}>
                <button
                  onClick={() => toggleAccount(accountGroup.account_id)}
                  className={`w-full flex items-center justify-between p-3 rounded-lg transition-colors ${hoverBg}`}
                >
                  <div className="flex items-center gap-3">
                    <svg
                      className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                    <span className="text-xl">{getAccountTypeIcon(accountGroup.account_type)}</span>
                    <div className="text-left">
                      <p className="font-medium text-gray-900">{accountGroup.account_name}</p>
                      <p className="text-xs text-gray-500">
                        {accountGroup.snapshots.length} {accountGroup.snapshots.length === 1 ? 'statement' : 'statements'}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-bold text-gray-900">{formatCurrency(latestSnapshot.total_value)}</p>
                    <p className="text-xs text-gray-500">{formatDate(latestSnapshot.statement_date)}</p>
                  </div>
                </button>

                {isExpanded && (
                  <div className="ml-10 mr-3 mb-2 space-y-1">
                    {accountGroup.snapshots.map((snapshot) => (
                      <div
                        key={snapshot.id}
                        className="flex items-center justify-between p-2.5 bg-gray-50/80 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
                        onClick={() => viewSnapshotDetail(snapshot.id)}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`w-1.5 h-1.5 rounded-full ${dotColor}`}></div>
                          <div>
                            <p className="text-sm font-medium text-gray-900">{formatDate(snapshot.statement_date)}</p>
                            <p className="text-xs text-gray-500">
                              {snapshot.position_count > 0 ? `${snapshot.position_count} positions` : 'Balance snapshot'}
                            </p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-bold text-gray-900">{formatCurrency(snapshot.total_value)}</p>
                          {snapshot.is_reconciled ? (
                            <span className="text-xs text-emerald-600">Reconciled</span>
                          ) : (
                            <span className="text-xs text-amber-600">Review</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          };

          return (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-gray-900">Statement History</h2>
                <p className="text-sm text-gray-500">{snapshots.length} statements across {accountGroups.length} accounts</p>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Investment Statements */}
                {investmentGroups.length > 0 && (
                  <div className="bg-white/70 backdrop-blur-xl rounded-2xl shadow-lg border border-white/50 overflow-hidden">
                    <div className="bg-gradient-to-r from-emerald-500 to-teal-500 px-5 py-3 flex items-center justify-between">
                      <div className="flex items-center gap-2 text-white">
                        <span className="text-xl">📈</span>
                        <h3 className="font-bold">Investment Statements</h3>
                      </div>
                      <span className="text-white/80 text-sm">{investmentStatements} total</span>
                    </div>
                    <div className="p-2 divide-y divide-gray-100">
                      {investmentGroups.map(group => renderAccountGroup(group, 'emerald'))}
                    </div>
                  </div>
                )}

                {/* Cash Statements */}
                {cashGroups.length > 0 && (
                  <div className="bg-white/70 backdrop-blur-xl rounded-2xl shadow-lg border border-white/50 overflow-hidden">
                    <div className="bg-gradient-to-r from-amber-500 to-yellow-500 px-5 py-3 flex items-center justify-between">
                      <div className="flex items-center gap-2 text-white">
                        <span className="text-xl">💵</span>
                        <h3 className="font-bold">Bank Statements</h3>
                      </div>
                      <span className="text-white/80 text-sm">{cashStatements} total</span>
                    </div>
                    <div className="p-2 divide-y divide-gray-100">
                      {cashGroups.map(group => renderAccountGroup(group, 'amber'))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })()}

        {/* Import Modal */}
        {showImportModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between p-6 border-b">
                <h2 className="text-xl font-bold text-gray-900">
                  {importStep === 'upload' && 'Import Brokerage Statements'}
                  {importStep === 'preview' && `Review ${parseResults.length} ${parseResults.length === 1 ? 'Statement' : 'Statements'}`}
                  {importStep === 'success' && 'Import Complete'}
                </h2>
                <button
                  onClick={closeImportModal}
                  className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
                >
                  &times;
                </button>
              </div>

              <div className="p-6">
                {/* Upload Step */}
                {importStep === 'upload' && (
                  <div className="text-center">
                    <div className="text-6xl mb-4">📄</div>
                    <p className="text-gray-600 mb-6">
                      Upload PDF statements from Fidelity, Schwab, or Interactive Brokers. You can select multiple files.
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf"
                      multiple
                      onChange={handleFileUpload}
                      className="hidden"
                      id="statement-upload"
                    />
                    <label
                      htmlFor="statement-upload"
                      className={`inline-block px-6 py-3 rounded-xl font-semibold cursor-pointer transition-all ${
                        importing
                          ? 'bg-gray-200 text-gray-500'
                          : 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white hover:from-emerald-700 hover:to-teal-700 shadow-lg'
                      }`}
                    >
                      {importing
                        ? `Processing ${importProgress.current}/${importProgress.total}: ${importProgress.currentFile}`
                        : 'Select PDF Files'}
                    </label>
                  </div>
                )}

                {/* Preview Step */}
                {importStep === 'preview' && parseResults.length > 0 && (
                  <div>
                    {/* Summary */}
                    {(() => {
                      // Calculate meaningful summary stats
                      const validResults = parseResults.filter(r => r.importId && r.result.positions && r.result.positions.length > 0);

                      // Group by account identifier to get unique accounts
                      const accountMap = new Map<string, { latest: typeof validResults[0], count: number }>();
                      for (const r of validResults) {
                        const key = r.result.account_identifier || r.filename;
                        const existing = accountMap.get(key);
                        if (!existing) {
                          accountMap.set(key, { latest: r, count: 1 });
                        } else {
                          existing.count++;
                          // Keep the one with the latest statement date
                          if (r.result.statement_date && (!existing.latest.result.statement_date || r.result.statement_date > existing.latest.result.statement_date)) {
                            existing.latest = r;
                          }
                        }
                      }

                      const uniqueAccounts = accountMap.size;
                      // Latest value = sum of latest statement per account (point-in-time net worth)
                      const latestValue = Array.from(accountMap.values()).reduce((sum, acc) => sum + acc.latest.result.total_value, 0);

                      // Date range
                      const dates = validResults
                        .map(r => r.result.statement_date)
                        .filter((d): d is string => d !== null)
                        .sort();
                      const dateRange = dates.length > 1
                        ? `${formatDate(dates[0])} - ${formatDate(dates[dates.length - 1])}`
                        : dates.length === 1 ? formatDate(dates[0]) : '';

                      return (
                        <div className="bg-gray-50 rounded-lg p-4 mb-6">
                          <div className="flex items-center justify-between">
                            <div>
                              <p className="font-semibold text-gray-800">
                                {parseResults.length} {parseResults.length === 1 ? 'Statement' : 'Statements'} Parsed
                              </p>
                              <p className="text-sm text-gray-600">
                                {uniqueAccounts} {uniqueAccounts === 1 ? 'account' : 'accounts'} • {validResults.length} ready to import
                              </p>
                              {dateRange && (
                                <p className="text-xs text-gray-500 mt-1">{dateRange}</p>
                              )}
                            </div>
                            <div className="text-right">
                              <p className="text-2xl font-bold text-emerald-800">
                                {formatCurrency(latestValue)}
                              </p>
                              <span className="text-xs text-gray-500">Latest Net Worth</span>
                            </div>
                          </div>
                        </div>
                      );
                    })()}

                    {/* Statements List */}
                    <div className="space-y-4 mb-6 max-h-[400px] overflow-y-auto">
                      {parseResults.map((item, idx) => {
                        const { result, filename } = item;
                        const hasError = !item.importId || !result.positions || result.positions.length === 0;

                        return (
                          <div
                            key={idx}
                            className={`rounded-lg p-4 ${hasError ? 'bg-red-50 border border-red-200' : 'bg-emerald-50 border border-emerald-200'}`}
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex-1 min-w-0">
                                <p className={`font-semibold truncate ${hasError ? 'text-red-800' : 'text-emerald-800'}`}>
                                  {filename}
                                </p>
                                {!hasError && (
                                  <p className="text-sm text-emerald-600">
                                    {result.provider.charAt(0).toUpperCase() + result.provider.slice(1)} • {getAccountTypeLabel(result.account_type)} • {result.statement_date ? formatDate(result.statement_date) : 'Unknown date'}
                                  </p>
                                )}
                                {!hasError && result.fx_rates && Object.keys(result.fx_rates).length > 1 && (
                                  <p className="text-xs text-emerald-500 mt-0.5">
                                    FX: {Object.entries(result.fx_rates)
                                      .filter(([k]) => k !== 'USD')
                                      .map(([currency, rate]) => `${currency}=${rate.toFixed(4)}`)
                                      .join(', ')}
                                  </p>
                                )}
                                {hasError && result.warnings && result.warnings.length > 0 && (
                                  <p className="text-sm text-red-600">{result.warnings[0]}</p>
                                )}
                              </div>
                              <div className="text-right ml-4">
                                {!hasError ? (
                                  <>
                                    <p className="text-xl font-bold text-emerald-800">
                                      {formatCurrency(result.total_value)}
                                    </p>
                                    <p className="text-xs text-emerald-600">
                                      {result.positions?.length || 0} positions
                                      {result.is_reconciled ? ' · Reconciled' : ''}
                                    </p>
                                  </>
                                ) : (
                                  <span className="text-sm text-red-600 font-medium">Failed</span>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    <div className="flex gap-3">
                      <button
                        onClick={closeImportModal}
                        className="flex-1 py-2 px-4 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleCommitImport}
                        disabled={importing || parseResults.filter(r => r.importId && r.result.positions && r.result.positions.length > 0).length === 0}
                        className="flex-1 py-2 px-4 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-lg hover:from-emerald-700 hover:to-teal-700 disabled:bg-gray-400 disabled:from-gray-400 disabled:to-gray-400"
                      >
                        {importing
                          ? `Importing ${importProgress.current}/${importProgress.total}...`
                          : `Import ${parseResults.filter(r => r.importId && r.result.positions && r.result.positions.length > 0).length} ${parseResults.filter(r => r.importId && r.result.positions && r.result.positions.length > 0).length === 1 ? 'Statement' : 'Statements'}`}
                      </button>
                    </div>
                  </div>
                )}

                {/* Success Step */}
                {importStep === 'success' && (
                  <div className="text-center">
                    <div className="text-6xl mb-4">✅</div>
                    <h3 className="text-xl font-semibold text-gray-900 mb-2">Import Successful!</h3>
                    <p className="text-gray-600 mb-6">
                      Your holdings have been imported and your net worth has been updated.
                    </p>
                    <button
                      onClick={closeImportModal}
                      className="px-6 py-3 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-xl hover:from-emerald-700 hover:to-teal-700 font-semibold"
                    >
                      Done
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Snapshot Detail Modal */}
        {showDetailModal && selectedSnapshot && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl mx-4 max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between p-6 border-b">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">{selectedSnapshot.account_name}</h2>
                  <p className="text-sm text-gray-500">{formatDate(selectedSnapshot.statement_date)}</p>
                </div>
                <button
                  onClick={() => setShowDetailModal(false)}
                  className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
                >
                  &times;
                </button>
              </div>

              <div className="p-6">
                {/* Summary */}
                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="bg-emerald-50 rounded-lg p-4 text-center">
                    <p className="text-sm text-emerald-600 mb-1">Total Value</p>
                    <p className="text-2xl font-bold text-emerald-800">{formatCurrency(selectedSnapshot.total_value)}</p>
                  </div>
                  <div className="bg-blue-50 rounded-lg p-4 text-center">
                    <p className="text-sm text-blue-600 mb-1">Securities</p>
                    <p className="text-2xl font-bold text-blue-800">{formatCurrency(selectedSnapshot.total_securities)}</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4 text-center">
                    <p className="text-sm text-gray-600 mb-1">Cash</p>
                    <p className="text-2xl font-bold text-gray-800">{formatCurrency(selectedSnapshot.total_cash)}</p>
                  </div>
                </div>

                {/* Positions Table */}
                {selectedSnapshot.positions && selectedSnapshot.positions.length > 0 && (
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="text-left px-4 py-3 font-semibold text-gray-700">Symbol</th>
                          <th className="text-left px-4 py-3 font-semibold text-gray-700">Security</th>
                          <th className="text-right px-4 py-3 font-semibold text-gray-700">Shares</th>
                          <th className="text-right px-4 py-3 font-semibold text-gray-700">Price</th>
                          <th className="text-right px-4 py-3 font-semibold text-gray-700">Value</th>
                          <th className="text-right px-4 py-3 font-semibold text-gray-700">Cost Basis</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {selectedSnapshot.positions.map((pos, i) => (
                          <tr key={i} className="hover:bg-gray-50">
                            <td className="px-4 py-3 font-mono font-semibold text-gray-900">{pos.symbol || '-'}</td>
                            <td className="px-4 py-3 text-gray-600">
                              {pos.security_name}
                              {pos.currency && pos.currency !== 'USD' && (
                                <span className="ml-1 text-xs text-blue-600 font-medium">({pos.currency})</span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-right text-gray-900">
                              {pos.quantity?.toLocaleString(undefined, { maximumFractionDigits: 4 }) || '-'}
                            </td>
                            <td className="px-4 py-3 text-right text-gray-600">
                              {pos.price ? formatCurrency(pos.price) : '-'}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <span className="font-semibold text-gray-900">
                                {pos.market_value_usd ? formatCurrency(pos.market_value_usd) : formatCurrency(pos.market_value)}
                              </span>
                              {pos.currency && pos.currency !== 'USD' && pos.fx_rate_used && (
                                <span className="block text-xs text-gray-500">
                                  @{pos.fx_rate_used.toFixed(4)}
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-right text-gray-600">
                              {pos.cost_basis ? formatCurrency(pos.cost_basis) : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {showDeleteModal && accountToDelete && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
              <div className="text-center mb-6">
                <div className="text-5xl mb-4">⚠️</div>
                <h3 className="text-xl font-bold text-gray-900 mb-2">Remove Account</h3>
                <p className="text-gray-600">
                  What would you like to do with <strong>{accountToDelete.name}</strong>?
                </p>
              </div>

              <div className="space-y-3 mb-6">
                {/* Deactivate Option */}
                <button
                  onClick={() => handleDeleteAccount(false)}
                  disabled={deleting}
                  className="w-full py-3 px-4 border-2 border-amber-200 rounded-lg text-left hover:bg-amber-50 disabled:opacity-50 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <span className="text-2xl">😴</span>
                    <div>
                      <p className="font-semibold text-gray-900">Deactivate</p>
                      <p className="text-sm text-gray-500">Hide account but keep all holdings data</p>
                    </div>
                  </div>
                </button>

                {/* Delete Permanently Option */}
                <button
                  onClick={() => handleDeleteAccount(true)}
                  disabled={deleting}
                  className="w-full py-3 px-4 border-2 border-red-200 rounded-lg text-left hover:bg-red-50 disabled:opacity-50 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <span className="text-2xl">🗑️</span>
                    <div>
                      <p className="font-semibold text-red-600">Delete Permanently</p>
                      <p className="text-sm text-gray-500">Remove account and all snapshots forever</p>
                    </div>
                  </div>
                </button>
              </div>

              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  setAccountToDelete(null);
                }}
                disabled={deleting}
                className="w-full py-2 px-4 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
              >
                {deleting ? 'Processing...' : 'Cancel'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
