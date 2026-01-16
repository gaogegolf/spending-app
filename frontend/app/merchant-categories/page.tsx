'use client';

import { useEffect, useState } from 'react';
import { getMerchantCategories, updateMerchantCategory, deleteMerchantCategory, bulkDeleteMerchantCategories, refreshMerchantCounts } from '@/lib/api';
import { MerchantCategory, MerchantCategoryListResponse } from '@/lib/types';

// Empower-style categories (same as transactions page)
const CATEGORIES = [
  'Restaurants',
  'Groceries',
  'Gasoline/Fuel',
  'Automotive',
  'Shopping',
  'Clothes',
  'Entertainment',
  'Travel',
  'Bills & Utilities',
  'Health & Fitness',
  'Personal Care',
  'Education',
  'Gifts & Donations',
  'Home',
  'Taxes',
  'Fees & Charges',
  'Coffee Shops',
  'Fast Food',
  'Alcohol & Bars',
  'Pharmacy',
  'Pet Care',
  'Electronics',
  'Books',
  'Office Supplies',
  'Subscriptions',
  'Insurance',
  'Other Expenses',
];

export default function MerchantCategoriesPage() {
  const [merchantCategories, setMerchantCategories] = useState<MerchantCategory[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Category editing state
  const [editingCategoryId, setEditingCategoryId] = useState<string | null>(null);
  const [savingCategory, setSavingCategory] = useState(false);

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<'single' | 'bulk'>('bulk');
  const [singleDeleteId, setSingleDeleteId] = useState<string | null>(null);

  // Filters
  const [merchantSearch, setMerchantSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');

  // Refresh counts state
  const [refreshingCounts, setRefreshingCounts] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Debounce search
  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(merchantSearch);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [merchantSearch]);

  useEffect(() => {
    loadMerchantCategories();
  }, [page, pageSize, debouncedSearch, sourceFilter, categoryFilter]);

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

  async function loadMerchantCategories() {
    try {
      setLoading(true);
      setError(null);

      const data: MerchantCategoryListResponse = await getMerchantCategories({
        merchant_search: debouncedSearch || undefined,
        source: sourceFilter || undefined,
        category: categoryFilter || undefined,
        page,
        page_size: pageSize,
      });

      setMerchantCategories(data.merchant_categories || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load merchant categories');
    } finally {
      setLoading(false);
    }
  }

  function resetFilters() {
    setMerchantSearch('');
    setSourceFilter('');
    setCategoryFilter('');
    setPage(1);
  }

  function toggleSelectAll() {
    if (selectedIds.size === merchantCategories.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(merchantCategories.map(mc => mc.id)));
    }
  }

  function toggleSelectMerchant(id: string) {
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
        await deleteMerchantCategory(singleDeleteId);
      } else if (deleteTarget === 'bulk') {
        await bulkDeleteMerchantCategories(Array.from(selectedIds));
      }

      setSelectedIds(new Set());
      setShowDeleteConfirm(false);
      setSingleDeleteId(null);
      await loadMerchantCategories();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete merchant categories');
    } finally {
      setDeleting(false);
    }
  }

  async function handleCategoryChange(mappingId: string, newCategory: string) {
    try {
      setSavingCategory(true);
      setError(null);

      await updateMerchantCategory(mappingId, { category: newCategory });

      setMerchantCategories(merchantCategories.map(mc =>
        mc.id === mappingId ? { ...mc, category: newCategory, source: 'USER' } : mc
      ));

      setEditingCategoryId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update category');
    } finally {
      setSavingCategory(false);
    }
  }

  async function handleRefreshCounts() {
    try {
      setRefreshingCounts(true);
      setError(null);
      const result = await refreshMerchantCounts();
      await loadMerchantCategories();
      if (result.updated_merchants > 0) {
        setSuccessMessage(`Updated counts for ${result.updated_merchants} merchants`);
      } else {
        setSuccessMessage('All counts are up to date');
      }
      // Clear success message after 3 seconds
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh counts');
    } finally {
      setRefreshingCounts(false);
    }
  }

  function getSourceColor(source: string): string {
    switch (source) {
      case 'USER':
        return 'bg-green-100 text-green-800';
      case 'AUTO':
        return 'bg-blue-100 text-blue-800';
      case 'LLM':
        return 'bg-purple-100 text-purple-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  }

  function formatDate(dateString: string): string {
    return new Date(dateString).toLocaleDateString();
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Merchant Categories</h1>
          <p className="mt-2 text-gray-600">
            These are learned category mappings. When you manually categorize a transaction,
            the merchant is remembered for future auto-categorization.
          </p>
        </div>
        <button
          onClick={handleRefreshCounts}
          disabled={refreshingCounts}
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm flex items-center gap-2"
          title="Recalculate times applied based on current transactions"
        >
          {refreshingCounts ? (
            <>
              <span className="animate-spin">⟳</span>
              Refreshing...
            </>
          ) : (
            <>
              <span>🔄</span>
              Refresh Counts
            </>
          )}
        </button>
      </div>

      {/* Success Message */}
      {successMessage && (
        <div className="mb-6 bg-green-50 border-l-4 border-green-500 rounded-lg p-4">
          <div className="flex items-center">
            <span className="text-green-500 mr-2">✓</span>
            <p className="text-green-800">{successMessage}</p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Filters</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* Merchant Search */}
          <div>
            <label htmlFor="merchant-search" className="block text-sm font-medium text-gray-700 mb-1">
              Search Merchant
            </label>
            <input
              type="text"
              id="merchant-search"
              value={merchantSearch}
              onChange={(e) => setMerchantSearch(e.target.value)}
              placeholder="Type to search..."
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            />
          </div>

          {/* Source Filter */}
          <div>
            <label htmlFor="source-filter" className="block text-sm font-medium text-gray-700 mb-1">
              Source
            </label>
            <select
              id="source-filter"
              value={sourceFilter}
              onChange={(e) => {
                setSourceFilter(e.target.value);
                setPage(1);
              }}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
            >
              <option value="">All Sources</option>
              <option value="USER">User (Manual)</option>
              <option value="AUTO">Auto-learned</option>
              <option value="LLM">AI Classified</option>
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
              {CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-4">
          <button
            onClick={resetFilters}
            className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
          >
            Reset All Filters
          </button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="bg-white shadow rounded-lg p-12">
          <div className="text-center">
            <p className="text-gray-500">Loading merchant categories...</p>
          </div>
        </div>
      ) : merchantCategories.length === 0 ? (
        <div className="bg-white shadow rounded-lg p-12">
          <div className="text-center">
            <p className="text-gray-500 mb-2">No merchant categories found.</p>
            <p className="text-gray-400 text-sm">
              Categories are automatically learned when you manually categorize transactions.
            </p>
          </div>
        </div>
      ) : (
        <>
          {/* Bulk Actions Bar */}
          {selectedIds.size > 0 && (
            <div className="bg-indigo-50 border-l-4 border-indigo-500 rounded-lg p-4 mb-4">
              {!showDeleteConfirm || deleteTarget === 'single' ? (
                <div className="flex items-center justify-between">
                  <span className="text-indigo-700 font-medium">
                    {selectedIds.size} mapping{selectedIds.size !== 1 ? 's' : ''} selected
                  </span>
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
                        Are you sure you want to delete {selectedIds.size} merchant mapping{selectedIds.size !== 1 ? 's' : ''}?
                        Future transactions from these merchants will no longer be auto-categorized.
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
                      {deleting ? 'Deleting...' : `Delete ${selectedIds.size} Mapping${selectedIds.size !== 1 ? 's' : ''}`}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="bg-white shadow rounded-lg overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left">
                    <input
                      type="checkbox"
                      checked={selectedIds.size === merchantCategories.length && merchantCategories.length > 0}
                      onChange={toggleSelectAll}
                      className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded cursor-pointer"
                    />
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Merchant
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Category
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Source
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Times Applied
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Last Updated
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {merchantCategories.map((mc) => (
                  <tr key={mc.id} className="hover:bg-gray-50">
                    <td className="px-4 py-4">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(mc.id)}
                        onChange={() => toggleSelectMerchant(mc.id)}
                        className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded cursor-pointer"
                      />
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      <div className="max-w-xs truncate font-medium" title={mc.merchant_normalized}>
                        {mc.merchant_normalized}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {editingCategoryId === mc.id ? (
                        <select
                          autoFocus
                          disabled={savingCategory}
                          defaultValue={mc.category}
                          onChange={(e) => handleCategoryChange(mc.id, e.target.value)}
                          onBlur={() => setEditingCategoryId(null)}
                          className="w-full px-2 py-1 border border-indigo-500 rounded focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
                        >
                          {CATEGORIES.map((cat) => (
                            <option key={cat} value={cat}>
                              {cat}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <button
                          onClick={() => setEditingCategoryId(mc.id)}
                          className="text-left hover:text-indigo-600 hover:underline focus:outline-none focus:text-indigo-600"
                          title="Click to change category"
                        >
                          {mc.category}
                        </button>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${getSourceColor(mc.source)}`}>
                        {mc.source}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-center">
                      {mc.times_applied}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {formatDate(mc.updated_at)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-center">
                      <button
                        onClick={() => handleDeleteClick(mc.id)}
                        className="text-red-600 hover:text-red-800 text-sm font-medium"
                        title="Delete mapping"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="bg-white px-4 py-3 border-t border-gray-200 sm:px-6 mt-4 rounded-lg shadow">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="text-sm text-gray-700">
                  Showing <span className="font-medium">{(page - 1) * pageSize + 1}</span> to{' '}
                  <span className="font-medium">{Math.min(page * pageSize, total)}</span> of{' '}
                  <span className="font-medium">{total}</span> results
                </div>

                <div className="flex items-center gap-2">
                  <label htmlFor="page-size" className="text-sm text-gray-700">
                    Show:
                  </label>
                  <select
                    id="page-size"
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(parseInt(e.target.value));
                      setPage(1);
                      setSelectedIds(new Set());
                    }}
                    className="px-2 py-1 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  >
                    <option value="50">50</option>
                    <option value="100">100</option>
                    <option value="200">200</option>
                    <option value="500">500</option>
                  </select>
                </div>
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
                  disabled={page * pageSize >= total}
                  className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:bg-gray-100 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Delete Confirmation Modal (for single delete) */}
      {showDeleteConfirm && deleteTarget === 'single' && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget && !deleting) {
              setShowDeleteConfirm(false);
              setSingleDeleteId(null);
            }
          }}
        >
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Confirm Delete</h3>
            <p className="text-gray-600 mb-6">
              Are you sure you want to delete this merchant category mapping?
              Future transactions from this merchant will no longer be auto-categorized.
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
