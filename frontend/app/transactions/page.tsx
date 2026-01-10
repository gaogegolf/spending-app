'use client';

import { useEffect, useState } from 'react';
import { getTransactions, getAccounts, deleteTransaction, bulkDeleteTransactions, reclassifyAllTransactions, updateTransaction, exportTransactions } from '@/lib/api';
import { Transaction, Account, TransactionListResponse } from '@/lib/types';
import { TRANSACTION_TYPES, getCategoriesForType } from '@/lib/categories';

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [reclassifying, setReclassifying] = useState(false);
  const [reclassifySuccess, setReclassifySuccess] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  // Category editing state
  const [editingCategoryId, setEditingCategoryId] = useState<string | null>(null);
  const [savingCategory, setSavingCategory] = useState(false);

  // Type editing state
  const [editingTypeId, setEditingTypeId] = useState<string | null>(null);
  const [savingType, setSavingType] = useState(false);

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<'single' | 'bulk'>('bulk');
  const [singleDeleteId, setSingleDeleteId] = useState<string | null>(null);

  // Filters
  const [accountFilter, setAccountFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [descriptionFilter, setDescriptionFilter] = useState<string>('');
  const [needsReviewFilter, setNeedsReviewFilter] = useState<boolean | undefined>(undefined);
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');

  // Sorting state
  type SortColumn = 'date' | 'description' | 'category' | 'type' | 'amount' | 'review';
  const [sortColumn, setSortColumn] = useState<SortColumn>('date');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    loadAccounts();
  }, []);

  useEffect(() => {
    loadTransactions();
  }, [page, pageSize, accountFilter, typeFilter, categoryFilter, descriptionFilter, needsReviewFilter, startDate, endDate]);

  // Lock body scroll when modal is open (only for single delete)
  useEffect(() => {
    if (showDeleteConfirm && deleteTarget === 'single') {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [showDeleteConfirm, deleteTarget]);

  async function loadAccounts() {
    try {
      const data = await getAccounts();
      setAccounts(data.accounts || []);
    } catch (err) {
      console.error('Failed to load accounts:', err);
    }
  }

  async function loadTransactions() {
    try {
      setLoading(true);
      setError(null);

      const data: TransactionListResponse = await getTransactions({
        account_id: accountFilter || undefined,
        transaction_type: typeFilter || undefined,
        category: categoryFilter || undefined,
        description: descriptionFilter || undefined,
        needs_review: needsReviewFilter,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        page,
        page_size: pageSize,
      });

      setTransactions(data.transactions || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load transactions');
    } finally {
      setLoading(false);
    }
  }

  function resetFilters() {
    setAccountFilter('');
    setTypeFilter('');
    setCategoryFilter('');
    setDescriptionFilter('');
    setNeedsReviewFilter(undefined);
    setStartDate('');
    setEndDate('');
    setPage(1);
  }

  function setDatePreset(preset: 'this_month' | 'last_month' | 'last_3_months' | 'last_6_months' | 'this_year' | 'last_year') {
    const now = new Date();
    let start = new Date();
    let end = new Date();

    switch (preset) {
      case 'this_month':
        start = new Date(now.getFullYear(), now.getMonth(), 1);
        end = now;
        break;
      case 'last_month':
        start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        end = new Date(now.getFullYear(), now.getMonth(), 0);
        break;
      case 'last_3_months':
        start = new Date(now.getFullYear(), now.getMonth() - 3, 1);
        end = now;
        break;
      case 'last_6_months':
        start = new Date(now.getFullYear(), now.getMonth() - 6, 1);
        end = now;
        break;
      case 'this_year':
        start = new Date(now.getFullYear(), 0, 1);
        end = now;
        break;
      case 'last_year':
        start = new Date(now.getFullYear() - 1, 0, 1);
        end = new Date(now.getFullYear() - 1, 11, 31);
        break;
    }

    setStartDate(start.toISOString().split('T')[0]);
    setEndDate(end.toISOString().split('T')[0]);
    setPage(1);
  }

  function toggleSelectAll() {
    if (selectedIds.size === sortedTransactions.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(sortedTransactions.map(t => t.id)));
    }
  }

  function toggleSelectTransaction(id: string) {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  }

  function handleDeleteClick(id?: string) {
    if (id) {
      setDeleteTarget('single');
      setSingleDeleteId(id);
    } else {
      setDeleteTarget('bulk');
    }
    setShowDeleteConfirm(true);
  }

  async function confirmDelete() {
    try {
      setDeleting(true);
      setError(null);

      if (deleteTarget === 'single' && singleDeleteId) {
        await deleteTransaction(singleDeleteId);
      } else if (deleteTarget === 'bulk') {
        await bulkDeleteTransactions(Array.from(selectedIds));
      }

      // Reset selection and reload
      setSelectedIds(new Set());
      setShowDeleteConfirm(false);
      await loadTransactions();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete transactions');
    } finally {
      setDeleting(false);
    }
  }

  async function handleReclassifyAll() {
    try {
      setReclassifying(true);
      setError(null);
      setReclassifySuccess(null);

      const result = await reclassifyAllTransactions();
      setReclassifySuccess(`Successfully re-classified ${result.reclassified_count} of ${result.total_transactions} transactions!`);

      // Reload transactions to show new categories
      await loadTransactions();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reclassify transactions');
    } finally {
      setReclassifying(false);
    }
  }

  async function handleExport() {
    try {
      setExporting(true);
      setError(null);

      await exportTransactions({
        account_id: accountFilter || undefined,
        transaction_type: typeFilter || undefined,
        category: categoryFilter || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export transactions');
    } finally {
      setExporting(false);
    }
  }

  async function handleCategoryChange(transactionId: string, newCategory: string) {
    try {
      setSavingCategory(true);
      setError(null);

      await updateTransaction(transactionId, { category: newCategory });

      // Update the transaction in local state
      setTransactions(transactions.map(t =>
        t.id === transactionId ? { ...t, category: newCategory, classification_method: 'MANUAL' as const } : t
      ));

      setEditingCategoryId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update category');
    } finally {
      setSavingCategory(false);
    }
  }

  async function handleTypeChange(transactionId: string, newType: string) {
    try {
      setSavingType(true);
      setError(null);

      await updateTransaction(transactionId, { transaction_type: newType });

      // Update the transaction in local state
      setTransactions(transactions.map(t =>
        t.id === transactionId ? { ...t, transaction_type: newType as Transaction['transaction_type'], classification_method: 'MANUAL' as const } : t
      ));

      setEditingTypeId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update transaction type');
    } finally {
      setSavingType(false);
    }
  }

  function formatDateDisplay(dateString: string): string {
    if (!dateString) return '';
    // Parse the date string as local date, not UTC
    const [year, month, day] = dateString.split('-').map(Number);
    return new Date(year, month - 1, day).toLocaleDateString();
  }

  function calculateDisplayedTotal(): number {
    return sortedTransactions.reduce((sum, transaction) => {
      const amount = parseFloat(transaction.amount);
      // Subtract expenses, add income
      if (transaction.is_spend) {
        return sum - amount;
      } else if (transaction.is_income) {
        return sum + amount;
      }
      // For other types (transfers, payments, etc.), don't include in net
      return sum;
    }, 0);
  }

  function getTransactionTypeColor(type: string): string {
    switch (type) {
      case 'EXPENSE':
        return 'bg-red-100 text-red-800';
      case 'INCOME':
        return 'bg-green-100 text-green-800';
      case 'TRANSFER':
        return 'bg-blue-100 text-blue-800';
      case 'UNCATEGORIZED':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  }

  function handleSort(column: SortColumn) {
    if (sortColumn === column) {
      // Toggle direction if same column
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      // New column, default to descending for date/amount, ascending for others
      setSortColumn(column);
      setSortDirection(column === 'date' || column === 'amount' ? 'desc' : 'asc');
    }
  }

  function getSortIcon(column: SortColumn) {
    if (sortColumn !== column) {
      return (
        <span className="ml-1 text-gray-400">⇅</span>
      );
    }
    return sortDirection === 'asc' ? (
      <span className="ml-1 text-indigo-600">↑</span>
    ) : (
      <span className="ml-1 text-indigo-600">↓</span>
    );
  }

  // Sort transactions
  const sortedTransactions = [...transactions].sort((a, b) => {
    let comparison = 0;

    switch (sortColumn) {
      case 'date':
        comparison = new Date(a.date).getTime() - new Date(b.date).getTime();
        break;
      case 'description':
        const descA = (a.merchant_normalized || a.description_raw).toLowerCase();
        const descB = (b.merchant_normalized || b.description_raw).toLowerCase();
        comparison = descA.localeCompare(descB);
        break;
      case 'category':
        const catA = (a.category || '').toLowerCase();
        const catB = (b.category || '').toLowerCase();
        comparison = catA.localeCompare(catB);
        break;
      case 'type':
        comparison = a.transaction_type.localeCompare(b.transaction_type);
        break;
      case 'amount':
        comparison = parseFloat(a.amount) - parseFloat(b.amount);
        break;
      case 'review':
        comparison = (a.needs_review ? 1 : 0) - (b.needs_review ? 1 : 0);
        break;
    }

    return sortDirection === 'asc' ? comparison : -comparison;
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Transactions</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExport}
            disabled={exporting}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm flex items-center gap-2"
          >
            {exporting ? (
              <>
                <span className="animate-spin">⟳</span>
                Exporting...
              </>
            ) : (
              <>
                <span>📥</span>
                Export CSV
              </>
            )}
          </button>
          <button
            onClick={handleReclassifyAll}
            disabled={reclassifying}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm flex items-center gap-2"
          >
            {reclassifying ? (
              <>
                <span className="animate-spin">⟳</span>
                Re-classifying...
              </>
            ) : (
              <>
                <span>🔄</span>
                Re-classify All
              </>
            )}
          </button>
        </div>
      </div>

      {/* Success Message */}
      {reclassifySuccess && (
        <div className="mb-6 bg-green-50 border-l-4 border-green-500 rounded-lg p-4 shadow-sm">
          <div className="flex items-start">
            <span className="text-green-500 text-xl mr-3">✓</span>
            <p className="text-green-800">{reclassifySuccess}</p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Filters</h2>

        {/* Date Range Presets */}
        <div className="mb-4 pb-4 border-b border-gray-200">
          <label htmlFor="date-preset" className="block text-sm font-medium text-gray-700 mb-2">
            Quick Date Range
          </label>
          <select
            id="date-preset"
            onChange={(e) => {
              if (e.target.value) {
                setDatePreset(e.target.value as any);
              }
            }}
            defaultValue=""
            className="block w-full sm:w-64 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
          >
            <option value="">Select a date range...</option>
            <option value="this_month">This Month</option>
            <option value="last_month">Last Month</option>
            <option value="last_3_months">Last 3 Months</option>
            <option value="last_6_months">Last 6 Months</option>
            <option value="this_year">This Year</option>
            <option value="last_year">Last Year</option>
          </select>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {/* Start Date */}
          <div>
            <label htmlFor="start-date" className="block text-sm font-medium text-gray-700 mb-1">
              Start Date
            </label>
            <input
              type="date"
              id="start-date"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                setPage(1);
              }}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            />
          </div>

          {/* End Date */}
          <div>
            <label htmlFor="end-date" className="block text-sm font-medium text-gray-700 mb-1">
              End Date
            </label>
            <input
              type="date"
              id="end-date"
              value={endDate}
              onChange={(e) => {
                setEndDate(e.target.value);
                setPage(1);
              }}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            />
          </div>

          {/* Account Filter */}
          <div>
            <label htmlFor="account-filter" className="block text-sm font-medium text-gray-700 mb-1">
              Account
            </label>
            <select
              id="account-filter"
              value={accountFilter}
              onChange={(e) => {
                setAccountFilter(e.target.value);
                setPage(1);
              }}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            >
              <option value="">All Accounts</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          </div>

          {/* Type Filter */}
          <div>
            <label htmlFor="type-filter" className="block text-sm font-medium text-gray-700 mb-1">
              Type
            </label>
            <select
              id="type-filter"
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value);
                setCategoryFilter(''); // Clear category when type changes
                setPage(1);
              }}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            >
              <option value="">All Types</option>
              {TRANSACTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type.charAt(0) + type.slice(1).toLowerCase()}
                </option>
              ))}
            </select>
          </div>

          {/* Category Filter */}
          <div>
            <label htmlFor="category-filter" className="block text-sm font-medium text-gray-700 mb-1">
              Category
            </label>
            <select
              id="category-filter"
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(1);
              }}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            >
              <option value="">All Categories</option>
              {getCategoriesForType(typeFilter).map((cat) => (
                <option key={cat.id} value={cat.name}>
                  {cat.name}
                </option>
              ))}
            </select>
          </div>

          {/* Description Filter */}
          <div>
            <label htmlFor="description-filter" className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <input
              type="text"
              id="description-filter"
              value={descriptionFilter}
              onChange={(e) => {
                setDescriptionFilter(e.target.value);
                setPage(1);
              }}
              placeholder="Search description..."
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            />
          </div>

          {/* Needs Review Filter */}
          <div>
            <label htmlFor="review-filter" className="block text-sm font-medium text-gray-700 mb-1">
              Review Status
            </label>
            <select
              id="review-filter"
              value={needsReviewFilter === undefined ? '' : String(needsReviewFilter)}
              onChange={(e) => {
                const value = e.target.value;
                setNeedsReviewFilter(value === '' ? undefined : value === 'true');
                setPage(1);
              }}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            >
              <option value="">All</option>
              <option value="true">Needs Review</option>
              <option value="false">Reviewed</option>
            </select>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between">
          <button
            onClick={resetFilters}
            className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
          >
            Reset All Filters
          </button>
          {(startDate || endDate) && (
            <span className="text-sm text-gray-600">
              {startDate && endDate
                ? `${formatDateDisplay(startDate)} - ${formatDateDisplay(endDate)}`
                : startDate
                ? `From ${formatDateDisplay(startDate)}`
                : `Until ${formatDateDisplay(endDate)}`}
            </span>
          )}
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Summary Bar - Moved to top */}
      {!loading && transactions.length > 0 && (
        <div className="bg-white shadow rounded-lg p-4 mb-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            {/* Results count and page size */}
            <div className="flex items-center gap-4 flex-wrap">
              <div className="text-sm text-gray-700">
                Showing <span className="font-medium">{(page - 1) * pageSize + 1}</span> to{' '}
                <span className="font-medium">{Math.min(page * pageSize, total)}</span> of{' '}
                <span className="font-medium">{total}</span> results
              </div>
              <div className="flex items-center gap-2">
                <label htmlFor="page-size-top" className="text-sm text-gray-700">
                  Show:
                </label>
                <select
                  id="page-size-top"
                  value={pageSize}
                  onChange={(e) => {
                    const newSize = parseInt(e.target.value);
                    setPageSize(newSize);
                    setPage(1);
                    setSelectedIds(new Set());
                  }}
                  className="px-2 py-1 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                >
                  <option value="50">50</option>
                  <option value="100">100</option>
                  <option value="200">200</option>
                  <option value="500">500</option>
                  <option value="1000">1000</option>
                  <option value="10000">All</option>
                </select>
              </div>
              {/* Pagination buttons */}
              {total > pageSize && (
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage(page - 1)}
                    disabled={page === 1}
                    className="px-3 py-1 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:bg-gray-100 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPage(page + 1)}
                    disabled={page * pageSize >= total}
                    className="px-3 py-1 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:bg-gray-100 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>

            {/* Net Amount */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">Net Amount:</span>
              <span className={`text-lg font-bold ${calculateDisplayedTotal() >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {calculateDisplayedTotal() >= 0 ? '+' : '-'}${Math.abs(calculateDisplayedTotal()).toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Transactions Table */}
      {loading ? (
        <div className="bg-white shadow rounded-lg p-12">
          <div className="text-center">
            <p className="text-gray-500">Loading transactions...</p>
          </div>
        </div>
      ) : transactions.length === 0 ? (
        <div className="bg-white shadow rounded-lg p-12">
          <div className="text-center">
            <p className="text-gray-500">No transactions found.</p>
            <a
              href="/imports"
              className="mt-4 inline-block text-indigo-600 hover:text-indigo-800"
            >
              Import transactions to get started
            </a>
          </div>
        </div>
      ) : (
        <>
          {/* Bulk Actions Bar */}
          {selectedIds.size > 0 && (
            <div className="bg-indigo-50 border-l-4 border-indigo-500 rounded-lg p-4 mb-4">
              {!showDeleteConfirm || deleteTarget === 'single' ? (
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className="text-indigo-700 font-medium">
                      {selectedIds.size} transaction{selectedIds.size !== 1 ? 's' : ''} selected
                    </span>
                  </div>
                  <button
                    onClick={() => handleDeleteClick()}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors font-medium text-sm"
                  >
                    Delete Selected
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-start">
                    <div className="flex-shrink-0 h-5 w-5 text-red-600 mr-2">
                      <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                      </svg>
                    </div>
                    <div className="flex-1">
                      <h3 className="text-sm font-medium text-gray-900">Confirm Deletion</h3>
                      <p className="mt-1 text-sm text-gray-600">
                        Are you sure you want to delete {selectedIds.size} transaction{selectedIds.size !== 1 ? 's' : ''}? This action cannot be undone.
                      </p>
                    </div>
                  </div>
                  <div className="flex justify-end gap-3">
                    <button
                      onClick={() => {
                        setShowDeleteConfirm(false);
                        setSingleDeleteId(null);
                      }}
                      disabled={deleting}
                      className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={confirmDelete}
                      disabled={deleting}
                      className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm"
                    >
                      {deleting ? 'Deleting...' : `Delete ${selectedIds.size} Transaction${selectedIds.size !== 1 ? 's' : ''}`}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left">
                    <input
                      type="checkbox"
                      checked={selectedIds.size === sortedTransactions.length && sortedTransactions.length > 0}
                      onChange={toggleSelectAll}
                      className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded cursor-pointer"
                    />
                  </th>
                  <th
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('date')}
                  >
                    <div className="flex items-center">
                      Date{getSortIcon('date')}
                    </div>
                  </th>
                  <th
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('description')}
                  >
                    <div className="flex items-center">
                      Description{getSortIcon('description')}
                    </div>
                  </th>
                  <th
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('category')}
                  >
                    <div className="flex items-center">
                      Category{getSortIcon('category')}
                    </div>
                  </th>
                  <th
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('type')}
                  >
                    <div className="flex items-center">
                      Type{getSortIcon('type')}
                    </div>
                  </th>
                  <th
                    className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('amount')}
                  >
                    <div className="flex items-center justify-end">
                      Amount{getSortIcon('amount')}
                    </div>
                  </th>
                  <th
                    className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('review')}
                  >
                    <div className="flex items-center justify-center">
                      Review{getSortIcon('review')}
                    </div>
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {sortedTransactions.map((transaction) => (
                  <tr key={transaction.id} className="hover:bg-gray-50">
                    <td className="px-4 py-4">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(transaction.id)}
                        onChange={() => toggleSelectTransaction(transaction.id)}
                        className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded cursor-pointer"
                      />
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {new Date(transaction.date).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      <div className="max-w-xs truncate" title={transaction.description_raw}>
                        {transaction.merchant_normalized || transaction.description_raw}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {editingCategoryId === transaction.id ? (
                        <select
                          autoFocus
                          disabled={savingCategory}
                          defaultValue={transaction.category || ''}
                          onChange={(e) => handleCategoryChange(transaction.id, e.target.value)}
                          onBlur={() => setEditingCategoryId(null)}
                          className="w-full px-2 py-1 border border-indigo-500 rounded focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
                        >
                          <option value="">Select category...</option>
                          {getCategoriesForType(transaction.transaction_type).map((cat) => (
                            <option key={cat.id} value={cat.name}>
                              {cat.name}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <button
                          onClick={() => setEditingCategoryId(transaction.id)}
                          className="text-left hover:text-indigo-600 hover:underline focus:outline-none focus:text-indigo-600 w-full"
                          title="Click to change category"
                        >
                          {transaction.category || '-'}
                          {transaction.classification_method === 'LEARNED' && (
                            <span className="ml-1 text-xs text-green-600" title="Learned from your edits">✓</span>
                          )}
                        </button>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {editingTypeId === transaction.id ? (
                        <select
                          autoFocus
                          disabled={savingType}
                          defaultValue={transaction.transaction_type}
                          onChange={(e) => handleTypeChange(transaction.id, e.target.value)}
                          onBlur={() => setEditingTypeId(null)}
                          className="px-2 py-1 border border-indigo-500 rounded focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
                        >
                          {TRANSACTION_TYPES.map((type) => (
                            <option key={type} value={type}>
                              {type.charAt(0) + type.slice(1).toLowerCase()}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <button
                          onClick={() => setEditingTypeId(transaction.id)}
                          className="focus:outline-none"
                          title="Click to change type"
                        >
                          <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${getTransactionTypeColor(transaction.transaction_type)} hover:ring-2 hover:ring-indigo-300 cursor-pointer transition-all`}>
                            {transaction.transaction_type}
                          </span>
                        </button>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right">
                      <span className={transaction.is_spend ? 'text-red-600' : transaction.is_income ? 'text-green-600' : 'text-gray-900'}>
                        ${parseFloat(transaction.amount).toFixed(2)}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-center">
                      {transaction.needs_review && (
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                          Review
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-center">
                      <button
                        onClick={() => handleDeleteClick(transaction.id)}
                        className="text-red-600 hover:text-red-800 text-sm font-medium"
                        title="Delete transaction"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

        </>
      )}

      {/* Delete Confirmation Modal (for single transaction delete only) */}
      {showDeleteConfirm && deleteTarget === 'single' && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          onClick={(e) => {
            // Close modal if clicking on backdrop
            if (e.target === e.currentTarget && !deleting) {
              setShowDeleteConfirm(false);
              setSingleDeleteId(null);
            }
          }}
        >
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Confirm Delete</h3>
            <p className="text-gray-600 mb-6">
              Are you sure you want to delete this transaction? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setSingleDeleteId(null);
                }}
                disabled={deleting}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
              >
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
