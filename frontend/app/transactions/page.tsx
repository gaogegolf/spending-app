'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { getTransactions, getAccounts, deleteTransaction, bulkDeleteTransactions, reclassifyAllTransactions, updateTransaction, exportTransactions, getMerchantTransactionCount, applyMerchantCategory, createTransaction } from '@/lib/api';
import { Transaction, Account, TransactionListResponse } from '@/lib/types';
import { TRANSACTION_TYPES, getCategoriesForType } from '@/lib/categories';
import { formatDate, compareDates } from '@/lib/dateUtils';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

// Brokerage accounts don't have transactions - they have positions
const BROKERAGE_ACCOUNT_TYPES = ['BROKERAGE', 'IRA_ROTH', 'IRA_TRADITIONAL', 'RETIREMENT_401K', 'STOCK_PLAN'];

export default function TransactionsPage() {
  const searchParams = useSearchParams();

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

  // Note editing state
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [noteValue, setNoteValue] = useState<string>('');
  const [savingNote, setSavingNote] = useState(false);

  // Apply merchant category prompt state
  const [showApplyMerchantPrompt, setShowApplyMerchantPrompt] = useState(false);
  const [applyMerchantData, setApplyMerchantData] = useState<{
    merchant: string;
    category: string;
    transactionId: string;
    otherCount: number;
  } | null>(null);
  const [applyingMerchant, setApplyingMerchant] = useState(false);

  // Add transaction dialog state
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [addingTransaction, setAddingTransaction] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [addForm, setAddForm] = useState({
    date: new Date().toISOString().split('T')[0],
    description_raw: '',
    amount: '',
    account_id: '',
    transaction_type: 'EXPENSE' as string,
    category: '',
    subcategory: '',
    merchant_normalized: '',
    user_note: '',
    currency: 'USD',
  });

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<'single' | 'bulk'>('bulk');
  const [singleDeleteId, setSingleDeleteId] = useState<string | null>(null);

  // Filters - initialize from URL params
  const [accountFilter, setAccountFilter] = useState<string>(searchParams.get('account_id') || '');
  const [typeFilter, setTypeFilter] = useState<string>(searchParams.get('transaction_type') || '');
  const [categoryFilter, setCategoryFilter] = useState<string>(searchParams.get('category') || '');
  const [descriptionFilter, setDescriptionFilter] = useState<string>(searchParams.get('description') || '');
  const [matchRulePatternFilter, setMatchRulePatternFilter] = useState<string>(searchParams.get('match_rule_pattern') || '');
  const [startDate, setStartDate] = useState<string>(searchParams.get('start_date') || '');
  const [endDate, setEndDate] = useState<string>(searchParams.get('end_date') || '');

  // Sorting state
  type SortColumn = 'date' | 'description' | 'category' | 'type' | 'amount';
  const [sortColumn, setSortColumn] = useState<SortColumn>('date');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');

  // Grouping state
  type GroupBy = 'none' | 'merchant' | 'category' | 'type' | 'account' | 'month';
  const [groupBy, setGroupBy] = useState<GroupBy>('none');
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  // Filter panel state
  const [filtersExpanded, setFiltersExpanded] = useState(true);

  useEffect(() => {
    loadAccounts();
  }, []);

  useEffect(() => {
    loadTransactions();
  }, [page, pageSize, accountFilter, typeFilter, categoryFilter, descriptionFilter, matchRulePatternFilter, startDate, endDate]);

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
        match_rule_pattern: matchRulePatternFilter || undefined,
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
    setMatchRulePatternFilter('');
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
        description: descriptionFilter || undefined,
        match_rule_pattern: matchRulePatternFilter || undefined,
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

      // Find the transaction to get its merchant
      const transaction = transactions.find(t => t.id === transactionId);

      // Update the transaction in local state
      setTransactions(transactions.map(t =>
        t.id === transactionId ? { ...t, category: newCategory, classification_method: 'MANUAL' as const } : t
      ));

      setEditingCategoryId(null);

      // Check if there are other transactions with the same merchant
      if (transaction?.merchant_normalized) {
        try {
          const result = await getMerchantTransactionCount(transaction.merchant_normalized, transactionId);
          if (result.count > 0) {
            setApplyMerchantData({
              merchant: transaction.merchant_normalized,
              category: newCategory,
              transactionId: transactionId,
              otherCount: result.count,
            });
            setShowApplyMerchantPrompt(true);
          }
        } catch {
          // Silently ignore - don't block the main operation
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update category');
    } finally {
      setSavingCategory(false);
    }
  }

  async function handleApplyMerchantCategory() {
    if (!applyMerchantData) return;

    try {
      setApplyingMerchant(true);
      const result = await applyMerchantCategory(
        applyMerchantData.merchant,
        applyMerchantData.category,
        applyMerchantData.transactionId
      );

      // Reload transactions to show updated categories
      await loadTransactions();

      setShowApplyMerchantPrompt(false);
      setApplyMerchantData(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to apply category to other transactions');
    } finally {
      setApplyingMerchant(false);
    }
  }

  function closeApplyMerchantPrompt() {
    setShowApplyMerchantPrompt(false);
    setApplyMerchantData(null);
  }

  function resetAddForm() {
    setAddForm({
      date: new Date().toISOString().split('T')[0],
      description_raw: '',
      amount: '',
      account_id: '',
      transaction_type: 'EXPENSE',
      category: '',
      subcategory: '',
      merchant_normalized: '',
      user_note: '',
      currency: 'USD',
    });
    setAddError(null);
  }

  async function handleAddTransaction(e: React.FormEvent) {
    e.preventDefault();

    if (!addForm.date || !addForm.description_raw || !addForm.amount || !addForm.account_id || !addForm.transaction_type) {
      setAddError('Please fill in all required fields');
      return;
    }

    try {
      setAddingTransaction(true);
      setAddError(null);

      await createTransaction({
        account_id: addForm.account_id,
        date: addForm.date,
        description_raw: addForm.description_raw,
        amount: parseFloat(addForm.amount),
        transaction_type: addForm.transaction_type,
        currency: addForm.currency || 'USD',
        category: addForm.category || undefined,
        subcategory: addForm.subcategory || undefined,
        merchant_normalized: addForm.merchant_normalized || undefined,
        user_note: addForm.user_note || undefined,
      });

      setShowAddDialog(false);
      resetAddForm();
      await loadTransactions();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add transaction');
    } finally {
      setAddingTransaction(false);
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

  async function handleNoteUpdate(transactionId: string) {
    try {
      setSavingNote(true);
      setError(null);

      await updateTransaction(transactionId, { user_note: noteValue });

      // Update the transaction in local state
      setTransactions(transactions.map(t =>
        t.id === transactionId ? { ...t, user_note: noteValue } : t
      ));

      setEditingNoteId(null);
      setNoteValue('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update note');
    } finally {
      setSavingNote(false);
    }
  }

  function startEditingNote(transaction: Transaction) {
    setEditingNoteId(transaction.id);
    setNoteValue(transaction.user_note || '');
  }

  function cancelEditingNote() {
    setEditingNoteId(null);
    setNoteValue('');
  }

  function formatDateDisplay(dateString: string): string {
    return formatDate(dateString);
  }

  function calculateDisplayedTotal(): number {
    return sortedTransactions.reduce((sum, transaction) => {
      const amount = parseFloat(transaction.amount);
      // Subtract expenses, add income
      // Note: Income from refunds/credits is stored as negative amounts,
      // so we subtract (which adds when amount is negative)
      if (transaction.is_spend) {
        return sum - amount;
      } else if (transaction.is_income) {
        return sum - amount;  // Subtracting negative amount = adding
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

  // Category color mapping for visual distinction
  function getCategoryColor(category: string | null): string {
    if (!category) return 'bg-gray-100 text-gray-700';

    const colors: Record<string, string> = {
      'Groceries': 'bg-green-100 text-green-700',
      'Restaurants': 'bg-orange-100 text-orange-700',
      'Entertainment': 'bg-purple-100 text-purple-700',
      'Travel': 'bg-blue-100 text-blue-700',
      'Gasoline/Fuel': 'bg-amber-100 text-amber-700',
      'Automotive': 'bg-slate-100 text-slate-700',
      'Healthcare/Medical': 'bg-red-100 text-red-700',
      'Insurance': 'bg-indigo-100 text-indigo-700',
      'Utilities': 'bg-cyan-100 text-cyan-700',
      'Rent': 'bg-rose-100 text-rose-700',
      'Mortgages': 'bg-pink-100 text-pink-700',
      'Education': 'bg-violet-100 text-violet-700',
      'Clothing/Shoes': 'bg-fuchsia-100 text-fuchsia-700',
      'Electronics': 'bg-sky-100 text-sky-700',
      'General Merchandise': 'bg-teal-100 text-teal-700',
      'Online Services': 'bg-emerald-100 text-emerald-700',
      'Dues & Subscriptions': 'bg-lime-100 text-lime-700',
      'Personal Care': 'bg-yellow-100 text-yellow-700',
      'Gifts': 'bg-red-50 text-red-600',
      'Taxes': 'bg-gray-200 text-gray-700',
      'Paychecks/Salary': 'bg-green-200 text-green-800',
      'Interest': 'bg-blue-50 text-blue-600',
      'Transfers': 'bg-slate-200 text-slate-700',
    };

    return colors[category] || 'bg-gray-100 text-gray-700';
  }

  // Get active filter count and descriptions
  function getActiveFilters(): { count: number; filters: { label: string; value: string; clear: () => void }[] } {
    const filters: { label: string; value: string; clear: () => void }[] = [];

    if (startDate) {
      filters.push({ label: 'From', value: formatDateDisplay(startDate), clear: () => setStartDate('') });
    }
    if (endDate) {
      filters.push({ label: 'Until', value: formatDateDisplay(endDate), clear: () => setEndDate('') });
    }
    if (accountFilter) {
      const accountName = accounts.find(a => a.id === accountFilter)?.name || accountFilter;
      filters.push({ label: 'Account', value: accountName, clear: () => setAccountFilter('') });
    }
    if (typeFilter) {
      filters.push({ label: 'Type', value: typeFilter.charAt(0) + typeFilter.slice(1).toLowerCase(), clear: () => setTypeFilter('') });
    }
    if (categoryFilter) {
      filters.push({ label: 'Category', value: categoryFilter, clear: () => setCategoryFilter('') });
    }
    if (descriptionFilter) {
      filters.push({ label: 'Description', value: descriptionFilter, clear: () => setDescriptionFilter('') });
    }
    if (groupBy !== 'none') {
      filters.push({ label: 'Grouped by', value: groupBy.charAt(0).toUpperCase() + groupBy.slice(1), clear: () => setGroupBy('none') });
    }

    return { count: filters.length, filters };
  }

  const activeFilters = getActiveFilters();

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
        comparison = compareDates(a.date, b.date);
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
    }

    return sortDirection === 'asc' ? comparison : -comparison;
  });

  // Grouping helper functions
  function getGroupKey(transaction: Transaction): string {
    switch (groupBy) {
      case 'merchant':
        return transaction.merchant_normalized || transaction.description_raw || 'Unknown';
      case 'category':
        return transaction.category || 'Uncategorized';
      case 'type':
        return transaction.transaction_type;
      case 'account':
        return transaction.account_id;
      case 'month':
        return transaction.date.substring(0, 7); // YYYY-MM
      default:
        return 'all';
    }
  }

  function getGroupLabel(key: string): string {
    switch (groupBy) {
      case 'account':
        return accounts.find(a => a.id === key)?.name || key;
      case 'month':
        const [year, month] = key.split('-');
        return new Date(parseInt(year), parseInt(month) - 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
      default:
        return key;
    }
  }

  function toggleGroup(key: string) {
    setCollapsedGroups(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function expandAllGroups() {
    setCollapsedGroups(new Set());
  }

  function collapseAllGroups() {
    const allKeys = groupedTransactions.map(g => g.key);
    setCollapsedGroups(new Set(allKeys));
  }

  // Group transactions
  const groupedTransactions = useMemo(() => {
    if (groupBy === 'none') {
      return [{ key: 'all', label: 'All Transactions', transactions: sortedTransactions, total: 0, count: sortedTransactions.length }];
    }

    const groups: Record<string, Transaction[]> = {};
    sortedTransactions.forEach(t => {
      const key = getGroupKey(t);
      if (!groups[key]) groups[key] = [];
      groups[key].push(t);
    });

    // Sort groups by total amount (descending)
    return Object.entries(groups)
      .map(([key, transactions]) => ({
        key,
        label: getGroupLabel(key),
        transactions,
        total: transactions.reduce((sum, t) => sum + Math.abs(parseFloat(t.amount)), 0),
        count: transactions.length
      }))
      .sort((a, b) => b.total - a.total);
  }, [sortedTransactions, groupBy, accounts]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-foreground">Transactions</h1>
        <div className="flex items-center gap-3">
          <Button
            onClick={() => { resetAddForm(); setShowAddDialog(true); }}
            variant="default"
          >
            + Add Transaction
          </Button>
          <Button
            onClick={handleExport}
            disabled={exporting}
            variant="success"
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
          </Button>
          <Button
            onClick={handleReclassifyAll}
            disabled={reclassifying}
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
          </Button>
        </div>
      </div>

      {/* Success Message */}
      {reclassifySuccess && (
        <Alert className="mb-6 border-green-500 bg-green-50">
          <AlertDescription className="text-green-800 flex items-center gap-2">
            <span className="text-green-500 text-xl">✓</span>
            {reclassifySuccess}
          </AlertDescription>
        </Alert>
      )}

      {/* Filters */}
      <div className="bg-white shadow rounded-lg overflow-hidden mb-6">
        {/* Filter Header - Always visible */}
        <div
          className="px-6 py-4 bg-gradient-to-r from-gray-50 to-white border-b border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors"
          onClick={() => setFiltersExpanded(!filtersExpanded)}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center bg-indigo-100 transition-transform duration-200 ${filtersExpanded ? 'rotate-90' : ''}`}>
                <span className="text-indigo-600 text-sm font-bold">▶</span>
              </div>
              <h2 className="text-lg font-semibold text-foreground">Filters</h2>
              {activeFilters.count > 0 && (
                <Badge variant="secondary" className="bg-indigo-100 text-indigo-700">
                  {activeFilters.count} active
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-3">
              {activeFilters.count > 0 && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    resetFilters();
                    setGroupBy('none');
                  }}
                  className="text-sm text-gray-500 hover:text-red-600 transition-colors"
                >
                  Clear all
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Active Filter Chips - Show when filters are collapsed but active */}
        {!filtersExpanded && activeFilters.count > 0 && (
          <div className="px-6 py-3 bg-gray-50 border-b border-gray-100">
            <div className="flex flex-wrap gap-2">
              {activeFilters.filters.map((filter, index) => (
                <span
                  key={index}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm bg-white border border-gray-200 text-gray-700 shadow-sm"
                >
                  <span className="text-gray-500 text-xs">{filter.label}:</span>
                  <span className="font-medium">{filter.value}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      filter.clear();
                    }}
                    className="ml-1 text-gray-400 hover:text-red-500 transition-colors"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Filter Content - Collapsible */}
        {filtersExpanded && (
          <div className="p-6">
            {/* Quick Date Presets */}
            <div className="mb-6">
              <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 block">
                Quick Date Range
              </Label>
              <div className="flex flex-wrap gap-2">
                {[
                  { value: 'this_month', label: 'This Month' },
                  { value: 'last_month', label: 'Last Month' },
                  { value: 'last_3_months', label: 'Last 3 Months' },
                  { value: 'last_6_months', label: 'Last 6 Months' },
                  { value: 'this_year', label: 'This Year' },
                  { value: 'last_year', label: 'Last Year' },
                ].map((preset) => (
                  <Button
                    key={preset.value}
                    onClick={() => setDatePreset(preset.value as 'this_month' | 'last_month' | 'last_3_months' | 'last_6_months' | 'this_year' | 'last_year')}
                    variant="outline"
                    size="sm"
                    className="hover:bg-indigo-100 hover:text-indigo-700"
                  >
                    {preset.label}
                  </Button>
                ))}
              </div>
            </div>

            {/* Filter Grid */}
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {/* Date Range Section */}
              <div className="sm:col-span-2 lg:col-span-2">
                <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">
                  Date Range
                </Label>
                <div className="flex gap-3">
                  <div className="flex-1">
                    <Input
                      type="date"
                      id="start-date"
                      value={startDate}
                      onChange={(e) => {
                        setStartDate(e.target.value);
                        setPage(1);
                      }}
                      placeholder="Start date"
                    />
                  </div>
                  <div className="flex items-center text-muted-foreground">
                    <span>→</span>
                  </div>
                  <div className="flex-1">
                    <Input
                      type="date"
                      id="end-date"
                      value={endDate}
                      onChange={(e) => {
                        setEndDate(e.target.value);
                        setPage(1);
                      }}
                      placeholder="End date"
                    />
                  </div>
                </div>
              </div>

              {/* Account Filter */}
              <div>
                <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">
                  Account
                </Label>
                <Select
                  value={accountFilter || 'all'}
                  onValueChange={(val) => {
                    setAccountFilter(val === 'all' ? '' : val);
                    setPage(1);
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="All Accounts" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Accounts</SelectItem>
                    {accounts
                      .filter(a => !BROKERAGE_ACCOUNT_TYPES.includes(a.account_type))
                      .map((account) => (
                        <SelectItem key={account.id} value={account.id}>
                          {account.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Description Search */}
              <div>
                <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">
                  Search
                </Label>
                <div className="relative">
                  <Input
                    type="text"
                    id="description-filter"
                    value={descriptionFilter}
                    onChange={(e) => {
                      setDescriptionFilter(e.target.value);
                      setPage(1);
                    }}
                    placeholder="Search description..."
                    className="pl-9"
                  />
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
                    🔍
                  </span>
                </div>
              </div>

              {/* Type Filter */}
              <div>
                <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">
                  Type
                </Label>
                <Select
                  value={typeFilter || 'all'}
                  onValueChange={(val) => {
                    setTypeFilter(val === 'all' ? '' : val);
                    setCategoryFilter('');
                    setPage(1);
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="All Types" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    {TRANSACTION_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>
                        {type.charAt(0) + type.slice(1).toLowerCase()}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Category Filter */}
              <div>
                <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">
                  Category
                </Label>
                <Select
                  value={categoryFilter || 'all'}
                  onValueChange={(val) => {
                    setCategoryFilter(val === 'all' ? '' : val);
                    setPage(1);
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="All Categories" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Categories</SelectItem>
                    {getCategoriesForType(typeFilter).map((cat) => (
                      <SelectItem key={cat.id} value={cat.name}>
                        {cat.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Group By */}
              <div>
                <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">
                  Group By
                </Label>
                <Select
                  value={groupBy}
                  onValueChange={(val) => {
                    setGroupBy(val as GroupBy);
                    setCollapsedGroups(new Set());
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="No Grouping" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No Grouping</SelectItem>
                    <SelectItem value="merchant">Merchant</SelectItem>
                    <SelectItem value="category">Category</SelectItem>
                    <SelectItem value="type">Type</SelectItem>
                    <SelectItem value="account">Account</SelectItem>
                    <SelectItem value="month">Month</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Active Filters Display (when expanded) */}
            {activeFilters.count > 0 && (
              <div className="mt-5 pt-5 border-t border-gray-100">
                <div className="flex items-center justify-between">
                  <div className="flex flex-wrap gap-2">
                    {activeFilters.filters.map((filter, index) => (
                      <span
                        key={index}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm bg-indigo-50 border border-indigo-100 text-indigo-700"
                      >
                        <span className="text-indigo-400 text-xs">{filter.label}:</span>
                        <span className="font-medium">{filter.value}</span>
                        <button
                          onClick={() => filter.clear()}
                          className="ml-1 text-indigo-400 hover:text-red-500 transition-colors"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                  <button
                    onClick={() => {
                      resetFilters();
                      setGroupBy('none');
                    }}
                    className="text-sm text-gray-500 hover:text-red-600 font-medium transition-colors"
                  >
                    Clear all
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Rule Filter Indicator */}
      {matchRulePatternFilter && (
        <div className="mb-6 bg-indigo-50 border-l-4 border-indigo-500 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-indigo-600">🔍</span>
              <span className="text-indigo-700">
                Showing transactions matching rule pattern
              </span>
            </div>
            <button
              onClick={() => setMatchRulePatternFilter('')}
              className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
            >
              Clear filter
            </button>
          </div>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
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
                  <Button
                    onClick={() => setPage(page - 1)}
                    disabled={page === 1}
                    variant="outline"
                    size="sm"
                  >
                    Previous
                  </Button>
                  <Button
                    onClick={() => setPage(page + 1)}
                    disabled={page * pageSize >= total}
                    variant="outline"
                    size="sm"
                  >
                    Next
                  </Button>
                </div>
              )}
            </div>

            {/* Net Amount */}
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-600">Net Amount:</span>
                <span className={`text-lg font-bold ${calculateDisplayedTotal() >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {calculateDisplayedTotal() >= 0 ? '+' : '-'}${Math.abs(calculateDisplayedTotal()).toFixed(2)}
                </span>
              </div>
              {/* Expand/Collapse All Buttons */}
              {groupBy !== 'none' && (
                <div className="flex items-center gap-2 border-l border-gray-200 pl-4">
                  <Button
                    onClick={expandAllGroups}
                    variant="ghost"
                    size="sm"
                    className="text-indigo-600 bg-indigo-50 hover:bg-indigo-100"
                  >
                    Expand All
                  </Button>
                  <Button
                    onClick={collapseAllGroups}
                    variant="ghost"
                    size="sm"
                  >
                    Collapse All
                  </Button>
                </div>
              )}
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
        <Card className="p-12 text-center">
          <CardContent className="p-0">
            <p className="text-muted-foreground">No transactions found.</p>
            <Button asChild variant="link" className="mt-4">
              <Link href="/imports">
                Import transactions to get started
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Bulk Actions Bar */}
          {selectedIds.size > 0 && (
            <Alert className="mb-4 bg-indigo-50 border-l-4 border-indigo-500">
              {!showDeleteConfirm || deleteTarget === 'single' ? (
                <div className="flex items-center justify-between w-full">
                  <div className="flex items-center">
                    <span className="text-indigo-700 font-medium">
                      {selectedIds.size} transaction{selectedIds.size !== 1 ? 's' : ''} selected
                    </span>
                  </div>
                  <Button
                    onClick={() => handleDeleteClick()}
                    variant="destructive"
                  >
                    Delete Selected
                  </Button>
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
                    <Button
                      onClick={() => {
                        setShowDeleteConfirm(false);
                        setSingleDeleteId(null);
                      }}
                      disabled={deleting}
                      variant="outline"
                    >
                      Cancel
                    </Button>
                    <Button
                      onClick={confirmDelete}
                      disabled={deleting}
                      variant="destructive"
                    >
                      {deleting ? 'Deleting...' : `Delete ${selectedIds.size} Transaction${selectedIds.size !== 1 ? 's' : ''}`}
                    </Button>
                  </div>
                </div>
              )}
            </Alert>
          )}

          <div className="bg-white shadow rounded-lg overflow-x-auto">
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
                    className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('date')}
                  >
                    <div className="flex items-center">
                      Date{getSortIcon('date')}
                    </div>
                  </th>
                  <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Account
                  </th>
                  <th
                    className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('description')}
                  >
                    <div className="flex items-center">
                      Description{getSortIcon('description')}
                    </div>
                  </th>
                  <th
                    className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('category')}
                  >
                    <div className="flex items-center">
                      Category{getSortIcon('category')}
                    </div>
                  </th>
                  <th
                    className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('type')}
                  >
                    <div className="flex items-center">
                      Type{getSortIcon('type')}
                    </div>
                  </th>
                  <th
                    className="px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={() => handleSort('amount')}
                  >
                    <div className="flex items-center justify-end">
                      Amount{getSortIcon('amount')}
                    </div>
                  </th>
                  <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {groupedTransactions.map((group) => (
                  <React.Fragment key={group.key}>
                    {/* Group Header Row */}
                    {groupBy !== 'none' && (
                      <tr
                        className="bg-gradient-to-r from-indigo-50 to-purple-50 cursor-pointer hover:from-indigo-100 hover:to-purple-100 transition-all duration-200 border-l-4 border-indigo-500"
                        onClick={() => toggleGroup(group.key)}
                      >
                        <td colSpan={8} className="px-6 py-4">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-4">
                              <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-transform duration-200 ${collapsedGroups.has(group.key) ? '' : 'rotate-90'} bg-indigo-100`}>
                                <span className="text-indigo-600 text-sm font-bold">▶</span>
                              </div>
                              <div>
                                <span className="font-bold text-gray-900 text-lg">
                                  {group.label}
                                </span>
                                <div className="flex items-center gap-2 mt-0.5">
                                  <span className="text-xs text-gray-500 bg-white/80 px-2 py-0.5 rounded-full border border-gray-200">
                                    {group.count} transaction{group.count !== 1 ? 's' : ''}
                                  </span>
                                </div>
                              </div>
                            </div>
                            <div className="text-right">
                              <span className="font-bold text-xl text-gray-900">
                                ${group.total.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                              </span>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                    {/* Transaction Rows */}
                    {!collapsedGroups.has(group.key) && group.transactions.map((transaction) => (
                  <tr key={transaction.id} className={`hover:bg-gray-50 transition-colors ${groupBy !== 'none' ? 'bg-white' : ''}`}>
                    <td className={`px-4 py-4 ${groupBy !== 'none' ? 'pl-6' : ''}`}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(transaction.id)}
                        onChange={() => toggleSelectTransaction(transaction.id)}
                        className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded cursor-pointer"
                      />
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-900">
                      <span title={formatDateDisplay(transaction.date)}>
                        {new Date(transaction.date + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                      </span>
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-500">
                      <div className="max-w-[90px] truncate" title={accounts.find(a => a.id === transaction.account_id)?.name || transaction.account_id}>
                        {accounts.find(a => a.id === transaction.account_id)?.name || '-'}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-sm text-gray-900">
                      <div className="max-w-[200px]">
                        <div className="truncate" title={transaction.description_raw}>
                          {transaction.merchant_normalized || transaction.description_raw}
                        </div>
                        {transaction.merchant_normalized && transaction.description_raw && transaction.merchant_normalized !== transaction.description_raw && (
                          <div className="mt-0.5 text-xs text-gray-400 truncate" title={transaction.description_raw}>
                            {transaction.description_raw}
                          </div>
                        )}
                        {editingNoteId === transaction.id ? (
                          <input
                            type="text"
                            autoFocus
                            disabled={savingNote}
                            value={noteValue}
                            onChange={(e) => setNoteValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                handleNoteUpdate(transaction.id);
                              } else if (e.key === 'Escape') {
                                cancelEditingNote();
                              }
                            }}
                            onBlur={() => handleNoteUpdate(transaction.id)}
                            placeholder="Add note..."
                            className="mt-1 w-full px-2 py-1 border border-indigo-500 rounded focus:outline-none focus:ring-2 focus:ring-indigo-500 text-xs"
                          />
                        ) : transaction.user_note ? (
                          <div
                            className="mt-1 text-xs text-gray-500 truncate cursor-pointer hover:text-indigo-600"
                            title={transaction.user_note}
                            onClick={() => startEditingNote(transaction)}
                          >
                            {transaction.user_note}
                          </div>
                        ) : null}
                      </div>
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-900">
                      {editingCategoryId === transaction.id ? (
                        <select
                          key={`category-${transaction.id}-${transaction.transaction_type}`}
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
                          className="focus:outline-none group"
                          title="Click to change category"
                        >
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${getCategoryColor(transaction.category)} group-hover:ring-2 group-hover:ring-indigo-300 transition-all`}>
                            {transaction.category || 'Uncategorized'}
                            {transaction.classification_method === 'LEARNED' && (
                              <span className="ml-1 text-green-600" title="Learned from your edits">✓</span>
                            )}
                          </span>
                        </button>
                      )}
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap">
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
                          <span className={`px-1.5 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full ${getTransactionTypeColor(transaction.transaction_type)} hover:ring-2 hover:ring-indigo-300 cursor-pointer transition-all`}>
                            {transaction.transaction_type.charAt(0) + transaction.transaction_type.slice(1).toLowerCase()}
                          </span>
                        </button>
                      )}
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap text-right">
                      <span className={`font-semibold text-sm ${
                        transaction.is_spend
                          ? 'text-red-600'
                          : transaction.is_income
                            ? 'text-emerald-600'
                            : 'text-gray-700'
                      }`}>
                        {transaction.is_income ? '+' : transaction.is_spend ? '-' : ''}
                        ${Math.abs(parseFloat(transaction.amount)).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap text-center">
                      <div className="flex items-center justify-center gap-2">
                        <button
                          onClick={() => startEditingNote(transaction)}
                          className={`text-sm ${transaction.user_note ? 'text-indigo-600' : 'text-gray-400'} hover:text-indigo-800`}
                          title={transaction.user_note || 'Add note'}
                        >
                          📝
                        </button>
                        <button
                          onClick={() => handleDeleteClick(transaction.id)}
                          className="text-sm text-gray-400 hover:text-red-600"
                          title="Delete transaction"
                        >
                          🗑️
                        </button>
                      </div>
                    </td>
                  </tr>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>

        </>
      )}

      {/* Delete Confirmation Modal (for single transaction delete only) */}
      <Dialog
        open={showDeleteConfirm && deleteTarget === 'single'}
        onOpenChange={(open) => {
          if (!open && !deleting) {
            setShowDeleteConfirm(false);
            setSingleDeleteId(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Delete</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this transaction? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              onClick={() => {
                setShowDeleteConfirm(false);
                setSingleDeleteId(null);
              }}
              disabled={deleting}
              variant="outline"
            >
              Cancel
            </Button>
            <Button
              onClick={confirmDelete}
              disabled={deleting}
              variant="destructive"
            >
              {deleting ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Apply Merchant Category Prompt Modal */}
      <Dialog
        open={showApplyMerchantPrompt && applyMerchantData !== null}
        onOpenChange={(open) => {
          if (!open && !applyingMerchant) {
            closeApplyMerchantPrompt();
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Apply to Other Transactions?</DialogTitle>
            <DialogDescription>
              {applyMerchantData && (
                <>
                  Found <span className="font-semibold">{applyMerchantData.otherCount}</span> other transaction{applyMerchantData.otherCount !== 1 ? 's' : ''} from{' '}
                  <span className="font-semibold">{applyMerchantData.merchant}</span>.
                  Would you like to apply <span className="font-semibold">"{applyMerchantData.category}"</span> to all of them?
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              onClick={closeApplyMerchantPrompt}
              disabled={applyingMerchant}
              variant="outline"
            >
              Skip
            </Button>
            <Button
              onClick={handleApplyMerchantCategory}
              disabled={applyingMerchant}
            >
              {applyingMerchant ? 'Applying...' : `Apply to ${applyMerchantData?.otherCount || 0} Transaction${(applyMerchantData?.otherCount || 0) !== 1 ? 's' : ''}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Transaction Dialog */}
      <Dialog
        open={showAddDialog}
        onOpenChange={(open) => {
          if (!open && !addingTransaction) {
            setShowAddDialog(false);
            resetAddForm();
          }
        }}
      >
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Add Transaction</DialogTitle>
            <DialogDescription>
              Manually add a new transaction to your records.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleAddTransaction}>
            <div className="grid gap-4 py-4">
              {addError && (
                <Alert variant="destructive">
                  <AlertDescription>{addError}</AlertDescription>
                </Alert>
              )}

              {/* Date */}
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="add-date" className="text-right">Date *</Label>
                <Input
                  id="add-date"
                  type="date"
                  value={addForm.date}
                  onChange={(e) => setAddForm({ ...addForm, date: e.target.value })}
                  className="col-span-3"
                  required
                />
              </div>

              {/* Description */}
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="add-desc" className="text-right">Description *</Label>
                <Input
                  id="add-desc"
                  value={addForm.description_raw}
                  onChange={(e) => setAddForm({ ...addForm, description_raw: e.target.value })}
                  placeholder="e.g. Coffee at Blue Bottle"
                  className="col-span-3"
                  required
                />
              </div>

              {/* Amount */}
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="add-amount" className="text-right">Amount *</Label>
                <Input
                  id="add-amount"
                  type="number"
                  step="0.01"
                  min="0"
                  value={addForm.amount}
                  onChange={(e) => setAddForm({ ...addForm, amount: e.target.value })}
                  placeholder="0.00"
                  className="col-span-3"
                  required
                />
              </div>

              {/* Account */}
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="add-account" className="text-right">Account *</Label>
                <Select
                  value={addForm.account_id}
                  onValueChange={(val) => setAddForm({ ...addForm, account_id: val })}
                >
                  <SelectTrigger className="col-span-3">
                    <SelectValue placeholder="Select account" />
                  </SelectTrigger>
                  <SelectContent>
                    {accounts
                      .filter(a => !BROKERAGE_ACCOUNT_TYPES.includes(a.account_type))
                      .map((account) => (
                        <SelectItem key={account.id} value={account.id}>
                          {account.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Type */}
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="add-type" className="text-right">Type *</Label>
                <Select
                  value={addForm.transaction_type}
                  onValueChange={(val) => setAddForm({ ...addForm, transaction_type: val, category: '' })}
                >
                  <SelectTrigger className="col-span-3">
                    <SelectValue placeholder="Select type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="EXPENSE">Expense</SelectItem>
                    <SelectItem value="INCOME">Income</SelectItem>
                    <SelectItem value="TRANSFER">Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Category (optional) */}
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="add-category" className="text-right">Category</Label>
                <Select
                  value={addForm.category || 'none'}
                  onValueChange={(val) => setAddForm({ ...addForm, category: val === 'none' ? '' : val })}
                >
                  <SelectTrigger className="col-span-3">
                    <SelectValue placeholder="Optional" />
                  </SelectTrigger>
                  <SelectContent className="max-h-60">
                    <SelectItem value="none">None</SelectItem>
                    {getCategoriesForType(addForm.transaction_type).map((cat) => (
                      <SelectItem key={cat.id} value={cat.name}>
                        {cat.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Merchant (optional) */}
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="add-merchant" className="text-right">Merchant</Label>
                <Input
                  id="add-merchant"
                  value={addForm.merchant_normalized}
                  onChange={(e) => setAddForm({ ...addForm, merchant_normalized: e.target.value })}
                  placeholder="Optional"
                  className="col-span-3"
                />
              </div>

              {/* Note (optional) */}
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="add-note" className="text-right">Note</Label>
                <Input
                  id="add-note"
                  value={addForm.user_note}
                  onChange={(e) => setAddForm({ ...addForm, user_note: e.target.value })}
                  placeholder="Optional"
                  className="col-span-3"
                />
              </div>

              {/* Currency (optional) */}
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="add-currency" className="text-right">Currency</Label>
                <Input
                  id="add-currency"
                  value={addForm.currency}
                  onChange={(e) => setAddForm({ ...addForm, currency: e.target.value.toUpperCase() })}
                  placeholder="USD"
                  maxLength={3}
                  className="col-span-3"
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => { setShowAddDialog(false); resetAddForm(); }}
                disabled={addingTransaction}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={addingTransaction}>
                {addingTransaction ? 'Adding...' : 'Add Transaction'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
