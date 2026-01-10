'use client';

import { useState, useEffect } from 'react';
import { getAccounts, createAccount, updateAccount, deleteAccount } from '@/lib/api';
import { Account, AccountType } from '@/lib/types';

const ACCOUNT_TYPES: AccountType[] = ['CREDIT_CARD', 'CHECKING', 'SAVINGS', 'INVESTMENT', 'OTHER'];

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const [formName, setFormName] = useState('');
  const [formType, setFormType] = useState<AccountType>('CREDIT_CARD');
  const [formInstitution, setFormInstitution] = useState('');
  const [formLast4, setFormLast4] = useState('');

  // Delete confirmation
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [accountToDelete, setAccountToDelete] = useState<Account | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadAccounts();
  }, []);

  async function loadAccounts() {
    try {
      setLoading(true);
      setError(null);
      const data = await getAccounts();
      setAccounts(data.accounts || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load accounts');
    } finally {
      setLoading(false);
    }
  }

  function openCreateModal() {
    setEditingAccount(null);
    setFormName('');
    setFormType('CREDIT_CARD');
    setFormInstitution('');
    setFormLast4('');
    setShowModal(true);
  }

  function openEditModal(account: Account) {
    setEditingAccount(account);
    setFormName(account.name);
    setFormType(account.account_type);
    setFormInstitution(account.institution || '');
    setFormLast4(account.account_number_last4 || '');
    setShowModal(true);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();

    if (!formName.trim()) {
      setError('Account name is required');
      return;
    }

    try {
      setSaving(true);
      setError(null);

      if (editingAccount) {
        // Update existing account
        const updated = await updateAccount(editingAccount.id, {
          name: formName.trim(),
          institution: formInstitution.trim() || undefined,
          account_number_last4: formLast4.trim() || undefined,
        });
        setAccounts(accounts.map(a => a.id === updated.id ? updated : a));
      } else {
        // Create new account
        const created = await createAccount({
          name: formName.trim(),
          account_type: formType,
          institution: formInstitution.trim() || undefined,
          account_number_last4: formLast4.trim() || undefined,
        });
        setAccounts([...accounts, created]);
      }

      setShowModal(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save account');
    } finally {
      setSaving(false);
    }
  }

  function confirmDelete(account: Account) {
    setAccountToDelete(account);
    setShowDeleteConfirm(true);
  }

  async function handleDelete() {
    if (!accountToDelete) return;

    try {
      setDeleting(true);
      setError(null);
      await deleteAccount(accountToDelete.id);
      setAccounts(accounts.filter(a => a.id !== accountToDelete.id));
      setShowDeleteConfirm(false);
      setAccountToDelete(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete account');
    } finally {
      setDeleting(false);
    }
  }

  function formatAccountType(type: string): string {
    return type.replace('_', ' ');
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Accounts</h1>
        <button
          onClick={openCreateModal}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-medium text-sm flex items-center gap-2"
        >
          <span>+</span>
          Add Account
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
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-indigo-200 border-t-indigo-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading accounts...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && accounts.length === 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
          <div className="text-6xl mb-4">🏦</div>
          <h3 className="text-xl font-semibold text-gray-900 mb-2">No accounts yet</h3>
          <p className="text-gray-600 mb-6">Create your first account to start importing transactions.</p>
          <button
            onClick={openCreateModal}
            className="px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-medium"
          >
            Create Account
          </button>
        </div>
      )}

      {/* Accounts List */}
      {!loading && accounts.length > 0 && (
        <div className="space-y-4">
          {accounts.map((account) => (
            <div
              key={account.id}
              className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold text-gray-900">{account.name}</h3>
                    <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-700 rounded">
                      {formatAccountType(account.account_type)}
                    </span>
                    {!account.is_active && (
                      <span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-700 rounded">
                        Inactive
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-600 space-y-1">
                    {account.institution && (
                      <p>Institution: {account.institution}</p>
                    )}
                    {account.account_number_last4 && (
                      <p>Account ending in: ****{account.account_number_last4}</p>
                    )}
                    <p className="text-gray-400">
                      Created: {new Date(account.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => openEditModal(account)}
                    className="px-3 py-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 rounded transition-colors"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => confirmDelete(account)}
                    className="px-3 py-1.5 text-sm font-medium text-red-600 hover:text-red-800 hover:bg-red-50 rounded transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-gray-900">
                {editingAccount ? 'Edit Account' : 'Create Account'}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleSave}>
              {/* Account Name */}
              <div className="mb-4">
                <label htmlFor="account-name" className="block text-sm font-medium text-gray-700 mb-1">
                  Account Name *
                </label>
                <input
                  type="text"
                  id="account-name"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g., Amex Platinum Card"
                  className="block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  required
                />
              </div>

              {/* Account Type - only for new accounts */}
              {!editingAccount && (
                <div className="mb-4">
                  <label htmlFor="account-type" className="block text-sm font-medium text-gray-700 mb-1">
                    Account Type *
                  </label>
                  <select
                    id="account-type"
                    value={formType}
                    onChange={(e) => setFormType(e.target.value as AccountType)}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    required
                  >
                    {ACCOUNT_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {formatAccountType(type)}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Institution */}
              <div className="mb-4">
                <label htmlFor="account-institution" className="block text-sm font-medium text-gray-700 mb-1">
                  Institution
                </label>
                <input
                  type="text"
                  id="account-institution"
                  value={formInstitution}
                  onChange={(e) => setFormInstitution(e.target.value)}
                  placeholder="e.g., American Express"
                  className="block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>

              {/* Last 4 Digits */}
              <div className="mb-6">
                <label htmlFor="account-last4" className="block text-sm font-medium text-gray-700 mb-1">
                  Last 4 Digits
                </label>
                <input
                  type="text"
                  id="account-last4"
                  value={formLast4}
                  onChange={(e) => setFormLast4(e.target.value.replace(/\D/g, '').slice(0, 4))}
                  placeholder="e.g., 1007"
                  maxLength={4}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>

              {/* Buttons */}
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="flex-1 py-2 px-4 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !formName.trim()}
                  className="flex-1 py-2 px-4 border border-transparent rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:bg-gray-400 disabled:cursor-not-allowed"
                >
                  {saving ? 'Saving...' : (editingAccount ? 'Save Changes' : 'Create Account')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && accountToDelete && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm mx-4 p-6">
            <div className="text-center">
              <div className="text-5xl mb-4">⚠️</div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Delete Account?</h3>
              <p className="text-gray-600 mb-6">
                Are you sure you want to delete <strong>{accountToDelete.name}</strong>?
                This will deactivate the account but keep all associated transactions.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="flex-1 py-2 px-4 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex-1 py-2 px-4 border border-transparent rounded-lg text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:bg-gray-400"
                >
                  {deleting ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
