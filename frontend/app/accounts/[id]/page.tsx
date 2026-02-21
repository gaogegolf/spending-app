'use client';

import { useState, useEffect, use } from 'react';
import Link from 'next/link';
import { getAccount, getImportsForAccount, getHoldingsSnapshots, deleteImport, deleteBrokerageSnapshot } from '@/lib/api';
import { Account, ImportRecord, AccountType } from '@/lib/types';
import { formatDate } from '@/lib/dateUtils';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

// Snapshot interface (not in types.ts)
interface Snapshot {
  id: string;
  account_id: string;
  statement_date: string;
  total_value: number;
  total_cash: number;
  total_securities: number;
  is_reconciled: boolean;
  position_count: number;
}

// Brokerage/Investment account types
const BROKERAGE_ACCOUNT_TYPES: AccountType[] = ['BROKERAGE', 'IRA_ROTH', 'IRA_TRADITIONAL', 'RETIREMENT_401K', 'STOCK_PLAN'];

function isBrokerageType(type: AccountType): boolean {
  return BROKERAGE_ACCOUNT_TYPES.includes(type);
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

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
}

export default function AccountDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [account, setAccount] = useState<Account | null>(null);
  const [imports, setImports] = useState<ImportRecord[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Delete confirmation dialog state
  const [deleteDialog, setDeleteDialog] = useState<{
    open: boolean;
    type: 'import' | 'snapshot';
    id: string;
    name: string;
  } | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadAccountData();
  }, [id]);

  async function loadAccountData() {
    try {
      setLoading(true);
      setError(null);

      const accountData = await getAccount(id);
      setAccount(accountData);

      // Load imports for all account types
      try {
        const importsData = await getImportsForAccount(id);
        setImports(importsData.imports || importsData || []);
      } catch {
        // Imports may not exist for all accounts
        setImports([]);
      }

      // Load snapshots for brokerage accounts
      if (isBrokerageType(accountData.account_type)) {
        try {
          const snapshotsData = await getHoldingsSnapshots({ accountId: id });
          setSnapshots(snapshotsData.snapshots || snapshotsData || []);
        } catch {
          setSnapshots([]);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load account');
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleteDialog) return;

    try {
      setDeleting(true);
      if (deleteDialog.type === 'import') {
        await deleteImport(deleteDialog.id);
        setImports(prev => prev.filter(i => i.id !== deleteDialog.id));
      } else {
        await deleteBrokerageSnapshot(deleteDialog.id);
        setSnapshots(prev => prev.filter(s => s.id !== deleteDialog.id));
      }
      setDeleteDialog(null);
      // Re-fetch account to update summary stats (transaction_count, import_count, etc.)
      const updatedAccount = await getAccount(id);
      setAccount(updatedAccount);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to delete ${deleteDialog.type}`);
    } finally {
      setDeleting(false);
    }
  }

  function getStatusBadgeVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
    switch (status) {
      case 'SUCCESS': return 'default';
      case 'FAILED': return 'destructive';
      case 'PROCESSING': return 'secondary';
      case 'PARTIAL': return 'outline';
      default: return 'secondary';
    }
  }

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12">
            <div className="text-center">
              <div className="animate-spin rounded-full h-10 w-10 border-3 border-indigo-200 border-t-indigo-600 mx-auto mb-4"></div>
              <p className="text-gray-500 text-sm">Loading account...</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !account) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <Link href="/accounts" className="inline-flex items-center text-sm text-indigo-600 hover:text-indigo-800 mb-6">
            <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Accounts
          </Link>
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        </div>
      </div>
    );
  }

  if (!account) return null;

  const isBrokerage = isBrokerageType(account.account_type);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Back link */}
        <Link href="/accounts" className="inline-flex items-center text-sm text-indigo-600 hover:text-indigo-800 mb-6">
          <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Accounts
        </Link>

        {/* Error banner (for non-fatal errors) */}
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Header */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center text-3xl flex-shrink-0">
                {getAccountIcon(account.account_type)}
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-bold text-gray-900">{account.name}</h1>
                  {account.is_active ? (
                    <Badge variant="default" className="bg-green-100 text-green-700 hover:bg-green-100">Active</Badge>
                  ) : (
                    <Badge variant="secondary">Inactive</Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-500 mt-1">
                  <span>{formatAccountType(account.account_type)}</span>
                  {account.institution && (
                    <>
                      <span>·</span>
                      <span>{account.institution}</span>
                    </>
                  )}
                  {account.account_number_last4 && (
                    <>
                      <span>·</span>
                      <span className="font-mono">****{account.account_number_last4}</span>
                    </>
                  )}
                </div>
              </div>
            </div>
            <Link href={`/transactions?account_id=${account.id}`}>
              <Button>
                <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
                View Transactions
              </Button>
            </Link>
          </div>
        </div>

        {/* Summary stats cards */}
        <div className={`grid ${isBrokerage ? 'grid-cols-2 md:grid-cols-4' : 'grid-cols-2'} gap-4 mb-6`}>
          {isBrokerage ? (
            <>
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-gray-500">Snapshots</p>
                  <p className="text-2xl font-bold text-gray-900">{account.snapshot_count}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-gray-500">Positions</p>
                  <p className="text-2xl font-bold text-gray-900">{account.position_count}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-gray-500">Statements Imported</p>
                  <p className="text-2xl font-bold text-gray-900">{imports.length}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-gray-500">Transactions</p>
                  <p className="text-2xl font-bold text-gray-900">{account.transaction_count}</p>
                </CardContent>
              </Card>
            </>
          ) : (
            <>
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-gray-500">Transactions</p>
                  <p className="text-2xl font-bold text-gray-900">{account.transaction_count.toLocaleString()}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-gray-500">Statements Imported</p>
                  <p className="text-2xl font-bold text-gray-900">{account.import_count}</p>
                </CardContent>
              </Card>
            </>
          )}
        </div>

        {/* Snapshots table (brokerage only) */}
        {isBrokerage && snapshots.length > 0 && (
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Snapshots</h2>
            <div className="bg-white shadow-sm rounded-lg border border-gray-100 overflow-hidden">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Statement Date</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Total Value</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Securities</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Cash</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Reconciled</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {snapshots.map((snapshot) => (
                    <tr key={snapshot.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm text-gray-900">
                        {formatDate(snapshot.statement_date, { year: 'numeric', month: 'short', day: 'numeric' })}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 text-right font-medium">
                        {formatCurrency(snapshot.total_value)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600 text-right">
                        {formatCurrency(snapshot.total_securities)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600 text-right">
                        {formatCurrency(snapshot.total_cash)}
                      </td>
                      <td className="px-4 py-3 text-sm text-center">
                        {snapshot.is_reconciled ? (
                          <Badge variant="default" className="bg-green-100 text-green-700 hover:bg-green-100">Yes</Badge>
                        ) : (
                          <Badge variant="secondary">No</Badge>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-right">
                        <button
                          onClick={() => setDeleteDialog({ open: true, type: 'snapshot', id: snapshot.id, name: `snapshot from ${formatDate(snapshot.statement_date, { year: 'numeric', month: 'short', day: 'numeric' })}` })}
                          className="text-gray-400 hover:text-red-600 transition-colors"
                          title="Delete snapshot"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Statements/Imports table */}
        {imports.length > 0 && (
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Imported Statements</h2>
            <div className="bg-white shadow-sm rounded-lg border border-gray-100 overflow-hidden">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Filename</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Imported</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Transactions</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {imports.map((imp) => (
                    <tr key={imp.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm text-gray-900 font-medium truncate max-w-xs" title={imp.filename}>
                        {imp.filename}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        <Badge variant="outline">{imp.source_type}</Badge>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {imp.created_at ? formatDate(imp.created_at.split('T')[0], { year: 'numeric', month: 'short', day: 'numeric' }) : '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900 text-right">
                        {imp.transactions_imported}
                        {imp.transactions_duplicate > 0 && (
                          <span className="text-gray-400 ml-1">(+{imp.transactions_duplicate} dupes)</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-center">
                        <Badge variant={getStatusBadgeVariant(imp.status)}>
                          {imp.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-sm text-right">
                        <button
                          onClick={() => setDeleteDialog({ open: true, type: 'import', id: imp.id, name: imp.filename })}
                          className="text-gray-400 hover:text-red-600 transition-colors"
                          title="Delete import"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Empty state when no imports and no snapshots */}
        {imports.length === 0 && snapshots.length === 0 && (
          <Card className="p-8 text-center">
            <CardContent className="p-0">
              <div className="text-4xl mb-3">📄</div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">No imports yet</h3>
              <p className="text-gray-500 text-sm mb-4">
                Import statements to see them here.
              </p>
              <Link href="/imports">
                <Button variant="outline">Go to Imports</Button>
              </Link>
            </CardContent>
          </Card>
        )}

        {/* Delete confirmation dialog */}
        <Dialog open={deleteDialog?.open === true} onOpenChange={(open) => !open && setDeleteDialog(null)}>
          <DialogContent className="sm:max-w-sm">
            <DialogHeader className="text-center">
              <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
                <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <DialogTitle>Delete {deleteDialog?.type === 'import' ? 'Import' : 'Snapshot'}</DialogTitle>
              <DialogDescription>
                Are you sure you want to delete <strong className="text-foreground">{deleteDialog?.name}</strong>?
                {deleteDialog?.type === 'import' && (
                  <span className="block mt-2 text-red-600">
                    This will also delete all transactions from this import.
                  </span>
                )}
                {deleteDialog?.type === 'snapshot' && (
                  <span className="block mt-2 text-red-600">
                    This will also delete all positions from this snapshot.
                  </span>
                )}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="flex gap-2 sm:justify-center">
              <Button
                variant="outline"
                onClick={() => setDeleteDialog(null)}
                disabled={deleting}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleDelete}
                disabled={deleting}
              >
                {deleting ? 'Deleting...' : 'Delete'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
