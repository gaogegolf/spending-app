'use client';

import { useState, useEffect } from 'react';
import {
  getRecurringTransactions,
  detectRecurringTransactions,
  getRecurringCandidates,
  acceptRecurringCandidate,
  createRecurringTransaction,
  updateRecurringTransaction,
  deleteRecurringTransaction,
  getUpcomingRecurring,
  getRecurringSummary,
} from '@/lib/api';
import {
  RecurringTransaction,
  RecurringCandidate,
  UpcomingRecurring,
  RecurringSummary,
  RecurringFrequency,
} from '@/lib/types';

const FREQUENCY_LABELS: Record<RecurringFrequency, string> = {
  WEEKLY: 'Weekly',
  BIWEEKLY: 'Bi-weekly',
  MONTHLY: 'Monthly',
  QUARTERLY: 'Quarterly',
  YEARLY: 'Yearly',
};

export default function SubscriptionsPage() {
  // State
  const [recurring, setRecurring] = useState<RecurringTransaction[]>([]);
  const [candidates, setCandidates] = useState<RecurringCandidate[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingRecurring[]>([]);
  const [summary, setSummary] = useState<RecurringSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'subscriptions' | 'candidates' | 'upcoming'>('subscriptions');

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingRecurring, setEditingRecurring] = useState<RecurringTransaction | null>(null);

  // Form state
  const [formMerchant, setFormMerchant] = useState('');
  const [formAmount, setFormAmount] = useState('');
  const [formFrequency, setFormFrequency] = useState<RecurringFrequency>('MONTHLY');
  const [formCategory, setFormCategory] = useState('');
  const [formNotes, setFormNotes] = useState('');
  const [formNextDate, setFormNextDate] = useState('');

  // Load data on mount
  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);

      const [recurringData, candidatesData, upcomingData, summaryData] = await Promise.all([
        getRecurringTransactions({ is_active: true }),
        getRecurringCandidates(),
        getUpcomingRecurring(30),
        getRecurringSummary(),
      ]);

      setRecurring(recurringData.recurring_transactions || []);
      setCandidates(candidatesData.candidates || []);
      setUpcoming(upcomingData.upcoming || []);
      setSummary(summaryData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  async function handleDetect() {
    try {
      setDetecting(true);
      setError(null);
      await detectRecurringTransactions({ min_transactions: 3, min_confidence: 0.6 });
      // Reload candidates after detection
      const candidatesData = await getRecurringCandidates();
      setCandidates(candidatesData.candidates || []);
      setActiveTab('candidates');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to detect recurring transactions');
    } finally {
      setDetecting(false);
    }
  }

  async function handleAcceptCandidate(candidate: RecurringCandidate) {
    try {
      setError(null);
      await acceptRecurringCandidate(candidate.merchant_normalized, formCategory || undefined);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to accept candidate');
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    try {
      setError(null);
      const data = {
        merchant_normalized: formMerchant,
        expected_amount: parseFloat(formAmount),
        frequency: formFrequency,
        category: formCategory || undefined,
        notes: formNotes || undefined,
        next_expected_date: formNextDate || undefined,
      };

      if (editingRecurring) {
        await updateRecurringTransaction(editingRecurring.id, data);
      } else {
        await createRecurringTransaction(data);
      }

      await loadData();
      closeModal();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Are you sure you want to delete this subscription?')) return;

    try {
      setError(null);
      await deleteRecurringTransaction(id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete');
    }
  }

  async function handleToggleActive(recurring: RecurringTransaction) {
    try {
      setError(null);
      await updateRecurringTransaction(recurring.id, { is_active: !recurring.is_active });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update');
    }
  }

  function openCreateModal() {
    setEditingRecurring(null);
    setFormMerchant('');
    setFormAmount('');
    setFormFrequency('MONTHLY');
    setFormCategory('');
    setFormNotes('');
    setFormNextDate('');
    setShowModal(true);
  }

  function openEditModal(recurring: RecurringTransaction) {
    setEditingRecurring(recurring);
    setFormMerchant(recurring.merchant_normalized);
    setFormAmount(recurring.expected_amount);
    setFormFrequency(recurring.frequency);
    setFormCategory(recurring.category || '');
    setFormNotes(recurring.notes || '');
    setFormNextDate(recurring.next_expected_date || '');
    setShowModal(true);
  }

  function closeModal() {
    setShowModal(false);
    setEditingRecurring(null);
  }

  function formatCurrency(amount: string | number): string {
    const num = typeof amount === 'string' ? parseFloat(amount) : amount;
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(num);
  }

  function formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
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
        <h1 className="text-2xl font-bold text-gray-900">Subscriptions</h1>
        <div className="flex gap-3">
          <button
            onClick={handleDetect}
            disabled={detecting}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2"
          >
            {detecting ? (
              <>
                <span className="animate-spin">&#x21bb;</span>
                Detecting...
              </>
            ) : (
              <>Auto-Detect</>
            )}
          </button>
          <button
            onClick={openCreateModal}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
          >
            + Add Subscription
          </button>
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-lg border p-4">
            <div className="text-sm text-gray-500">Active Subscriptions</div>
            <div className="text-2xl font-bold text-gray-900">{summary.total_active}</div>
          </div>
          <div className="bg-white rounded-lg border p-4">
            <div className="text-sm text-gray-500">Monthly Cost</div>
            <div className="text-2xl font-bold text-red-600">{formatCurrency(summary.total_monthly_cost)}</div>
          </div>
          <div className="bg-white rounded-lg border p-4">
            <div className="text-sm text-gray-500">Yearly Cost</div>
            <div className="text-2xl font-bold text-red-600">{formatCurrency(summary.total_yearly_cost)}</div>
          </div>
          <div className="bg-white rounded-lg border p-4">
            <div className="text-sm text-gray-500">Pending Candidates</div>
            <div className="text-2xl font-bold text-purple-600">{candidates.length}</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('subscriptions')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'subscriptions'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Subscriptions ({recurring.length})
          </button>
          <button
            onClick={() => setActiveTab('candidates')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'candidates'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Detected Candidates ({candidates.length})
          </button>
          <button
            onClick={() => setActiveTab('upcoming')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'upcoming'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Upcoming ({upcoming.length})
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'subscriptions' && (
        <div className="bg-white rounded-lg border overflow-x-auto">
          {recurring.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>No subscriptions tracked yet.</p>
              <p className="text-sm mt-2">Use "Auto-Detect" to find recurring payments or add one manually.</p>
            </div>
          ) : (
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Merchant</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Amount</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Frequency</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Category</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Next Due</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {recurring.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="font-medium text-gray-900">{r.merchant_normalized}</div>
                      {r.is_auto_detected && (
                        <span className="text-xs text-purple-600">Auto-detected</span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-900">
                      {formatCurrency(r.expected_amount)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-600">
                      {FREQUENCY_LABELS[r.frequency]}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-600">
                      {r.category || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-600">
                      {r.next_expected_date ? formatDate(r.next_expected_date) : '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <button
                        onClick={() => handleToggleActive(r)}
                        className={`px-2 py-1 rounded text-xs font-medium ${
                          r.is_active
                            ? 'bg-green-100 text-green-800'
                            : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {r.is_active ? 'Active' : 'Paused'}
                      </button>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right space-x-2">
                      <button
                        onClick={() => openEditModal(r)}
                        className="text-indigo-600 hover:text-indigo-900"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(r.id)}
                        className="text-red-600 hover:text-red-900"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {activeTab === 'candidates' && (
        <div className="bg-white rounded-lg border overflow-x-auto">
          {candidates.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>No pending candidates found.</p>
              <p className="text-sm mt-2">Click "Auto-Detect" to analyze your transactions for recurring patterns.</p>
            </div>
          ) : (
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Merchant</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Amount</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Frequency</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Confidence</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Transactions</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date Range</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Action</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {candidates.map((c) => (
                  <tr key={c.merchant_normalized} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap font-medium text-gray-900">
                      {c.merchant_normalized}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-900">
                      {formatCurrency(c.expected_amount)}
                      <span className="text-xs text-gray-500 ml-1">
                        (±{parseFloat(c.amount_variance).toFixed(1)}%)
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-600">
                      {FREQUENCY_LABELS[c.frequency]}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <div className="w-16 bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-green-500 h-2 rounded-full"
                            style={{ width: `${parseFloat(c.confidence) * 100}%` }}
                          />
                        </div>
                        <span className="text-sm text-gray-600">
                          {(parseFloat(c.confidence) * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-600">
                      {c.transaction_count} txns
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-600 text-sm">
                      {formatDate(c.first_date)} - {formatDate(c.last_date)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right">
                      <button
                        onClick={() => handleAcceptCandidate(c)}
                        className="px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700"
                      >
                        Accept
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {activeTab === 'upcoming' && (
        <div className="bg-white rounded-lg border overflow-x-auto">
          {upcoming.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p>No upcoming payments in the next 30 days.</p>
            </div>
          ) : (
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Merchant</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Amount</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Due Date</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Days Until</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Category</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {upcoming.map((u) => (
                  <tr key={u.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap font-medium text-gray-900">
                      {u.merchant_normalized}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-900">
                      {formatCurrency(u.expected_amount)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-600">
                      {formatDate(u.next_expected_date)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2 py-1 rounded text-sm ${
                          u.days_until <= 3
                            ? 'bg-red-100 text-red-800'
                            : u.days_until <= 7
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {u.days_until === 0 ? 'Today' : u.days_until === 1 ? 'Tomorrow' : `${u.days_until} days`}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-600">
                      {u.category || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h2 className="text-xl font-bold mb-4">
              {editingRecurring ? 'Edit Subscription' : 'Add Subscription'}
            </h2>
            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Merchant Name
                </label>
                <input
                  type="text"
                  value={formMerchant}
                  onChange={(e) => setFormMerchant(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Amount
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formAmount}
                  onChange={(e) => setFormAmount(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Frequency
                </label>
                <select
                  value={formFrequency}
                  onChange={(e) => setFormFrequency(e.target.value as RecurringFrequency)}
                  className="w-full border rounded-lg px-3 py-2"
                >
                  {Object.entries(FREQUENCY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Category
                </label>
                <input
                  type="text"
                  value={formCategory}
                  onChange={(e) => setFormCategory(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2"
                  placeholder="e.g., Entertainment, Utilities"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Next Expected Date
                </label>
                <input
                  type="date"
                  value={formNextDate}
                  onChange={(e) => setFormNextDate(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Notes
                </label>
                <textarea
                  value={formNotes}
                  onChange={(e) => setFormNotes(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={2}
                />
              </div>
              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
                >
                  {editingRecurring ? 'Update' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
