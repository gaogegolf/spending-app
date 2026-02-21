# Account Detail Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dedicated account detail page at `/accounts/[id]` showing import history, snapshots, and actions for both bank and brokerage accounts.

**Architecture:** New Next.js dynamic route page that fetches account details, import records, and (for brokerage) snapshots via existing API endpoints. Account cards on the list page become clickable links. No new backend endpoints needed — `GET /imports?account_id=X`, `GET /brokerage/snapshots?account_id=X`, `DELETE /imports/{id}`, and `DELETE /brokerage/snapshots/{id}` all exist.

**Tech Stack:** Next.js (App Router), TypeScript, Tailwind CSS, Radix UI components (already in project)

---

### Task 1: Add frontend API client functions

**Files:**
- Modify: `frontend/lib/api.ts`

**Step 1: Add API functions**

Add these functions to `frontend/lib/api.ts`:

```typescript
export async function getAccount(accountId: string) {
  const response = await authFetch(`${API_BASE_URL}/accounts/${accountId}`);
  if (!response.ok) throw new Error('Failed to fetch account');
  return response.json();
}

export async function getImportsForAccount(accountId: string) {
  const response = await authFetch(`${API_BASE_URL}/imports?account_id=${accountId}`);
  if (!response.ok) throw new Error('Failed to fetch imports');
  return response.json();
}

export async function deleteImport(importId: string) {
  const response = await authFetch(`${API_BASE_URL}/imports/${importId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete import');
}

export async function getSnapshotsForAccount(accountId: string) {
  const response = await authFetch(`${API_BASE_URL}/brokerage/snapshots?account_id=${accountId}`);
  if (!response.ok) throw new Error('Failed to fetch snapshots');
  return response.json();
}

