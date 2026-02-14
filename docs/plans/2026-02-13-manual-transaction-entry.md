# Manual Transaction Entry — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to manually add transactions via a form on the Transactions page.

**Architecture:** Add a `POST /api/v1/transactions` endpoint to the existing transactions router. Generate a deterministic dedup hash with `manual:` prefix. Add a dialog form to the Transactions page that calls this endpoint.

**Tech Stack:** FastAPI, SQLAlchemy, Next.js, React, shadcn/ui Dialog

---

### Task 1: Backend — Add POST endpoint for manual transaction creation

**Files:**
- Modify: `backend/app/api/v1/transactions.py` (add new route near top of file, after imports)

**Step 1: Add the create endpoint**

Add this route after the `router = APIRouter()` line (line 28) and before the `list_transactions` route:

```python
@router.post("/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    transaction_data: TransactionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Manually create a new transaction.

    Args:
        transaction_data: Transaction data from user
        current_user: Authenticated user
        db: Database session

    Returns:
        Created transaction
    """
    import uuid
    import hashlib

    # Verify account belongs to user
    account = db.query(Account).filter(
        Account.id == transaction_data.account_id,
        Account.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {transaction_data.account_id} not found"
        )

    # Generate deterministic dedup hash for manual transactions
    hash_input = f"manual:{transaction_data.account_id}:{transaction_data.date.isoformat()}:{transaction_data.description_raw}:{transaction_data.amount}"
    hash_dedup_key = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

    # Check for duplicate
    existing = db.query(Transaction).filter(
        Transaction.hash_dedup_key == hash_dedup_key
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A transaction with the same account, date, description, and amount already exists"
        )

    # Create transaction
    transaction = Transaction(
        id=str(uuid.uuid4()),
        account_id=transaction_data.account_id,
        import_id=None,
        hash_dedup_key=hash_dedup_key,
        date=transaction_data.date,
        post_date=transaction_data.post_date,
        description_raw=transaction_data.description_raw,
        merchant_normalized=transaction_data.merchant_normalized,
        amount=abs(transaction_data.amount),
        currency=transaction_data.currency,
        transaction_type=transaction_data.transaction_type,
        category=transaction_data.category,
        subcategory=transaction_data.subcategory,
        tags=transaction_data.tags,
        confidence=1.0,
        needs_review=False,
        classification_method='MANUAL',
        user_note=transaction_data.user_note,
    )
    transaction.set_is_spend_based_on_type()

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return transaction
```

**Step 2: Verify the server starts without errors**

Run: `cd backend && python -c "from app.main import app; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/app/api/v1/transactions.py
git commit -m "feat: add POST /api/v1/transactions endpoint for manual entry"
```

---

### Task 2: Frontend — Add `createTransaction` to API client

**Files:**
- Modify: `frontend/lib/api.ts` (add after the existing `getTransactions` function, around line 176)

**Step 1: Add the API function**

Add after the `getTransactions` function:

```typescript
export async function createTransaction(data: {
  account_id: string;
  date: string;
  description_raw: string;
  amount: number;
  transaction_type: string;
  currency?: string;
  post_date?: string;
  merchant_normalized?: string;
  category?: string;
  subcategory?: string;
  tags?: string[];
  user_note?: string;
}) {
  const response = await authFetch(`${API_BASE_URL}/transactions`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (response.status === 409) {
    throw new Error('A transaction with the same account, date, description, and amount already exists');
  }
  if (!response.ok) throw new Error('Failed to create transaction');
  return response.json();
}
```

**Step 2: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: add createTransaction API client function"
```

---

### Task 3: Frontend — Add "Add Transaction" dialog to Transactions page

**Files:**
- Modify: `frontend/app/transactions/page.tsx`

**Step 1: Add import for `createTransaction`**

In the import from `@/lib/api` (line 6), add `createTransaction`:

```typescript
import { getTransactions, getAccounts, deleteTransaction, bulkDeleteTransactions, reclassifyAllTransactions, updateTransaction, exportTransactions, getMerchantTransactionCount, applyMerchantCategory, createTransaction } from '@/lib/api';
```

**Step 2: Add state variables for the add dialog**

After the existing state declarations (around line 65, after the `applyingMerchant` state), add:

```typescript
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
```

**Step 3: Add the form reset and submit handler**

After the `closeApplyMerchantPrompt` function (around line 349), add:

```typescript
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
```

**Step 4: Add the "Add Transaction" button to the page header**

In the header `div` with the buttons (around line 636), add before the Export CSV button:

```tsx
          <Button
            onClick={() => { resetAddForm(); setShowAddDialog(true); }}
            variant="default"
          >
            + Add Transaction
          </Button>
```

**Step 5: Add the Add Transaction Dialog**

At the bottom of the component, before the closing `</div>` of the page (around line 1500, after the Apply Merchant Category Dialog), add:

```tsx
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
                  <SelectContent>
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
```

**Step 6: Commit**

```bash
git add frontend/app/transactions/page.tsx
git commit -m "feat: add manual transaction entry dialog to Transactions page"
```

---

### Task 4: Manual smoke test

**Step 1: Start backend**

Run: `cd backend && uvicorn app.main:app --reload --port 8000`

**Step 2: Start frontend**

Run: `cd frontend && npm run dev`

**Step 3: Test the flow**

1. Navigate to the Transactions page
2. Click "Add Transaction"
3. Fill in: today's date, "Test coffee", $5.50, pick an account, EXPENSE type, Restaurants category
4. Submit — should appear in the list
5. Try submitting the exact same form again — should see 409 duplicate error
6. Try with a different amount or date — should succeed

**Step 4: Commit any fixes if needed**
