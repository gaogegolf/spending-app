'use client';

import { useState, useEffect } from 'react';
import { getAccounts, uploadFile, parseImport, commitImport, getImportStatus } from '@/lib/api';
import { Account, ImportRecord } from '@/lib/types';

export default function ImportsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [importRecord, setImportRecord] = useState<ImportRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<'select' | 'upload' | 'processing' | 'complete'>('select');

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

  async function handleFileUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedAccount || !file) {
      setError('Please select an account and file');
      return;
    }

    try {
      setImporting(true);
      setError(null);
      setStep('upload');

      // Upload file
      const uploadResult = await uploadFile(selectedAccount, file);
      setImportRecord(uploadResult);

      // Parse file
      setStep('processing');
      const parseResult = await parseImport(uploadResult.id);
      setImportRecord(parseResult);

      // Check if parsing was successful
      if (parseResult.status === 'FAILED') {
        setError(parseResult.error_message || 'Failed to parse file');
        setStep('select');
        return;
      }

      // Commit import
      const commitResult = await commitImport(uploadResult.id);
      setImportRecord(commitResult);
      setStep('complete');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
      setStep('select');
    } finally {
      setImporting(false);
    }
  }

  function resetImport() {
    setFile(null);
    setSelectedAccount('');
    setImportRecord(null);
    setError(null);
    setStep('select');
  }

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Import Transactions</h1>

      {/* Error Message */}
      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Step 1: Select Account and File */}
      {step === 'select' && (
        <div className="bg-white shadow rounded-lg p-6">
          <form onSubmit={handleFileUpload}>
            {/* Account Selection */}
            <div className="mb-6">
              <label htmlFor="account" className="block text-sm font-medium text-gray-700 mb-2">
                Select Account
              </label>
              <select
                id="account"
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                required
              >
                <option value="">Choose an account...</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name} ({account.account_type})
                  </option>
                ))}
              </select>
            </div>

            {/* File Upload */}
            <div className="mb-6">
              <label htmlFor="file" className="block text-sm font-medium text-gray-700 mb-2">
                Upload File
              </label>
              <input
                type="file"
                id="file"
                accept=".csv,.pdf"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="block w-full text-sm text-gray-500
                  file:mr-4 file:py-2 file:px-4
                  file:rounded-md file:border-0
                  file:text-sm file:font-semibold
                  file:bg-indigo-50 file:text-indigo-700
                  hover:file:bg-indigo-100"
                required
              />
              <p className="mt-2 text-sm text-gray-500">
                Supported formats: CSV, PDF (up to 10MB)
              </p>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={importing || !selectedAccount || !file}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {importing ? 'Importing...' : 'Import Transactions'}
            </button>
          </form>
        </div>
      )}

      {/* Step 2: Processing */}
      {(step === 'upload' || step === 'processing') && (
        <div className="bg-white shadow rounded-lg p-6">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
            <p className="text-gray-700 font-medium">
              {step === 'upload' ? 'Uploading file...' : 'Processing transactions...'}
            </p>
            <p className="text-sm text-gray-500 mt-2">This may take a moment</p>
          </div>
        </div>
      )}

      {/* Step 3: Complete */}
      {step === 'complete' && importRecord && (
        <div className="bg-white shadow rounded-lg p-6">
          <div className="text-center mb-6">
            <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100 mb-4">
              <svg
                className="h-6 w-6 text-green-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M5 13l4 4L19 7"
                />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-gray-900">Import Complete!</h3>
          </div>

          {/* Import Summary */}
          <div className="border-t border-gray-200 pt-4">
            <dl className="space-y-3">
              <div className="flex justify-between">
                <dt className="text-sm text-gray-500">File</dt>
                <dd className="text-sm font-medium text-gray-900">{importRecord.filename}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-gray-500">Transactions Imported</dt>
                <dd className="text-sm font-medium text-green-600">
                  {importRecord.transactions_imported}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-gray-500">Duplicates Skipped</dt>
                <dd className="text-sm font-medium text-gray-600">
                  {importRecord.transactions_duplicate}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-gray-500">Status</dt>
                <dd className="text-sm font-medium text-gray-900">{importRecord.status}</dd>
              </div>
            </dl>
          </div>

          {/* Actions */}
          <div className="mt-6 flex gap-3">
            <button
              onClick={resetImport}
              className="flex-1 py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
            >
              Import Another File
            </button>
            <a
              href="/transactions"
              className="flex-1 py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 text-center"
            >
              View Transactions
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
