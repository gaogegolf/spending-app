'use client';

import { useEffect, useState } from 'react';
import { getTransactions, getAccounts, updateTransaction } from '@/lib/api';
import { Transaction, Account, TransactionListResponse } from '@/lib/types';

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [accountFilter, setAccountFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [needsReviewFilter, setNeedsReviewFilter] = useState<boolean | undefined>(undefined);

  useEffect(() => {
    loadAccounts();
  }, []);

  useEffect(() => {
    loadTransactions();
  }, [page, accountFilter, typeFilter, categoryFilter, needsReviewFilter]);

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
        needs_review: needsReviewFilter,
        page,
        page_size: 50,
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
    setNeedsReviewFilter(undefined);
    setPage(1);
  }

  function getTransactionTypeColor(type: string): string {
    switch (type) {
      case 'EXPENSE':
        return 'bg-red-100 text-red-800';
      case 'INCOME':
        return 'bg-green-100 text-green-800';
      case 'PAYMENT':
        return 'bg-blue-100 text-blue-800';
      case 'REFUND':
        return 'bg-purple-100 text-purple-800';
      case 'TRANSFER':
        return 'bg-gray-100 text-gray-800';
      case 'FEE_INTEREST':
        return 'bg-orange-100 text-orange-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Transactions</h1>

      {/* Filters */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Filters</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
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
                setPage(1);
              }}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            >
              <option value="">All Types</option>
              <option value="EXPENSE">Expense</option>
              <option value="INCOME">Income</option>
              <option value="PAYMENT">Payment</option>
              <option value="REFUND">Refund</option>
              <option value="TRANSFER">Transfer</option>
              <option value="FEE_INTEREST">Fee/Interest</option>
            </select>
          </div>

          {/* Category Filter */}
          <div>
            <label htmlFor="category-filter" className="block text-sm font-medium text-gray-700 mb-1">
              Category
            </label>
            <input
              type="text"
              id="category-filter"
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(1);
              }}
              placeholder="Enter category..."
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

        <div className="mt-4">
          <button
            onClick={resetFilters}
            className="text-sm text-indigo-600 hover:text-indigo-800"
          >
            Reset Filters
          </button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
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
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Date
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Description
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Category
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Amount
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Review
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {transactions.map((transaction) => (
                  <tr key={transaction.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {new Date(transaction.date).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      <div className="max-w-xs truncate" title={transaction.description_raw}>
                        {transaction.merchant_normalized || transaction.description_raw}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {transaction.category || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${getTransactionTypeColor(transaction.transaction_type)}`}>
                        {transaction.transaction_type}
                      </span>
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="bg-white px-4 py-3 border-t border-gray-200 sm:px-6 mt-4 rounded-lg shadow">
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-700">
                Showing <span className="font-medium">{(page - 1) * 50 + 1}</span> to{' '}
                <span className="font-medium">{Math.min(page * 50, total)}</span> of{' '}
                <span className="font-medium">{total}</span> results
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(page - 1)}
                  disabled={page === 1}
                  className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:bg-gray-100 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={page * 50 >= total}
                  className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:bg-gray-100 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
