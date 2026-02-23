'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  getAccounts,
  uploadFile,
  parseImport,
  commitImport,
  createAccount,
  uploadBrokerageStatement,
  parseBrokerageStatement,
  commitBrokerageImport,
} from '@/lib/api';
import { Account, ImportRecord, AccountType, BrokerageParseResult } from '@/lib/types';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

const BANK_ACCOUNT_TYPES: AccountType[] = ['CREDIT_CARD', 'CHECKING', 'SAVINGS', 'CASH', 'DIGITAL_WALLET', 'OTHER'];
const BROKERAGE_ACCOUNT_TYPES: AccountType[] = ['BROKERAGE', 'IRA_ROTH', 'IRA_TRADITIONAL', 'RETIREMENT_401K', 'STOCK_PLAN'];

type ImportType = 'transactions' | 'brokerage';

// Transaction parse result with detection info
interface TransactionParseResult {
  success: boolean;
  import_id: string;
  filename: string;
  source_type: string;
  detected_columns: any;
  transactions_preview: any[];
  total_count: number;
  duplicate_count: number;
  warnings: string[];
  errors?: string[];
  detected_institution: string | null;
  detected_account_type: string | null;
  detected_account_last4: string | null;
}

export default function ImportsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [files, setFiles] = useState<File[]>([]);
  const [importing, setImporting] = useState(false);
  const [importRecords, setImportRecords] = useState<ImportRecord[]>([]);
  const [currentFileIndex, setCurrentFileIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<'select' | 'upload' | 'processing' | 'preview' | 'complete'>('select');

  // Import type selection
  const [importType, setImportType] = useState<ImportType>('transactions');

  // Auto-detect mode (for transactions)
  const [autoDetectMode, setAutoDetectMode] = useState(true);
  const [transactionParseResult, setTransactionParseResult] = useState<TransactionParseResult | null>(null);
  const [transactionImportId, setTransactionImportId] = useState<string | null>(null);

  // Brokerage import state
  const [brokerageParseResult, setBrokerageParseResult] = useState<BrokerageParseResult | null>(null);
  const [brokerageImportId, setBrokerageImportId] = useState<string | null>(null);
  const [brokerageResult, setBrokerageResult] = useState<{
    account_name: string;
    total_value: number;
    position_count: number;
  } | null>(null);

  // New account modal state
  const [showNewAccountModal, setShowNewAccountModal] = useState(false);
  const [newAccountName, setNewAccountName] = useState('');
  const [newAccountType, setNewAccountType] = useState<AccountType>('CREDIT_CARD');
  const [newAccountInstitution, setNewAccountInstitution] = useState('');
  const [newAccountLast4, setNewAccountLast4] = useState('');
  const [creatingAccount, setCreatingAccount] = useState(false);

  useEffect(() => {
    loadAccounts();
  }, []);

  async function loadAccounts() {
    try {
      const data = await getAccounts();
      setAccounts(data.accounts || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load accounts');
    }
  }

  async function handleCreateAccount(e: React.FormEvent) {
    e.preventDefault();

    if (!newAccountName.trim()) {
      setError('Account name is required');
      return;
    }

    try {
      setCreatingAccount(true);
      setError(null);

      const newAccount = await createAccount({
        name: newAccountName.trim(),
        account_type: newAccountType,
        institution: newAccountInstitution.trim() || undefined,
        account_number_last4: newAccountLast4.trim() || undefined,
      });

      setAccounts([...accounts, newAccount]);
      setSelectedAccount(newAccount.id);

      setShowNewAccountModal(false);
      setNewAccountName('');
      setNewAccountType('CREDIT_CARD');
      setNewAccountInstitution('');
      setNewAccountLast4('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create account');
    } finally {
      setCreatingAccount(false);
    }
  }

  function handleAccountChange(value: string) {
    if (value === '__new__') {
      // Set default account type based on import type
      setNewAccountType(importType === 'brokerage' ? 'BROKERAGE' : 'CREDIT_CARD');
      setShowNewAccountModal(true);
    } else {
      setSelectedAccount(value);
    }
  }

  // Handle transaction import with auto-detect support
  async function handleTransactionImport() {
    if (files.length === 0) {
      setError('Please select at least one file');
      return;
    }

    // In non-auto-detect mode, require account selection
    if (!autoDetectMode && !selectedAccount) {
      setError('Please select an account');
      return;
    }

    try {
      setImporting(true);
      setError(null);
      setImportRecords([]);
      setStep('upload');

      // For single file, show preview (allows user to verify account match)
      if (files.length === 1) {
        const file = files[0];
        const uploadResult = await uploadFile(autoDetectMode ? null : selectedAccount, file);
        setTransactionImportId(uploadResult.id);

        setStep('processing');
        const parseResult = await parseImport(uploadResult.id) as TransactionParseResult;

        if (parseResult.success === false || parseResult.errors?.length) {
          setError(parseResult.errors?.join(', ') || 'Failed to parse file');
          setStep('select');
          return;
        }

        setTransactionParseResult(parseResult);
        setStep('preview');
        return;
      }

      // For multiple files, process directly
      const results: ImportRecord[] = [];

      for (let i = 0; i < files.length; i++) {
        setCurrentFileIndex(i);
        const file = files[i];

        try {
          const uploadResult = await uploadFile(autoDetectMode ? null : selectedAccount, file);
          setStep('processing');
          const parseResult = await parseImport(uploadResult.id);

          if (parseResult.success === false || parseResult.errors?.length > 0) {
            const errorMsg = parseResult.errors ? parseResult.errors.join(', ') : 'Failed to parse file';
            results.push({
              id: uploadResult.id,
              filename: file.name,
              status: 'FAILED',
              error_message: errorMsg,
              transactions_imported: 0,
              transactions_duplicate: 0,
            } as ImportRecord);
            continue;
          }

          // Commit with auto-create if in auto-detect mode
          const commitResult = await commitImport(uploadResult.id, autoDetectMode ? {
            createAccount: true
          } : {
            accountId: selectedAccount
          });
          results.push(commitResult);
        } catch (err) {
          results.push({
            id: '',
            filename: file.name,
            status: 'FAILED',
            error_message: err instanceof Error ? err.message : 'Import failed',
            transactions_imported: 0,
            transactions_duplicate: 0,
          } as ImportRecord);
        }
      }

      setImportRecords(results);
      setStep('complete');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
      setStep('select');
    } finally {
      setImporting(false);
    }
  }

  // Commit transaction import from preview (auto-detect mode)
  async function handleTransactionCommit() {
    if (!transactionImportId) return;

    try {
      setImporting(true);
      setError(null);

      // If user selected an existing account, use it; otherwise auto-create
      const commitResult = await commitImport(transactionImportId, selectedAccount ? {
        accountId: selectedAccount,
        createAccount: false
      } : {
        createAccount: true
      });

      setImportRecords([commitResult]);
      setStep('complete');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to commit import');
    } finally {
      setImporting(false);
    }
  }

  // Handle brokerage import with auto-detect support
  async function handleBrokerageImport() {
    if (files.length === 0) {
      setError('Please select a brokerage statement PDF');
      return;
    }

    // In non-auto-detect mode, require account selection
    if (!autoDetectMode && !selectedAccount) {
      setError('Please select a brokerage account');
      return;
    }

    try {
      setImporting(true);
      setError(null);
      setStep('upload');

      const file = files[0];

      // Upload with optional account (undefined for auto-detect mode)
      const uploadResult = await uploadBrokerageStatement(file, autoDetectMode ? undefined : selectedAccount);
      setBrokerageImportId(uploadResult.import_id);

      // Parse and get preview
      setStep('processing');
      const parseResult = await parseBrokerageStatement(uploadResult.import_id);
      setBrokerageParseResult(parseResult);

      // Auto-match to existing account by last4 + institution
      if (autoDetectMode && parseResult.account_identifier) {
        const last4 = parseResult.account_identifier.replace(/[^0-9A-Za-z]/g, '').slice(-4);
        const provider = (parseResult.provider || '').toLowerCase();
        const match = accounts.find(a =>
          a.account_number_last4 === last4 &&
          (a.institution || '').toLowerCase() === provider &&
          BROKERAGE_ACCOUNT_TYPES.includes(a.account_type as AccountType)
        );
        if (match) {
          setSelectedAccount(match.id);
        }
      }

      setStep('preview');

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to process brokerage statement');
      setStep('select');
    } finally {
      setImporting(false);
    }
  }

  async function handleBrokerageCommit() {
    if (!brokerageImportId) return;

    try {
      setImporting(true);
      setError(null);

      // If user selected an existing account, use it; otherwise auto-create
      const result = await commitBrokerageImport(brokerageImportId, selectedAccount ? {
        accountId: selectedAccount,
        createAccount: false
      } : {
        createAccount: true
      });
      setBrokerageResult({
        account_name: result.account_name,
        total_value: result.total_value,
        position_count: result.position_count,
      });
      setStep('complete');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to commit import');
    } finally {
      setImporting(false);
    }
  }

  async function handleFileUpload(e: React.FormEvent) {
    e.preventDefault();
    if (importType === 'transactions') {
      await handleTransactionImport();
    } else {
      await handleBrokerageImport();
    }
  }

  function resetImport() {
    setFiles([]);
    setSelectedAccount('');
    setImportRecords([]);
    setCurrentFileIndex(0);
    setError(null);
    setStep('select');
    setBrokerageParseResult(null);
    setBrokerageImportId(null);
    setBrokerageResult(null);
    setTransactionParseResult(null);
    setTransactionImportId(null);
  }

  function formatCurrency(value: number): string {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(value);
  }

  function formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  function getAccountTypeLabel(type: string): string {
    const labels: Record<string, string> = {
      // Bank account types
      'CREDIT_CARD': 'Credit Card',
      'CHECKING': 'Checking',
      'SAVINGS': 'Savings',
      'OTHER': 'Other',
      'CASH': 'Cash',
      'DIGITAL_WALLET': 'Digital Wallet',
      // Brokerage account types
      'BROKERAGE': 'Brokerage',
      'IRA_ROTH': 'Roth IRA',
      'IRA_TRADITIONAL': 'Traditional IRA',
      'RETIREMENT_401K': '401(k)',
      'STOCK_PLAN': 'Stock Plan (RSU/ESPP)',
    };
    return labels[type] || type;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Page Header */}
        <div className="mb-10">
          <div className="flex items-center gap-4 mb-3">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg">
              <span className="text-2xl">📤</span>
            </div>
            <div>
              <h1 className="text-4xl font-black bg-gradient-to-r from-gray-900 via-indigo-900 to-purple-900 bg-clip-text text-transparent">
                Import Statements
              </h1>
              <p className="text-gray-600 mt-1">Upload bank statements or brokerage statements</p>
            </div>
          </div>
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

        {/* Step 1: Select Import Type, Account and File */}
        {step === 'select' && (
          <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-2xl border border-white/50 p-8">
            <form onSubmit={handleFileUpload}>
              {/* Import Type Selection */}
              <div className="mb-8">
                <label className="block text-base font-semibold text-gray-800 mb-3">
                  1. What are you importing?
                </label>
                <div className="grid grid-cols-2 gap-4">
                  <button
                    type="button"
                    onClick={() => { setImportType('transactions'); setSelectedAccount(''); }}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${
                      importType === 'transactions'
                        ? 'border-indigo-500 bg-indigo-50 shadow-md'
                        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-2xl">💳</span>
                      <span className="font-semibold text-gray-900">Bank Statement</span>
                    </div>
                    <p className="text-sm text-gray-600">
                      Credit cards, checking, savings accounts (CSV or PDF)
                    </p>
                  </button>
                  <button
                    type="button"
                    onClick={() => { setImportType('brokerage'); setSelectedAccount(''); }}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${
                      importType === 'brokerage'
                        ? 'border-emerald-500 bg-emerald-50 shadow-md'
                        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-2xl">📈</span>
                      <span className="font-semibold text-gray-900">Brokerage Statement</span>
                    </div>
                    <p className="text-sm text-gray-600">
                      Fidelity, Schwab, Vanguard, IBKR, Wealthfront, Equatex (PDF)
                    </p>
                  </button>
                </div>
              </div>

              {/* Account Selection */}
              <div className="mb-8">
                <label htmlFor="account" className="block text-base font-semibold text-gray-800 mb-3">
                  2. Account
                </label>

                {/* Auto-detect toggle */}
                <div className="mb-4 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => { setAutoDetectMode(true); setSelectedAccount(''); }}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                      autoDetectMode
                        ? importType === 'brokerage'
                          ? 'bg-emerald-100 text-emerald-800 border-2 border-emerald-500'
                          : 'bg-indigo-100 text-indigo-800 border-2 border-indigo-500'
                        : 'bg-gray-100 text-gray-600 border-2 border-transparent hover:bg-gray-200'
                    }`}
                  >
                    Auto-detect
                  </button>
                  <button
                    type="button"
                    onClick={() => setAutoDetectMode(false)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                      !autoDetectMode
                        ? importType === 'brokerage'
                          ? 'bg-emerald-100 text-emerald-800 border-2 border-emerald-500'
                          : 'bg-indigo-100 text-indigo-800 border-2 border-indigo-500'
                        : 'bg-gray-100 text-gray-600 border-2 border-transparent hover:bg-gray-200'
                    }`}
                  >
                    Choose account
                  </button>
                </div>

                {/* Show auto-detect info or account selector */}
                {autoDetectMode ? (
                  <div className={`rounded-lg p-4 ${
                    importType === 'brokerage'
                      ? 'bg-emerald-50 border border-emerald-200'
                      : 'bg-indigo-50 border border-indigo-200'
                  }`}>
                    <div className="flex items-start gap-3">
                      <span className="text-2xl">🔍</span>
                      <div>
                        <p className={`font-medium ${importType === 'brokerage' ? 'text-emerald-900' : 'text-indigo-900'}`}>
                          {importType === 'brokerage' ? 'Auto-detect provider & account' : 'Auto-detect bank & account'}
                        </p>
                        <p className={`text-sm mt-1 ${importType === 'brokerage' ? 'text-emerald-700' : 'text-indigo-700'}`}>
                          {importType === 'brokerage'
                            ? "We'll automatically detect your brokerage from the statement and create an account for you. Supports Fidelity, Schwab, Vanguard, IBKR, Wealthfront, and Equatex."
                            : "We'll automatically detect your bank from the statement and create an account for you. Supports Chase, Amex, Wells Fargo, Capital One, Ally Bank, Fidelity, and more."
                          }
                        </p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <>
                    <select
                      id="account"
                      value={selectedAccount}
                      onChange={(e) => handleAccountChange(e.target.value)}
                      className={`block w-full px-4 py-3 border-2 border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 text-base transition-all ${
                        importType === 'brokerage'
                          ? 'focus:ring-emerald-500 focus:border-emerald-500'
                          : 'focus:ring-indigo-500 focus:border-indigo-500'
                      }`}
                      required={importType === 'brokerage' || !autoDetectMode}
                    >
                      <option value="">Choose an account...</option>
                      {importType === 'transactions'
                        ? accounts.filter(a => !BROKERAGE_ACCOUNT_TYPES.includes(a.account_type as AccountType)).map((account) => (
                            <option key={account.id} value={account.id}>
                              {account.name} ({account.account_type.replace('_', ' ')})
                            </option>
                          ))
                        : accounts.filter(a => BROKERAGE_ACCOUNT_TYPES.includes(a.account_type as AccountType)).map((account) => (
                            <option key={account.id} value={account.id}>
                              {account.name} ({account.account_type.replace('_', ' ')})
                            </option>
                          ))
                      }
                      <option value="__new__" className={importType === 'brokerage' ? 'font-semibold text-emerald-600' : 'font-semibold text-indigo-600'}>
                        + Create New Account
                      </option>
                    </select>
                    {importType === 'brokerage' && accounts.filter(a => BROKERAGE_ACCOUNT_TYPES.includes(a.account_type as AccountType)).length === 0 && (
                      <p className="mt-2 text-sm text-amber-600">
                        No brokerage accounts yet. Create one first to import statements.
                      </p>
                    )}
                  </>
                )}
              </div>

              {/* File Upload */}
              <div className="mb-8">
                <label htmlFor="file" className="block text-base font-semibold text-gray-800 mb-3">
                  3. Upload {importType === 'brokerage' ? 'Statement' : 'File'}
                </label>
                <div className={`border-2 border-dashed rounded-lg p-6 hover:border-opacity-70 transition-colors ${
                  importType === 'brokerage' ? 'border-emerald-300 hover:border-emerald-400' : 'border-gray-300 hover:border-indigo-400'
                }`}>
                  <input
                    type="file"
                    id="file"
                    accept={importType === 'brokerage' ? '.pdf' : '.csv,.pdf'}
                    multiple={importType === 'transactions'}
                    onChange={(e) => setFiles(e.target.files ? Array.from(e.target.files) : [])}
                    className={`block w-full text-base text-gray-700
                      file:mr-4 file:py-3 file:px-6
                      file:rounded-lg file:border-0
                      file:text-sm file:font-semibold
                      file:cursor-pointer file:transition-all
                      ${importType === 'brokerage'
                        ? 'file:bg-gradient-to-r file:from-emerald-500 file:to-teal-600 file:text-white hover:file:from-emerald-600 hover:file:to-teal-700'
                        : 'file:bg-gradient-to-r file:from-indigo-500 file:to-purple-600 file:text-white hover:file:from-indigo-600 hover:file:to-purple-700'
                      }`}
                    required
                  />
                  {files.length > 0 && (
                    <div className="mt-3 text-sm text-gray-700">
                      <strong>{files.length}</strong> file{files.length !== 1 ? 's' : ''} selected
                      {files.map((f, i) => (
                        <div key={i} className="text-gray-500 mt-1">• {f.name}</div>
                      ))}
                    </div>
                  )}
                  <p className="mt-3 text-sm text-gray-500 flex items-center">
                    <span className="mr-2">📄</span>
                    {importType === 'brokerage'
                      ? 'Supported: PDF statements from Fidelity, Schwab, Vanguard, IBKR, Wealthfront, Equatex'
                      : 'Supported formats: CSV, PDF (up to 10MB each). You can select multiple files.'
                    }
                  </p>
                </div>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={
                  importing ||
                  files.length === 0 ||
                  (importType === 'brokerage' && !autoDetectMode && !selectedAccount) ||
                  (importType === 'transactions' && !autoDetectMode && !selectedAccount)
                }
                className={`w-full flex justify-center items-center py-4 px-6 border border-transparent rounded-lg shadow-lg text-base font-semibold text-white focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:from-gray-400 disabled:to-gray-400 disabled:cursor-not-allowed transition-all transform hover:scale-105 ${
                  importType === 'brokerage'
                    ? 'bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 focus:ring-emerald-500'
                    : 'bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 focus:ring-indigo-500'
                }`}
              >
                {importing ? (
                  <>
                    <span className="animate-spin mr-2">⏳</span>
                    Processing...
                  </>
                ) : (
                  <>
                    <span className="mr-2">{importType === 'brokerage' ? '📈' : '🚀'}</span>
                    {importType === 'brokerage'
                      ? 'Import Brokerage Statement'
                      : autoDetectMode
                        ? (files.length > 0 ? `Auto Import ${files.length} File${files.length !== 1 ? 's' : ''}` : 'Auto Import')
                        : (files.length > 0 ? `Import ${files.length} File${files.length !== 1 ? 's' : ''}` : 'Import Transactions')
                    }
                  </>
                )}
              </button>
            </form>
          </div>
        )}

        {/* Step 2: Processing */}
        {(step === 'upload' || step === 'processing') && (
          <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-2xl border border-white/50 p-8">
            <div className="text-center">
              <div className={`animate-spin rounded-full h-16 w-16 border-4 mx-auto mb-6 ${
                importType === 'brokerage'
                  ? 'border-emerald-200 border-t-emerald-600'
                  : 'border-indigo-200 border-t-indigo-600'
              }`}></div>
              <p className="text-xl text-gray-800 font-semibold mb-2">
                {step === 'upload' ? 'Uploading...' : 'Processing...'}
              </p>
              {importType === 'transactions' && (
                <>
                  <p className="text-base text-gray-600 mb-4">
                    Processing file {currentFileIndex + 1} of {files.length}
                  </p>
                  <div className="w-full bg-gray-200 rounded-full h-2 max-w-md mx-auto">
                    <div
                      className="bg-gradient-to-r from-indigo-500 to-purple-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${((currentFileIndex + 1) / files.length) * 100}%` }}
                    ></div>
                  </div>
                </>
              )}
              {importType === 'brokerage' && (
                <p className="text-base text-gray-600">
                  Detecting provider and extracting holdings...
                </p>
              )}
              <p className="text-sm text-gray-500 mt-4">This may take a moment...</p>
            </div>
          </div>
        )}

        {/* Transaction Preview Step (Auto-detect mode) */}
        {step === 'preview' && transactionParseResult && (
          <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-2xl border border-white/50 p-8">
            <h2 className="text-xl font-bold text-gray-900 mb-6">Review Import</h2>

            {/* Detection Summary */}
            <div className="bg-indigo-50 rounded-xl p-5 mb-6 border border-indigo-200">
              <div className="flex items-center justify-between">
                <div>
                  {transactionParseResult.detected_institution ? (
                    <>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xl">🔍</span>
                        <span className="text-sm text-indigo-600 font-medium">Detected</span>
                      </div>
                      <p className="font-semibold text-indigo-800 text-lg">
                        {transactionParseResult.detected_institution} {transactionParseResult.detected_account_type?.replace('_', ' ')}
                      </p>
                    </>
                  ) : (
                    <p className="font-semibold text-gray-800 text-lg">
                      Unknown Institution
                    </p>
                  )}
                  <p className="text-sm text-indigo-600 mt-1">
                    {transactionParseResult.filename}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-3xl font-bold text-indigo-800">
                    {transactionParseResult.total_count}
                  </p>
                  <p className="text-sm text-indigo-600">transactions</p>
                </div>
              </div>
            </div>

            {/* Warnings */}
            {transactionParseResult.warnings && transactionParseResult.warnings.length > 0 && (
              <div className="bg-amber-50 rounded-lg p-4 mb-6 border border-amber-200">
                <p className="font-semibold text-amber-800 mb-2">Warnings</p>
                {transactionParseResult.warnings.map((warning, i) => (
                  <p key={i} className="text-sm text-amber-700">{warning}</p>
                ))}
              </div>
            )}

            {/* Account Mismatch Warning */}
            {selectedAccount && (() => {
              const selectedAccountObj = accounts.find(a => a.id === selectedAccount);
              if (selectedAccountObj?.account_number_last4 &&
                  transactionParseResult.detected_account_last4 &&
                  selectedAccountObj.account_number_last4 !== transactionParseResult.detected_account_last4) {
                return (
                  <div className="bg-red-50 rounded-lg p-4 mb-6 border border-red-200">
                    <p className="font-semibold text-red-800 mb-2">⚠️ Account Number Mismatch</p>
                    <p className="text-sm text-red-700">
                      The statement appears to be for an account ending in <strong>...{transactionParseResult.detected_account_last4}</strong>,
                      but you selected <strong>{selectedAccountObj.name}</strong> which ends in <strong>...{selectedAccountObj.account_number_last4}</strong>.
                    </p>
                    <p className="text-sm text-red-700 mt-2">
                      Please verify you&apos;re importing to the correct account, or select &quot;Auto-create new account&quot; to create a new account.
                    </p>
                  </div>
                );
              }
              return null;
            })()}

            {/* Transaction Preview */}
            <div className="border rounded-xl overflow-hidden mb-6">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">Date</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">Description</th>
                    <th className="text-right px-4 py-3 font-semibold text-gray-700">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {transactionParseResult.transactions_preview.slice(0, 10).map((txn, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-600">{txn.date}</td>
                      <td className="px-4 py-3 text-gray-900 truncate max-w-[300px]">
                        {txn.description_raw || txn.merchant_normalized}
                      </td>
                      <td className="px-4 py-3 text-right font-medium text-gray-900">
                        {formatCurrency(txn.amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {transactionParseResult.transactions_preview.length > 10 && (
                <div className="bg-gray-50 px-4 py-2 text-sm text-gray-500 text-center border-t">
                  + {transactionParseResult.total_count - 10} more transactions
                </div>
              )}
            </div>

            {/* Account Selection Override */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Import to account (optional - leave blank to auto-create)
              </label>
              <select
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                className="block w-full px-4 py-3 border-2 border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-base"
              >
                <option value="">Auto-create new account</option>
                {accounts.filter(a => !BROKERAGE_ACCOUNT_TYPES.includes(a.account_type as AccountType)).map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name} ({account.account_type.replace('_', ' ')})
                  </option>
                ))}
              </select>
              {!selectedAccount && transactionParseResult.detected_institution && (
                <p className="mt-2 text-sm text-gray-500">
                  Will create: {transactionParseResult.detected_institution} {transactionParseResult.detected_account_type?.replace('_', ' ')}
                </p>
              )}
            </div>

            {/* Duplicate Info */}
            {transactionParseResult.duplicate_count > 0 && (
              <div className="bg-gray-50 rounded-lg p-4 mb-6 border border-gray-200">
                <p className="text-sm text-gray-600">
                  <strong>{transactionParseResult.duplicate_count}</strong> duplicate transactions will be skipped
                </p>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-4">
              <button
                onClick={resetImport}
                className="flex-1 py-3 px-6 border-2 border-gray-300 rounded-lg text-base font-semibold text-gray-700 bg-white hover:bg-gray-50 transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleTransactionCommit}
                disabled={importing}
                className="flex-1 py-3 px-6 border border-transparent rounded-lg text-base font-semibold text-white bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 disabled:from-gray-400 disabled:to-gray-400 transition-all"
              >
                {importing ? 'Importing...' : 'Confirm Import'}
              </button>
            </div>
          </div>
        )}

        {/* Brokerage Preview Step */}
        {step === 'preview' && brokerageParseResult && (
          <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-2xl border border-white/50 p-8">
            <h2 className="text-xl font-bold text-gray-900 mb-6">Review Holdings</h2>

            {/* Summary Card */}
            <div className="bg-emerald-50 rounded-xl p-5 mb-6 border border-emerald-200">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-semibold text-emerald-800 text-lg">
                    {brokerageParseResult.provider.charAt(0).toUpperCase() + brokerageParseResult.provider.slice(1)} Statement
                  </p>
                  <p className="text-sm text-emerald-600 mt-1">
                    {getAccountTypeLabel(brokerageParseResult.account_type)} • {brokerageParseResult.account_identifier}
                  </p>
                  {brokerageParseResult.statement_date && (
                    <p className="text-sm text-emerald-600">
                      As of {formatDate(brokerageParseResult.statement_date)}
                    </p>
                  )}
                </div>
                <div className="text-right">
                  <p className="text-3xl font-bold text-emerald-800">
                    {formatCurrency(brokerageParseResult.total_value)}
                  </p>
                  {brokerageParseResult.is_reconciled ? (
                    <span className="text-xs text-emerald-600 font-medium">Reconciled</span>
                  ) : (
                    <span className="text-xs text-amber-600 font-medium">
                      Diff: {formatCurrency(brokerageParseResult.reconciliation_diff)}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Provider Mismatch Warning */}
            {!autoDetectMode && selectedAccount && (() => {
              const selectedAccountData = accounts.find(a => a.id === selectedAccount);
              const detectedProvider = brokerageParseResult.provider.toLowerCase();
              const accountInstitution = selectedAccountData?.institution?.toLowerCase() || '';
              const isMismatch = accountInstitution && !accountInstitution.includes(detectedProvider) && !detectedProvider.includes(accountInstitution);

              if (isMismatch) {
                return (
                  <div className="bg-red-50 rounded-lg p-4 mb-6 border-2 border-red-300">
                    <div className="flex items-start gap-3">
                      <span className="text-2xl">⚠️</span>
                      <div>
                        <p className="font-bold text-red-800">Provider Mismatch Detected!</p>
                        <p className="text-sm text-red-700 mt-1">
                          This statement is from <strong>{brokerageParseResult.provider.charAt(0).toUpperCase() + brokerageParseResult.provider.slice(1)}</strong>,
                          but you selected <strong>{selectedAccountData?.name}</strong> ({selectedAccountData?.institution}).
                        </p>
                        <p className="text-sm text-red-700 mt-2">
                          If you continue, the holdings will be imported into the wrong account.
                          Consider using <strong>Auto-detect</strong> mode or selecting the correct account.
                        </p>
                      </div>
                    </div>
                  </div>
                );
              }
              return null;
            })()}

            {/* Warnings */}
            {brokerageParseResult.warnings && brokerageParseResult.warnings.length > 0 && (
              <div className="bg-amber-50 rounded-lg p-4 mb-6 border border-amber-200">
                <p className="font-semibold text-amber-800 mb-2">Warnings</p>
                {brokerageParseResult.warnings.map((warning, i) => (
                  <p key={i} className="text-sm text-amber-700">{warning}</p>
                ))}
              </div>
            )}

            {/* Positions Preview */}
            <div className="border rounded-xl overflow-hidden mb-6">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">Symbol</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">Security</th>
                    <th className="text-right px-4 py-3 font-semibold text-gray-700">Shares</th>
                    <th className="text-right px-4 py-3 font-semibold text-gray-700">Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {brokerageParseResult.positions.slice(0, 10).map((pos, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono font-semibold text-gray-900">{pos.symbol || '-'}</td>
                      <td className="px-4 py-3 text-gray-600 truncate max-w-[200px]">{pos.security_name}</td>
                      <td className="px-4 py-3 text-right text-gray-900">
                        {pos.quantity?.toLocaleString(undefined, { maximumFractionDigits: 2 }) || '-'}
                      </td>
                      <td className="px-4 py-3 text-right font-semibold text-gray-900">
                        {formatCurrency(pos.market_value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {brokerageParseResult.positions.length > 10 && (
                <div className="bg-gray-50 px-4 py-2 text-sm text-gray-500 text-center border-t">
                  + {brokerageParseResult.positions.length - 10} more positions
                </div>
              )}
            </div>

            {/* Account Selection Override */}
            {autoDetectMode && (
              <div className="mb-6 p-4 bg-gray-50 rounded-xl border border-gray-200">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Import to account
                </label>
                <select
                  value={selectedAccount}
                  onChange={(e) => setSelectedAccount(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent text-base"
                >
                  <option value="">Auto-create: {brokerageParseResult.provider.charAt(0).toUpperCase() + brokerageParseResult.provider.slice(1)} {getAccountTypeLabel(brokerageParseResult.account_type)}</option>
                  {accounts.filter(a => BROKERAGE_ACCOUNT_TYPES.includes(a.account_type as AccountType)).map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name} ({account.institution || 'No institution'})
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-2">
                  Leave as auto-create or select an existing account to add positions to
                </p>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-4">
              <button
                onClick={resetImport}
                className="flex-1 py-3 px-6 border-2 border-gray-300 rounded-lg text-base font-semibold text-gray-700 bg-white hover:bg-gray-50 transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleBrokerageCommit}
                disabled={importing}
                className="flex-1 py-3 px-6 border border-transparent rounded-lg text-base font-semibold text-white bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 disabled:from-gray-400 disabled:to-gray-400 transition-all"
              >
                {importing ? 'Importing...' : 'Confirm Import'}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Complete (Transactions) */}
        {step === 'complete' && importType === 'transactions' && importRecords.length > 0 && (
          <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-2xl border border-white/50 p-8">
            <div className="text-center mb-8">
              <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-green-100 mb-4">
                <svg className="h-8 w-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 className="text-2xl font-bold text-gray-900">Import Complete!</h3>
              <p className="text-gray-600 mt-2">
                Processed {importRecords.length} file{importRecords.length !== 1 ? 's' : ''}
              </p>
            </div>

            {/* Import Summary */}
            <div className="space-y-4 mb-8">
              {importRecords.map((record, index) => (
                <div key={index} className={`border rounded-lg p-4 ${
                  record.status === 'FAILED' ? 'border-red-200 bg-red-50' : 'border-green-200 bg-green-50'
                }`}>
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex-1">
                      <div className="font-semibold text-gray-900 mb-1">{record.filename}</div>
                      {record.account_name && (
                        <div className="text-sm text-indigo-600 font-medium mb-1">
                          → {record.account_name}
                        </div>
                      )}
                      <div className={`text-sm font-medium ${
                        record.status === 'FAILED' ? 'text-red-600' : 'text-green-600'
                      }`}>
                        {record.status}
                      </div>
                    </div>
                    {record.status !== 'FAILED' && (
                      <div className="text-right">
                        <div className="text-lg font-bold text-green-600">+{record.transactions_imported}</div>
                        <div className="text-xs text-gray-500">imported</div>
                      </div>
                    )}
                  </div>
                  {record.status === 'FAILED' && record.error_message && (
                    <div className="text-sm text-red-700 mt-2">Error: {record.error_message}</div>
                  )}
                  {record.status !== 'FAILED' && (
                    <div className="text-sm text-gray-600">{record.transactions_duplicate} duplicates skipped</div>
                  )}
                </div>
              ))}
            </div>

            {/* Total Summary */}
            <div className="border-t border-gray-200 pt-6 mb-6">
              <div className="grid grid-cols-2 gap-4 text-center">
                <div>
                  <div className="text-3xl font-bold text-green-600">
                    {importRecords.reduce((sum, r) => sum + r.transactions_imported, 0)}
                  </div>
                  <div className="text-sm text-gray-600 mt-1">Total Imported</div>
                </div>
                <div>
                  <div className="text-3xl font-bold text-gray-600">
                    {importRecords.reduce((sum, r) => sum + r.transactions_duplicate, 0)}
                  </div>
                  <div className="text-sm text-gray-600 mt-1">Total Duplicates</div>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-4">
              <button
                onClick={resetImport}
                className="flex-1 py-3 px-6 border-2 border-gray-300 rounded-lg text-base font-semibold text-gray-700 bg-white hover:bg-gray-50 transition-all"
              >
                Import More Files
              </button>
              <a
                href={(() => {
                  // If all imports went to the same account, filter by it
                  const accountIds = importRecords
                    .filter(r => r.status !== 'FAILED' && r.account_id)
                    .map(r => r.account_id);
                  const uniqueAccountIds = [...new Set(accountIds)];
                  if (uniqueAccountIds.length === 1 && uniqueAccountIds[0]) {
                    return `/transactions?account_id=${uniqueAccountIds[0]}`;
                  }
                  return '/transactions';
                })()}
                className="flex-1 py-3 px-6 border border-transparent rounded-lg text-base font-semibold text-white bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-center transition-all"
              >
                View Transactions
              </a>
            </div>
          </div>
        )}

        {/* Step 3: Complete (Brokerage) */}
        {step === 'complete' && importType === 'brokerage' && brokerageResult && (
          <div className="bg-white/70 backdrop-blur-xl shadow-2xl rounded-2xl border border-white/50 p-8">
            <div className="text-center mb-8">
              <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-emerald-100 mb-4">
                <svg className="h-8 w-8 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 className="text-2xl font-bold text-gray-900">Import Complete!</h3>
              <p className="text-gray-600 mt-2">Holdings imported successfully</p>
            </div>

            {/* Summary */}
            <div className="bg-emerald-50 rounded-xl p-6 mb-8 border border-emerald-200">
              <div className="text-center">
                <p className="text-lg font-semibold text-emerald-800 mb-2">{brokerageResult.account_name}</p>
                <p className="text-4xl font-bold text-emerald-700 mb-2">
                  {formatCurrency(brokerageResult.total_value)}
                </p>
                <p className="text-sm text-emerald-600">
                  {brokerageResult.position_count} positions imported
                </p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-4">
              <button
                onClick={resetImport}
                className="flex-1 py-3 px-6 border-2 border-gray-300 rounded-lg text-base font-semibold text-gray-700 bg-white hover:bg-gray-50 transition-all"
              >
                Import More
              </button>
              <a
                href="/net-worth"
                className="flex-1 py-3 px-6 border border-transparent rounded-lg text-base font-semibold text-white bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-center transition-all"
              >
                View Net Worth
              </a>
            </div>
          </div>
        )}

        {/* New Account Modal */}
        {showNewAccountModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-gray-900">Create New Account</h2>
                <button
                  onClick={() => setShowNewAccountModal(false)}
                  className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
                >
                  &times;
                </button>
              </div>

              <form onSubmit={handleCreateAccount}>
                <div className="mb-4">
                  <label htmlFor="new-account-name" className="block text-sm font-medium text-gray-700 mb-1">
                    Account Name *
                  </label>
                  <input
                    type="text"
                    id="new-account-name"
                    value={newAccountName}
                    onChange={(e) => setNewAccountName(e.target.value)}
                    placeholder="e.g., Amex Platinum Card"
                    className="block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    required
                  />
                </div>

                <div className="mb-4">
                  <label htmlFor="new-account-type" className="block text-sm font-medium text-gray-700 mb-1">
                    Account Type *
                  </label>
                  <select
                    id="new-account-type"
                    value={newAccountType}
                    onChange={(e) => setNewAccountType(e.target.value as AccountType)}
                    className={`block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 ${
                      importType === 'brokerage' ? 'focus:ring-emerald-500 focus:border-emerald-500' : 'focus:ring-indigo-500 focus:border-indigo-500'
                    }`}
                    required
                  >
                    {(importType === 'brokerage' ? BROKERAGE_ACCOUNT_TYPES : BANK_ACCOUNT_TYPES).map((type) => (
                      <option key={type} value={type}>
                        {getAccountTypeLabel(type)}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="mb-4">
                  <label htmlFor="new-account-institution" className="block text-sm font-medium text-gray-700 mb-1">
                    Institution
                  </label>
                  <input
                    type="text"
                    id="new-account-institution"
                    value={newAccountInstitution}
                    onChange={(e) => setNewAccountInstitution(e.target.value)}
                    placeholder="e.g., American Express"
                    className="block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                </div>

                <div className="mb-6">
                  <label htmlFor="new-account-last4" className="block text-sm font-medium text-gray-700 mb-1">
                    Last 4 Digits
                  </label>
                  <input
                    type="text"
                    id="new-account-last4"
                    value={newAccountLast4}
                    onChange={(e) => setNewAccountLast4(e.target.value.replace(/\D/g, '').slice(0, 4))}
                    placeholder="e.g., 1007"
                    maxLength={4}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                </div>

                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setShowNewAccountModal(false)}
                    className="flex-1 py-2 px-4 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={creatingAccount || !newAccountName.trim()}
                    className={`flex-1 py-2 px-4 border border-transparent rounded-lg text-sm font-medium text-white disabled:bg-gray-400 disabled:cursor-not-allowed ${
                      importType === 'brokerage' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-indigo-600 hover:bg-indigo-700'
                    }`}
                  >
                    {creatingAccount ? 'Creating...' : 'Create Account'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
