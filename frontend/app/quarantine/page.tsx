'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  getQuarantinedTransactions,
  updateQuarantinedTransaction,
  retryQuarantinedTransaction,
  discardQuarantinedTransaction,
  bulkRetryQuarantined,
  bulkDiscardQuarantined,
  QuarantinedTransaction,
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function QuarantinePage() {
  const [items, setItems] = useState<QuarantinedTransaction[]>([]);
  const [total, setTotal] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<string, any>>({});
  const [statusFilter, setStatusFilter] = useState<string>('PENDING');
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    loadQuarantined();
  }, [statusFilter]);

  async function loadQuarantined() {
    try {
      setLoading(true);
      setError(null);
      const data = await getQuarantinedTransactions({
        status: statusFilter || undefined,
        limit: 100,
      });
      setItems(data.items);
      setTotal(data.total);
      setPendingCount(data.pending_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load quarantined transactions');
    } finally {
      setLoading(false);
    }
  }

  async function handleRetry(id: string) {
    try {
      setActionLoading(id);
      const result = await retryQuarantinedTransaction(id);
      if (result.status === 'RESOLVED') {
        // Remove from list or update status
        setItems(items.filter(item => item.id !== id));
        setPendingCount(prev => Math.max(0, prev - 1));
      } else {
        // Update the item with new error message
        setItems(items.map(item =>
          item.id === id
            ? { ...item, error_message: result.error_message || item.error_message, retry_count: item.retry_count + 1 }
            : item
        ));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry transaction');
    } finally {
      setActionLoading(null);
    }
  }

  async function handleDiscard(id: string) {
    try {
      setActionLoading(id);
      await discardQuarantinedTransaction(id);
      if (statusFilter === 'PENDING') {
        setItems(items.filter(item => item.id !== id));
      } else {
        setItems(items.map(item =>
          item.id === id ? { ...item, status: 'DISCARDED' } : item
        ));
      }
      setPendingCount(prev => Math.max(0, prev - 1));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to discard transaction');
    } finally {
      setActionLoading(null);
    }
  }

  async function handleBulkRetry() {
    if (selectedIds.size === 0) return;
    try {
      setActionLoading('bulk');
      const result = await bulkRetryQuarantined(Array.from(selectedIds));
      // Reload to get fresh data
      await loadQuarantined();
      setSelectedIds(new Set());
      if (result.failed_count > 0) {
        setError(`${result.success_count} succeeded, ${result.failed_count} failed`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to bulk retry');
    } finally {
      setActionLoading(null);
    }
  }

  async function handleBulkDiscard() {
    if (selectedIds.size === 0) return;
    try {
      setActionLoading('bulk');
      await bulkDiscardQuarantined(Array.from(selectedIds));
      await loadQuarantined();
      setSelectedIds(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to bulk discard');
    } finally {
      setActionLoading(null);
    }
  }

  function startEdit(item: QuarantinedTransaction) {
    setEditingId(item.id);
    setEditValues({
      date: item.raw_data.date || '',
      amount: item.raw_data.amount || '',
      description: item.raw_data.description || item.raw_data.description_raw || '',
    });
  }

  async function saveEdit(id: string) {
    try {
      setActionLoading(id);
      await updateQuarantinedTransaction(id, {
        date: editValues.date,
        amount: parseFloat(editValues.amount),
        description: editValues.description,
      });
      // Update local state
      setItems(items.map(item =>
        item.id === id
          ? {
              ...item,
              raw_data: {
                ...item.raw_data,
                date: editValues.date,
                amount: parseFloat(editValues.amount),
                description: editValues.description,
              },
            }
          : item
      ));
      setEditingId(null);
      setEditValues({});
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save changes');
    } finally {
      setActionLoading(null);
    }
  }

  function cancelEdit() {
    setEditingId(null);
    setEditValues({});
  }

  function toggleSelect(id: string) {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  }

  function toggleSelectAll() {
    if (selectedIds.size === items.filter(i => i.status === 'PENDING').length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(items.filter(i => i.status === 'PENDING').map(i => i.id)));
    }
  }

  function getStatusBadge(status: string) {
    switch (status) {
      case 'PENDING':
        return <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-300">Pending</Badge>;
      case 'RESOLVED':
        return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300">Resolved</Badge>;
      case 'DISCARDED':
        return <Badge variant="outline" className="bg-gray-50 text-gray-500 border-gray-300">Discarded</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  }

  function getErrorTypeBadge(errorType: string) {
    switch (errorType) {
      case 'PARSE_ERROR':
        return <Badge variant="destructive" className="bg-red-100 text-red-700">Parse Error</Badge>;
      case 'VALIDATION_ERROR':
        return <Badge variant="outline" className="bg-orange-50 text-orange-700 border-orange-300">Validation Error</Badge>;
      case 'DUPLICATE':
        return <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-300">Duplicate</Badge>;
      default:
        return <Badge variant="outline">{errorType}</Badge>;
    }
  }

  function formatCurrency(value: number | string | undefined): string {
    if (value === undefined || value === null) return '-';
    const num = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(num)) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(num);
  }

  function formatDate(dateStr: string | undefined): string {
    if (!dateStr) return '-';
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateStr;
    }
  }

  const pendingItems = items.filter(i => i.status === 'PENDING');

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Page Header */}
        <div className="mb-10">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-lg">
                <span className="text-2xl">&#9888;</span>
              </div>
              <div>
                <h1 className="text-4xl font-black bg-gradient-to-r from-gray-900 via-amber-900 to-orange-900 bg-clip-text text-transparent">
                  Quarantine Review
                </h1>
                <p className="text-gray-600 mt-1">
                  {pendingCount > 0 ? (
                    <span className="text-amber-600 font-medium">{pendingCount} items need attention</span>
                  ) : (
                    'All clear - no pending items'
                  )}
                </p>
              </div>
            </div>
            <Link
              href="/imports"
              className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-all"
            >
              <span className="mr-2">&larr;</span>
              Back to Imports
            </Link>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-6 bg-red-50 border-l-4 border-red-500 rounded-lg p-4 shadow-sm">
            <div className="flex items-start justify-between">
              <div className="flex items-start">
                <span className="text-red-500 text-xl mr-3">!</span>
                <p className="text-red-800">{error}</p>
              </div>
              <button
                onClick={() => setError(null)}
                className="text-red-500 hover:text-red-700"
              >
                &times;
              </button>
            </div>
          </div>
        )}

        {/* Filter Buttons */}
        <div className="mb-6 flex items-center gap-4">
          <div className="flex gap-2">
            <button
              onClick={() => setStatusFilter('PENDING')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                statusFilter === 'PENDING'
                  ? 'bg-amber-100 text-amber-800 border-2 border-amber-500'
                  : 'bg-white text-gray-600 border-2 border-gray-200 hover:bg-gray-50'
              }`}
            >
              Pending {pendingCount > 0 && `(${pendingCount})`}
            </button>
            <button
              onClick={() => setStatusFilter('')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                statusFilter === ''
                  ? 'bg-amber-100 text-amber-800 border-2 border-amber-500'
                  : 'bg-white text-gray-600 border-2 border-gray-200 hover:bg-gray-50'
              }`}
            >
              All ({total})
            </button>
          </div>

          {/* Bulk Actions */}
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-sm text-gray-600">{selectedIds.size} selected</span>
              <Button
                variant="outline"
                size="sm"
                onClick={handleBulkRetry}
                disabled={actionLoading === 'bulk'}
                className="text-green-600 border-green-300 hover:bg-green-50"
              >
                Retry Selected
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleBulkDiscard}
                disabled={actionLoading === 'bulk'}
                className="text-red-600 border-red-300 hover:bg-red-50"
              >
                Discard Selected
              </Button>
            </div>
          )}
        </div>

        {/* Loading State */}
        {loading && (
          <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-2xl border border-white/50 p-8">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-amber-200 border-t-amber-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading quarantined transactions...</p>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!loading && items.length === 0 && (
          <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-2xl border border-white/50 p-8">
            <div className="text-center py-12">
              <div className="mx-auto w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mb-4">
                <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-2">No Quarantined Items</h3>
              <p className="text-gray-600 mb-6">
                {statusFilter === 'PENDING'
                  ? 'All transactions have been processed successfully!'
                  : 'No quarantined transactions found.'}
              </p>
              <Link
                href="/imports"
                className="inline-flex items-center px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-lg hover:from-indigo-700 hover:to-purple-700 transition-all"
              >
                Go to Imports
              </Link>
            </div>
          </div>
        )}

        {/* Quarantined Items List */}
        {!loading && items.length > 0 && (
          <div className="space-y-4">
            {/* Select All (only for pending items) */}
            {statusFilter === 'PENDING' && pendingItems.length > 0 && (
              <div className="flex items-center gap-2 px-4">
                <input
                  type="checkbox"
                  checked={selectedIds.size === pendingItems.length && pendingItems.length > 0}
                  onChange={toggleSelectAll}
                  className="h-4 w-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                />
                <span className="text-sm text-gray-600">Select all pending</span>
              </div>
            )}

            {items.map((item) => (
              <Card key={item.id} className="bg-white/70 backdrop-blur-xl border-white/50">
                <CardContent className="p-6">
                  <div className="flex items-start gap-4">
                    {/* Checkbox */}
                    {item.status === 'PENDING' && (
                      <input
                        type="checkbox"
                        checked={selectedIds.has(item.id)}
                        onChange={() => toggleSelect(item.id)}
                        className="mt-1 h-4 w-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                      />
                    )}

                    {/* Main Content */}
                    <div className="flex-1 min-w-0">
                      {/* Status and Error Type Badges */}
                      <div className="flex items-center gap-2 mb-3">
                        {getStatusBadge(item.status)}
                        {getErrorTypeBadge(item.error_type)}
                        {item.retry_count > 0 && (
                          <Badge variant="outline" className="text-gray-500">
                            Retried {item.retry_count}x
                          </Badge>
                        )}
                        {item.import_filename && (
                          <span className="text-xs text-gray-500 ml-auto">
                            From: {item.import_filename}
                          </span>
                        )}
                      </div>

                      {/* Error Message */}
                      <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
                        <p className="text-sm text-red-700">
                          <span className="font-medium">Error: </span>
                          {item.error_message}
                        </p>
                        {item.error_field && (
                          <p className="text-xs text-red-600 mt-1">
                            Field: {item.error_field}
                          </p>
                        )}
                      </div>

                      {/* Transaction Details - Edit Mode */}
                      {editingId === item.id ? (
                        <div className="grid grid-cols-3 gap-4 mb-4">
                          <div>
                            <label className="block text-xs font-medium text-gray-500 mb-1">Date</label>
                            <Input
                              type="date"
                              value={editValues.date || ''}
                              onChange={(e) => setEditValues({ ...editValues, date: e.target.value })}
                              className="text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-500 mb-1">Amount</label>
                            <Input
                              type="number"
                              step="0.01"
                              value={editValues.amount || ''}
                              onChange={(e) => setEditValues({ ...editValues, amount: e.target.value })}
                              className="text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-500 mb-1">Description</label>
                            <Input
                              type="text"
                              value={editValues.description || ''}
                              onChange={(e) => setEditValues({ ...editValues, description: e.target.value })}
                              className="text-sm"
                            />
                          </div>
                        </div>
                      ) : (
                        <div className="grid grid-cols-3 gap-4 mb-4">
                          <div>
                            <span className="block text-xs font-medium text-gray-500 mb-1">Date</span>
                            <span className="text-sm text-gray-900">
                              {formatDate(item.raw_data.date)}
                            </span>
                          </div>
                          <div>
                            <span className="block text-xs font-medium text-gray-500 mb-1">Amount</span>
                            <span className="text-sm font-medium text-gray-900">
                              {formatCurrency(item.raw_data.amount)}
                            </span>
                          </div>
                          <div>
                            <span className="block text-xs font-medium text-gray-500 mb-1">Description</span>
                            <span className="text-sm text-gray-900 truncate block">
                              {item.raw_data.description || item.raw_data.description_raw || '-'}
                            </span>
                          </div>
                        </div>
                      )}

                      {/* Account Info */}
                      {item.account_name && (
                        <p className="text-xs text-gray-500">
                          Account: {item.account_name}
                        </p>
                      )}
                    </div>

                    {/* Action Buttons */}
                    <div className="flex flex-col gap-2">
                      {item.status === 'PENDING' && (
                        <>
                          {editingId === item.id ? (
                            <>
                              <Button
                                variant="default"
                                size="sm"
                                onClick={() => saveEdit(item.id)}
                                disabled={actionLoading === item.id}
                                className="bg-green-600 hover:bg-green-700"
                              >
                                Save
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={cancelEdit}
                                disabled={actionLoading === item.id}
                              >
                                Cancel
                              </Button>
                            </>
                          ) : (
                            <>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => startEdit(item)}
                                disabled={actionLoading === item.id}
                              >
                                Edit
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleRetry(item.id)}
                                disabled={actionLoading === item.id}
                                className="text-green-600 border-green-300 hover:bg-green-50"
                              >
                                {actionLoading === item.id ? 'Retrying...' : 'Retry'}
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleDiscard(item.id)}
                                disabled={actionLoading === item.id}
                                className="text-red-600 border-red-300 hover:bg-red-50"
                              >
                                Discard
                              </Button>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