export async function deleteSnapshot(snapshotId: string) {
  const response = await authFetch(`${API_BASE_URL}/brokerage/snapshots/${snapshotId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete snapshot');
}
```

**Step 2: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: add API client functions for account detail page"
```

---

### Task 2: Create the account detail page

**Files:**
- Create: `frontend/app/accounts/[id]/page.tsx`

**Step 1: Create the page**

Create `frontend/app/accounts/[id]/page.tsx`. This is the main page component. Use `'use client'` directive.

```typescript
'use client';

import { useState, useEffect, use } from 'react';
import Link from 'next/link';
import { getAccount, getImportsForAccount, getSnapshotsForAccount, deleteImport, deleteSnapshot, deleteAccount } from '@/lib/api';
import { Account, ImportRecord, AccountType } from '@/lib/types';
import { formatDate } from '@/lib/dateUtils';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

const BROKERAGE_ACCOUNT_TYPES: AccountType[] = ['BROKERAGE', 'IRA_ROTH', 'IRA_TRADITIONAL', 'RETIREMENT_401K', 'STOCK_PLAN'];

function isBrokerageType(type: AccountType): boolean {
  return BROKERAGE_ACCOUNT_TYPES.includes(type);
}

function getAccountIcon(type: string): string {
  switch (type) {
    case 'CREDIT_CARD': return '💳';
    case 'CHECKING': return '🏦';
    case 'SAVINGS': return '🐷';
    case 'CASH': return '💵';
    case 'DIGITAL_WALLET': return '📱';
    case 'BROKERAGE': return '💼';
    case 'IRA_ROTH': return '🌟';
    case 'IRA_TRADITIONAL': return '📋';
    case 'RETIREMENT_401K': return '🏛️';
    case 'STOCK_PLAN': return '📊';
    default: return '💰';
  }
}

function formatAccountType(type: string): string {
  const labels: Record<string, string> = {
    'CREDIT_CARD': 'Credit Card',
    'CHECKING': 'Checking',
    'SAVINGS': 'Savings',
    'CASH': 'Cash',
    'DIGITAL_WALLET': 'Digital Wallet',
    'OTHER': 'Other',
    'BROKERAGE': 'Brokerage',
    'IRA_ROTH': 'Roth IRA',
    'IRA_TRADITIONAL': 'Traditional IRA',
    'RETIREMENT_401K': '401(k)',
    'STOCK_PLAN': 'Stock Plan',
  };
  return labels[type] || type;
}

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

export default function AccountDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [account, setAccount] = useState<Account | null>(null);
  const [imports, setImports] = useState<ImportRecord[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<{ type: 'import' | 'snapshot'; id: string; name: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadData();
  }, [id]);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const accountData = await getAccount(id);
      setAccount(accountData);

      const importsData = await getImportsForAccount(id);
      setImports(importsData.imports || []);

      if (isBrokerageType(accountData.account_type)) {
        const snapshotsData = await getSnapshotsForAccount(id);
        setSnapshots(snapshotsData.snapshots || []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load account');
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      setDeleting(true);
      if (deleteTarget.type === 'import') {
        await deleteImport(deleteTarget.id);
        setImports(imports.filter(i => i.id !== deleteTarget.id));
      } else {
        await deleteSnapshot(deleteTarget.id);
        setSnapshots(snapshots.filter(s => s.id !== deleteTarget.id));
      }
      setDeleteTarget(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete');
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-10 w-10 border-3 border-indigo-200 border-t-indigo-600"></div>
        </div>
      </div>
    );
  }

  if (!account) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <Alert><AlertDescription>Account not found.</AlertDescription></Alert>
        <Link href="/accounts" className="text-indigo-600 hover:underline mt-4 inline-block">← Back to Accounts</Link>
      </div>
    );
  }

  const isBrokerage = isBrokerageType(account.account_type);

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Back link */}
      <Link href="/accounts" className="text-sm text-gray-500 hover:text-indigo-600 mb-6 inline-flex items-center gap-1">
        ← Back to Accounts
      </Link>

      {/* Header */}
      <div className="flex items-center justify-between mb-8 mt-4">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center text-2xl shadow-sm">
            {getAccountIcon(account.account_type)}
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{account.name}</h1>
            <div className="flex items-center gap-2 text-sm text-gray-500 mt-0.5">
              <span>{formatAccountType(account.account_type)}</span>
              {account.institution && <><span>·</span><span>{account.institution}</span></>}
              {account.account_number_last4 && <><span>·</span><span className="font-mono">****{account.account_number_last4}</span></>}
              {!account.is_active && <Badge variant="secondary">Inactive</Badge>}
            </div>
          </div>
        </div>
        <Link href={`/transactions?account_id=${account.id}`}>
          <Button variant="outline">View Transactions</Button>
        </Link>
      </div>

      {error && (
        <Alert className="mb-6"><AlertDescription>{error}</AlertDescription></Alert>
      )}

      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        {!isBrokerage ? (
          <>
            <Card><CardContent className="pt-6">
              <p className="text-2xl font-bold text-gray-900">{account.transaction_count.toLocaleString()}</p>
              <p className="text-sm text-gray-500">Transactions</p>
            </CardContent></Card>
            <Card><CardContent className="pt-6">
              <p className="text-2xl font-bold text-gray-900">{account.import_count}</p>
              <p className="text-sm text-gray-500">Statements</p>
            </CardContent></Card>
          </>
        ) : (
          <>
            <Card><CardContent className="pt-6">
              <p className="text-2xl font-bold text-gray-900">{account.snapshot_count}</p>
              <p className="text-sm text-gray-500">Snapshots</p>
            </CardContent></Card>
            <Card><CardContent className="pt-6">
              <p className="text-2xl font-bold text-gray-900">{account.position_count}</p>
              <p className="text-sm text-gray-500">Positions</p>
            </CardContent></Card>
          </>
        )}
      </div>

      {/* Snapshots table (brokerage only) */}
      {isBrokerage && snapshots.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Holdings Snapshots</h2>
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Statement Date</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Total Value</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Securities</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Cash</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Reconciled</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {snapshots.map((snapshot) => (
                  <tr key={snapshot.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-900">{formatDate(snapshot.statement_date)}</td>
                    <td className="px-4 py-3 text-sm text-gray-900 text-right font-semibold">
                      ${Number(snapshot.total_value).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500 text-right">
                      ${Number(snapshot.total_securities).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500 text-right">
                      ${Number(snapshot.total_cash).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {snapshot.is_reconciled
                        ? <span className="text-green-600" title="Reconciled">✓</span>
                        : <span className="text-yellow-500" title="Not reconciled">⚠</span>
                      }
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => setDeleteTarget({ type: 'snapshot', id: snapshot.id, name: `snapshot from ${formatDate(snapshot.statement_date)}` })}
                        className="text-gray-400 hover:text-red-600 text-sm"
                        title="Delete snapshot"
                      >🗑️</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Imports/Statements table */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          {isBrokerage ? 'Imported Statements' : 'Statements'}
        </h2>
        {imports.length === 0 ? (
          <Card>
            <CardContent className="pt-6 text-center text-gray-500">
              No statements imported yet.
              <Link href="/imports" className="text-indigo-600 hover:underline ml-1">Import one →</Link>
            </CardContent>
          </Card>
        ) : (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Filename</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Imported</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Transactions</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {imports.map((imp) => (
                  <tr key={imp.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-900 truncate max-w-[200px]" title={imp.filename}>
                      {imp.filename}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{imp.source_type}</td>
                    <td className="px-4 py-3 text-sm text-gray-500">{formatDate(imp.created_at.split('T')[0])}</td>
                    <td className="px-4 py-3 text-sm text-gray-900 text-right">
                      {imp.transactions_imported}
                      {imp.transactions_duplicate > 0 && (
                        <span className="text-gray-400 ml-1">({imp.transactions_duplicate} dupes)</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        imp.status === 'SUCCESS' ? 'bg-green-100 text-green-700' :
                        imp.status === 'FAILED' ? 'bg-red-100 text-red-700' :
                        imp.status === 'PARTIAL' ? 'bg-yellow-100 text-yellow-700' :
                        'bg-gray-100 text-gray-700'
                      }`}>{imp.status}</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => setDeleteTarget({ type: 'import', id: imp.id, name: imp.filename })}
                        className="text-gray-400 hover:text-red-600 text-sm"
                        title="Delete import"
                      >🗑️</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteTarget !== null} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete {deleteTarget?.type === 'snapshot' ? 'Snapshot' : 'Import'}</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>{deleteTarget?.name}</strong>?
              {deleteTarget?.type === 'import' && ' This will also delete all transactions from this import.'}
              {deleteTarget?.type === 'snapshot' && ' This will also delete all positions from this snapshot.'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/accounts/\[id\]/page.tsx
git commit -m "feat: add account detail page with imports and snapshots tables"
```

---

### Task 3: Make account cards clickable on list page

**Files:**
- Modify: `frontend/app/accounts/page.tsx`

**Step 1: Add Link import**

Add `import Link from 'next/link';` to the imports at the top of the file (if not already present).

**Step 2: Wrap account card with Link**

In the `renderAccountCard` function, wrap the outer `<div>` content with a `<Link>` to make the entire card clickable:

Find the outer div of the card:
```tsx
      <div
        key={account.id}
        className={`group relative bg-white rounded-xl border p-4 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 ${
          !account.is_active ? 'opacity-60 border-gray-200' : 'border-gray-100 shadow-sm'
        }`}
      >
```

Change it to:
```tsx
      <Link
        href={`/accounts/${account.id}`}
        key={account.id}
        className={`group relative bg-white rounded-xl border p-4 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 block ${
          !account.is_active ? 'opacity-60 border-gray-200' : 'border-gray-100 shadow-sm'
        }`}
      >
```

And change the closing `</div>` of the card to `</Link>`.

Make sure Edit and Delete buttons use `e.preventDefault()` and `e.stopPropagation()` in their onClick handlers to prevent navigation when clicking them.

**Step 3: Commit**

```bash
git add frontend/app/accounts/page.tsx
git commit -m "feat: make account cards clickable links to detail page"
```

---

### Task 4: Verify end-to-end

**Step 1: Test bank account detail**

Open http://localhost:3001/accounts, click a credit card account. Verify:
- Header shows correct name, type, institution, last4
- Summary stats show transaction count and import count
- Statements table shows imported files with correct data
- Delete button on a statement shows confirmation dialog
- "View Transactions" button links to filtered transactions page
- Back link returns to accounts list

**Step 2: Test brokerage account detail**

Click a brokerage account. Verify:
- Summary stats show snapshot count and position count
- Snapshots table shows statement dates, values, reconciliation status
- Statements table also shows imported files
- Delete works for both snapshots and imports

**Step 3: Test edge cases**

- Click a new account with no imports → shows "No statements imported yet" with link to import page
- Verify Edit/Delete buttons on list page still work without navigating
