'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import {
  getNetWorth,
  getHoldingsSnapshots,
  getSnapshotDetail,
  uploadBrokerageStatement,
  parseBrokerageStatement,
  commitBrokerageImport,
  deleteBrokerageAccount,
  updateAccount,
} from '@/lib/api';
import { HoldingsSnapshot, NetWorthData, Position, BrokerageParseResult } from '@/lib/types';

export default function InvestmentsPage() {
  const [netWorth, setNetWorth] = useState<NetWorthData | null>(null);
  const [snapshots, setSnapshots] = useState<HoldingsSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Import modal state
  const [showImportModal, setShowImportModal] = useState(false);
  const [importStep, setImportStep] = useState<'upload' | 'preview' | 'success'>('upload');
  const [importing, setImporting] = useState(false);
  const [parseResult, setParsResult] = useState<BrokerageParseResult | null>(null);
  const [importId, setImportId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Snapshot detail modal
  const [selectedSnapshot, setSelectedSnapshot] = useState<HoldingsSnapshot | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Delete confirmation modal
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [accountToDelete, setAccountToDelete] = useState<{ id: string; name: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const [netWorthData, snapshotsData] = await Promise.all([
        getNetWorth(),
        getHoldingsSnapshots(),
      ]);
      setNetWorth(netWorthData);
      setSnapshots(snapshotsData.snapshots || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setImporting(true);
      setError(null);

      // Upload
      const uploadResult = await uploadBrokerageStatement(file);
      setImportId(uploadResult.import_id);

      // Parse
      const parseData = await parseBrokerageStatement(uploadResult.import_id);
      setParsResult(parseData);
      setImportStep('preview');

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload statement');
    } finally {
      setImporting(false);
    }
  }

  async function handleCommitImport() {
    if (!importId) return;

    try {
      setImporting(true);
      await commitBrokerageImport(importId, { createAccount: true });
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
    setParsResult(null);
    setImportId(null);
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
      default: return type;
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg">
              <span className="text-2xl">📈</span>
            </div>
            <div>
              <h1 className="text-4xl font-black bg-gradient-to-r from-gray-900 via-emerald-900 to-teal-900 bg-clip-text text-transparent">
                Investments
              </h1>
              <p className="text-gray-600 mt-1">Track your brokerage holdings and net worth</p>
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
        {!loading && netWorth && (
          <div className="mb-8">
            <div className="bg-white/70 backdrop-blur-xl rounded-2xl shadow-xl border border-white/50 p-8">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-gray-900">Net Worth</h2>
                <span className="text-4xl font-black text-emerald-600">
                  {formatCurrency(netWorth.current_total)}
                </span>
              </div>

              {/* Accounts breakdown */}
              {netWorth.accounts.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {netWorth.accounts.map((account) => (
                    <div
                      key={account.account_id}
                      className="bg-gradient-to-br from-gray-50 to-white p-4 rounded-xl border border-gray-100 group relative"
                    >
                      {/* Delete button */}
                      <button
                        onClick={(e) => confirmDeleteAccount(account.account_id, account.account_name, e)}
                        className="absolute top-2 right-2 p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all"
                        title="Delete account"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                      <div className="flex items-center gap-3 mb-2">
                        <span className="text-2xl">{getAccountTypeIcon(account.account_type)}</span>
                        <div>
                          <p className="font-semibold text-gray-900">{account.account_name}</p>
                          <p className="text-xs text-gray-500">{getAccountTypeLabel(account.account_type)}</p>
                        </div>
                      </div>
                      <p className="text-xl font-bold text-gray-900">{formatCurrency(account.latest_value)}</p>
                      <p className="text-xs text-gray-500 mt-1">as of {formatDate(account.statement_date)}</p>
                    </div>
                  ))}
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

        {/* Snapshots List */}
        {!loading && snapshots.length > 0 && (
          <div className="bg-white/70 backdrop-blur-xl rounded-2xl shadow-xl border border-white/50 overflow-hidden">
            <div className="px-6 py-4 bg-gradient-to-r from-gray-50/80 to-white/80 border-b border-gray-100">
              <h2 className="text-lg font-bold text-gray-900">Holdings History</h2>
            </div>
            <div className="divide-y divide-gray-100">
              {snapshots.map((snapshot) => (
                <div
                  key={snapshot.id}
                  className="p-6 hover:bg-gray-50/50 transition-colors cursor-pointer"
                  onClick={() => viewSnapshotDetail(snapshot.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <span className="text-2xl">{getAccountTypeIcon(snapshot.account_type)}</span>
                      <div>
                        <p className="font-semibold text-gray-900">{snapshot.account_name}</p>
                        <p className="text-sm text-gray-500">
                          {formatDate(snapshot.statement_date)} • {snapshot.position_count} positions
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-xl font-bold text-gray-900">{formatCurrency(snapshot.total_value)}</p>
                      {snapshot.is_reconciled ? (
                        <span className="text-xs text-emerald-600 font-medium">Reconciled</span>
                      ) : (
                        <span className="text-xs text-amber-600 font-medium">Review needed</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Import Modal */}
        {showImportModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between p-6 border-b">
                <h2 className="text-xl font-bold text-gray-900">
                  {importStep === 'upload' && 'Import Brokerage Statement'}
                  {importStep === 'preview' && 'Review Holdings'}
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
                      Upload a PDF statement from Fidelity or Schwab.
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf"
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
                      {importing ? 'Processing...' : 'Select PDF File'}
                    </label>
                  </div>
                )}

                {/* Preview Step */}
                {importStep === 'preview' && parseResult && (
                  <div>
                    <div className="bg-emerald-50 rounded-lg p-4 mb-6">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-semibold text-emerald-800">
                            {parseResult.provider.charAt(0).toUpperCase() + parseResult.provider.slice(1)} Statement
                          </p>
                          <p className="text-sm text-emerald-600">
                            {getAccountTypeLabel(parseResult.account_type)} • {parseResult.statement_date ? formatDate(parseResult.statement_date) : 'Unknown date'}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-2xl font-bold text-emerald-800">
                            {formatCurrency(parseResult.total_value)}
                          </p>
                          {parseResult.is_reconciled ? (
                            <span className="text-xs text-emerald-600">Reconciled</span>
                          ) : (
                            <span className="text-xs text-amber-600">
                              Diff: {formatCurrency(parseResult.reconciliation_diff)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Warnings */}
                    {parseResult.warnings.length > 0 && (
                      <div className="bg-amber-50 rounded-lg p-4 mb-6">
                        <p className="font-semibold text-amber-800 mb-2">Warnings</p>
                        {parseResult.warnings.map((warning, i) => (
                          <p key={i} className="text-sm text-amber-700">{warning}</p>
                        ))}
                      </div>
                    )}

                    {/* Positions Preview */}
                    <div className="border rounded-lg overflow-hidden mb-6">
                      <table className="w-full text-sm">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="text-left px-4 py-2 font-semibold text-gray-700">Symbol</th>
                            <th className="text-left px-4 py-2 font-semibold text-gray-700">Name</th>
                            <th className="text-right px-4 py-2 font-semibold text-gray-700">Shares</th>
                            <th className="text-right px-4 py-2 font-semibold text-gray-700">Value</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {parseResult.positions.slice(0, 10).map((pos, i) => (
                            <tr key={i}>
                              <td className="px-4 py-2 font-mono text-gray-900">{pos.symbol || '-'}</td>
                              <td className="px-4 py-2 text-gray-600 truncate max-w-[200px]">{pos.security_name}</td>
                              <td className="px-4 py-2 text-right text-gray-900">
                                {pos.quantity?.toLocaleString() || '-'}
                              </td>
                              <td className="px-4 py-2 text-right font-semibold text-gray-900">
                                {formatCurrency(pos.market_value)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {parseResult.positions.length > 10 && (
                        <div className="bg-gray-50 px-4 py-2 text-sm text-gray-500 text-center">
                          + {parseResult.positions.length - 10} more positions
                        </div>
                      )}
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
                        disabled={importing}
                        className="flex-1 py-2 px-4 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-lg hover:from-emerald-700 hover:to-teal-700 disabled:bg-gray-400"
                      >
                        {importing ? 'Importing...' : 'Confirm Import'}
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
                            <td className="px-4 py-3 text-gray-600">{pos.security_name}</td>
                            <td className="px-4 py-3 text-right text-gray-900">
                              {pos.quantity?.toLocaleString(undefined, { maximumFractionDigits: 4 }) || '-'}
                            </td>
                            <td className="px-4 py-3 text-right text-gray-600">
                              {pos.price ? formatCurrency(pos.price) : '-'}
                            </td>
                            <td className="px-4 py-3 text-right font-semibold text-gray-900">
                              {formatCurrency(pos.market_value)}
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
