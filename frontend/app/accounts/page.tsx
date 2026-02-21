'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getAccounts, createAccount, updateAccount, deleteAccount } from '@/lib/api';
import { Account, AccountType } from '@/lib/types';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

// Bank/Transaction account types
const BANK_ACCOUNT_TYPES: AccountType[] = ['CREDIT_CARD', 'CHECKING', 'SAVINGS', 'CASH', 'DIGITAL_WALLET', 'OTHER'];
// Brokerage/Investment account types
const BROKERAGE_ACCOUNT_TYPES: AccountType[] = ['BROKERAGE', 'IRA_ROTH', 'IRA_TRADITIONAL', 'RETIREMENT_401K', 'STOCK_PLAN'];

// Helper to determine if an account type is bank or brokerage
function isBrokerageType(type: AccountType): boolean {
  return BROKERAGE_ACCOUNT_TYPES.includes(type);
}

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

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
        const updateData: {
          name: string;
          institution?: string;
          account_type?: string;
          account_number_last4?: string;
        } = {
          name: formName.trim(),
          institution: formInstitution.trim() || undefined,
          account_number_last4: formLast4.trim() || undefined,
        };
        if (formType !== editingAccount.account_type) {
          updateData.account_type = formType;
        }
        const updated = await updateAccount(editingAccount.id, updateData);
        setAccounts(accounts.map(a => a.id === updated.id ? updated : a));
      } else {
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

  async function handleDelete(permanent: boolean) {
    if (!accountToDelete) return;

    try {
      setDeleting(true);
      setError(null);
      await deleteAccount(accountToDelete.id, permanent);
      if (permanent) {
        setAccounts(accounts.filter(a => a.id !== accountToDelete.id));
      } else {
        setAccounts(accounts.map(a =>
          a.id === accountToDelete.id ? { ...a, is_active: false } : a
        ));
      }
      setShowDeleteConfirm(false);
      setAccountToDelete(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete account');
    } finally {
      setDeleting(false);
    }
  }

  function formatAccountType(type: string): string {
    const typeLabels: Record<string, string> = {
      'CREDIT_CARD': 'Credit Card',
      'CHECKING': 'Checking',
      'SAVINGS': 'Savings',
      'OTHER': 'Other',
      'CASH': 'Cash',
      'DIGITAL_WALLET': 'Digital Wallet',
      'BROKERAGE': 'Brokerage',
      'IRA_ROTH': 'Roth IRA',
      'IRA_TRADITIONAL': 'Traditional IRA',
      'RETIREMENT_401K': '401(k)',
      'STOCK_PLAN': 'Stock Plan',
    };
    return typeLabels[type] || type.replace('_', ' ');
  }

  function getAccountIcon(type: string): string {
    switch (type) {
      case 'CREDIT_CARD': return '💳';
      case 'CHECKING': return '🏦';
      case 'SAVINGS': return '🐷';
      case 'BROKERAGE': return '💼';
      case 'IRA_ROTH': return '🌟';
      case 'IRA_TRADITIONAL': return '📋';
      case 'RETIREMENT_401K': return '🏛️';
      case 'STOCK_PLAN': return '📊';
      case 'CASH': return '💵';
      case 'DIGITAL_WALLET': return '📱';
      default: return '💰';
    }
  }

  // Filter accounts by search query
  const filteredAccounts = searchQuery.trim()
    ? accounts.filter(a => {
        const text = `${a.name} ${a.institution || ''}`.toLowerCase();
        return searchQuery.toLowerCase().split(/\s+/).every(word => text.includes(word));
      })
    : accounts;

  // Group accounts by category
  const bankAccounts = filteredAccounts.filter(a => !isBrokerageType(a.account_type));
  const investmentAccounts = filteredAccounts.filter(a => isBrokerageType(a.account_type));

  // Further group bank accounts by type
  const creditCards = bankAccounts.filter(a => a.account_type === 'CREDIT_CARD');
  const checkingAccounts = bankAccounts.filter(a => a.account_type === 'CHECKING');
  const savingsAccounts = bankAccounts.filter(a => a.account_type === 'SAVINGS');
  const otherAccounts = bankAccounts.filter(a => a.account_type === 'OTHER');
  const cashAccounts = bankAccounts.filter(a => a.account_type === 'CASH');
  const digitalWalletAccounts = bankAccounts.filter(a => a.account_type === 'DIGITAL_WALLET');

  // Render a single account card (compact)
  function renderAccountCard(account: Account) {
    return (
      <Link
        href={`/accounts/${account.id}`}
        key={account.id}
        className={`group relative bg-white rounded-xl border p-4 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 block ${
          !account.is_active ? 'opacity-60 border-gray-200' : 'border-gray-100 shadow-sm'
        }`}
      >
        {/* Edit/Delete buttons - show on hover */}
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
          <button
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); openEditModal(account); }}
            className="p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
            title="Edit"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
            </svg>
          </button>
          <button
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); confirmDelete(account); }}
            className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
            title="Delete"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>

        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center text-xl flex-shrink-0">
            {getAccountIcon(account.account_type)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-gray-900 truncate text-sm">{account.name}</h3>
              {!account.is_active && (
                <span className="px-1.5 py-0.5 text-[10px] font-medium bg-gray-100 text-gray-500 rounded">
                  Inactive
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-500 mt-0.5">
              {account.institution && <span>{account.institution}</span>}
              {account.institution && account.account_number_last4 && <span>·</span>}
              {account.account_number_last4 && <span className="font-mono">****{account.account_number_last4}</span>}
            </div>
            {/* Stats line - different for bank vs investment accounts */}
            {isBrokerageType(account.account_type) ? (
              // Investment account stats
              (account.position_count > 0 || account.snapshot_count > 0) && (
                <div className="text-xs text-emerald-600 font-medium mt-1">
                  {account.position_count > 0 && (
                    <span>{account.position_count} position{account.position_count !== 1 ? 's' : ''}</span>
                  )}
                  {account.position_count > 0 && account.snapshot_count > 0 && <span> · </span>}
                  {account.snapshot_count > 0 && (
                    <span>{account.snapshot_count} snapshot{account.snapshot_count !== 1 ? 's' : ''}</span>
                  )}
                </div>
              )
            ) : (
              // Bank account stats
              (account.transaction_count > 0 || account.import_count > 0) && (
                <div className="text-xs text-indigo-600 font-medium mt-1">
                  {account.transaction_count > 0 && (
                    <span>{account.transaction_count.toLocaleString()} transaction{account.transaction_count !== 1 ? 's' : ''}</span>
                  )}
                  {account.transaction_count > 0 && account.import_count > 0 && <span> · </span>}
                  {account.import_count > 0 && (
                    <span>{account.import_count} statement{account.import_count !== 1 ? 's' : ''}</span>
                  )}
                </div>
              )
            )}
          </div>
        </div>
      </Link>
    );
  }

  // Render a section with accounts
  function renderSection(title: string, icon: string, accountsList: Account[], colorClass: string) {
    if (accountsList.length === 0) return null;

    return (
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-lg">{icon}</span>
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">{title}</h3>
          <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${colorClass}`}>
            {accountsList.length}
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {accountsList.map(renderAccountCard)}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg">
              <span className="text-xl">🏦</span>
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Accounts</h1>
              <p className="text-sm text-gray-500">
                {accounts.length} account{accounts.length !== 1 ? 's' : ''} · {accounts.filter(a => a.is_active).length} active
              </p>
            </div>
          </div>
          <Button onClick={openCreateModal}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Account
          </Button>
        </div>

        {/* Search */}
        {!loading && accounts.length > 0 && (
          <div className="relative mb-6">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <Input
              type="text"
              placeholder="Search accounts..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
        )}

        {/* Error Message */}
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Loading State */}
        {loading && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12">
            <div className="text-center">
              <div className="animate-spin rounded-full h-10 w-10 border-3 border-indigo-200 border-t-indigo-600 mx-auto mb-4"></div>
              <p className="text-gray-500 text-sm">Loading accounts...</p>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!loading && accounts.length === 0 && (
          <Card className="p-12 text-center">
            <CardContent className="p-0">
              <div className="text-5xl mb-4">🏦</div>
              <h3 className="text-lg font-semibold text-foreground mb-2">No accounts yet</h3>
              <p className="text-muted-foreground text-sm mb-6 max-w-md mx-auto">
                Create your first account to start importing transactions.
              </p>
              <Button onClick={openCreateModal}>
                Create Account
              </Button>
            </CardContent>
          </Card>
        )}

        {/* No search results */}
        {!loading && accounts.length > 0 && filteredAccounts.length === 0 && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center">
            <div className="text-4xl mb-3">🔍</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-1">No accounts found</h3>
            <p className="text-gray-500 text-sm">No accounts match &ldquo;{searchQuery}&rdquo;</p>
          </div>
        )}

        {/* Accounts by Category */}
        {!loading && filteredAccounts.length > 0 && (
          <div className="space-y-8">
            {/* Bank & Credit Section */}
            {bankAccounts.length > 0 && (
              <div className="bg-white/70 backdrop-blur rounded-2xl border border-gray-100 shadow-sm p-6">
                <div className="flex items-center gap-2 mb-5 pb-3 border-b border-gray-100">
                  <span className="text-2xl">💳</span>
                  <h2 className="text-lg font-bold text-gray-900">Bank & Credit</h2>
                  <span className="px-2 py-0.5 text-xs font-medium bg-indigo-100 text-indigo-700 rounded-full">
                    {bankAccounts.length}
                  </span>
                </div>

                {renderSection('Credit Cards', '💳', creditCards, 'bg-purple-100 text-purple-700')}
                {renderSection('Checking', '🏦', checkingAccounts, 'bg-blue-100 text-blue-700')}
                {renderSection('Savings', '🐷', savingsAccounts, 'bg-green-100 text-green-700')}
                {renderSection('Cash', '💵', cashAccounts, 'bg-emerald-100 text-emerald-700')}
                {renderSection('Digital Wallets', '📱', digitalWalletAccounts, 'bg-cyan-100 text-cyan-700')}
                {renderSection('Other', '💰', otherAccounts, 'bg-gray-100 text-gray-700')}
              </div>
            )}

            {/* Investment Section */}
            {investmentAccounts.length > 0 && (
              <div className="bg-white/70 backdrop-blur rounded-2xl border border-gray-100 shadow-sm p-6">
                <div className="flex items-center gap-2 mb-5 pb-3 border-b border-gray-100">
                  <span className="text-2xl">📈</span>
                  <h2 className="text-lg font-bold text-gray-900">Investments</h2>
                  <span className="px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700 rounded-full">
                    {investmentAccounts.length}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {investmentAccounts.map(renderAccountCard)}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Create/Edit Modal */}
        <Dialog open={showModal} onOpenChange={setShowModal}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                {editingAccount ? 'Edit Account' : 'Create Account'}
              </DialogTitle>
            </DialogHeader>

            <form onSubmit={handleSave} className="space-y-4">
              {/* Account Name */}
              <div className="space-y-2">
                <Label htmlFor="account-name">Account Name *</Label>
                <Input
                  type="text"
                  id="account-name"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g., Amex Platinum Card"
                  required
                />
              </div>

              {/* Account Type */}
              <div className="space-y-2">
                <Label>Account Type *</Label>
                {editingAccount ? (
                  <Select value={formType} onValueChange={(val) => setFormType(val as AccountType)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      {(isBrokerageType(editingAccount.account_type) ? BROKERAGE_ACCOUNT_TYPES : BANK_ACCOUNT_TYPES).map((type) => (
                        <SelectItem key={type} value={type}>
                          {formatAccountType(type)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Select value={formType} onValueChange={(val) => setFormType(val as AccountType)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectLabel>Bank & Credit</SelectLabel>
                        {BANK_ACCOUNT_TYPES.map((type) => (
                          <SelectItem key={type} value={type}>
                            {formatAccountType(type)}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                      <SelectGroup>
                        <SelectLabel>Investments</SelectLabel>
                        {BROKERAGE_ACCOUNT_TYPES.map((type) => (
                          <SelectItem key={type} value={type}>
                            {formatAccountType(type)}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                )}
              </div>

              {/* Institution */}
              <div className="space-y-2">
                <Label htmlFor="account-institution">Institution</Label>
                <Input
                  type="text"
                  id="account-institution"
                  value={formInstitution}
                  onChange={(e) => setFormInstitution(e.target.value)}
                  placeholder="e.g., American Express"
                />
              </div>

              {/* Last 4 Digits */}
              <div className="space-y-2">
                <Label htmlFor="account-last4">Last 4 Digits</Label>
                <Input
                  type="text"
                  id="account-last4"
                  value={formLast4}
                  onChange={(e) => setFormLast4(e.target.value.replace(/\D/g, '').slice(0, 4))}
                  placeholder="e.g., 1007"
                  maxLength={4}
                />
              </div>

              {/* Buttons */}
              <DialogFooter>
                <Button
                  type="button"
                  onClick={() => setShowModal(false)}
                  variant="outline"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={saving || !formName.trim()}
                >
                  {saving ? 'Saving...' : (editingAccount ? 'Save Changes' : 'Create')}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        {/* Delete Confirmation Modal */}
        <Dialog open={showDeleteConfirm && accountToDelete !== null} onOpenChange={(open) => !open && setShowDeleteConfirm(false)}>
          <DialogContent className="sm:max-w-sm">
            <DialogHeader className="text-center">
              <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
                <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <DialogTitle>Remove Account</DialogTitle>
              <DialogDescription>
                What would you like to do with <strong className="text-foreground">{accountToDelete?.name}</strong>?
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-2">
              <Button
                onClick={() => handleDelete(false)}
                disabled={deleting}
                variant="outline"
                className="w-full justify-start border-amber-200 bg-amber-50 hover:bg-amber-100"
              >
                <span className="text-xl mr-3">😴</span>
                <div className="text-left">
                  <p className="font-medium text-sm">Deactivate</p>
                  <p className="text-xs text-muted-foreground">Hide but keep data</p>
                </div>
              </Button>

              <Button
                onClick={() => handleDelete(true)}
                disabled={deleting}
                variant="outline"
                className="w-full justify-start border-red-200 bg-red-50 hover:bg-red-100"
              >
                <span className="text-xl mr-3">🗑️</span>
                <div className="text-left">
                  <p className="font-medium text-red-600 text-sm">Delete Permanently</p>
                  <p className="text-xs text-muted-foreground">Remove all data</p>
                </div>
              </Button>

              <Button
                onClick={() => setShowDeleteConfirm(false)}
                disabled={deleting}
                variant="ghost"
                className="w-full"
              >
                {deleting ? 'Processing...' : 'Cancel'}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
