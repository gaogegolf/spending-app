'use client';

import { useState, useEffect } from 'react';
import { getAccounts, uploadFile, parseImport, commitImport, getImportStatus } from '@/lib/api';
import { Account, ImportRecord } from '@/lib/types';

export default function ImportsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [files, setFiles] = useState<File[]>([]);
  const [importing, setImporting] = useState(false);
  const [importRecords, setImportRecords] = useState<ImportRecord[]>([]);
  const [currentFileIndex, setCurrentFileIndex] = useState(0);
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

    console.log('Form submitted', { selectedAccount, filesCount: files.length });

    if (!selectedAccount || files.length === 0) {
      setError('Please select an account and at least one file');
      return;
    }

    try {
      setImporting(true);
      setError(null);
      setImportRecords([]);
      setStep('upload');

      const results: ImportRecord[] = [];

      // Process each file sequentially
      for (let i = 0; i < files.length; i++) {
        setCurrentFileIndex(i);
        const file = files[i];

        console.log(`Processing file ${i + 1}/${files.length}:`, file.name);

        try {
          // Upload file
          console.log('Uploading file...');
          const uploadResult = await uploadFile(selectedAccount, file);
          console.log('Upload result:', uploadResult);

          // Parse file
          setStep('processing');
          console.log('Parsing file...');
          const parseResult = await parseImport(uploadResult.id);
          console.log('Parse result:', parseResult);

          // Check if parsing was successful
          if (parseResult.status === 'FAILED') {
            console.error('Parse failed:', parseResult.error_message);
            results.push({
              ...parseResult,
              error_message: parseResult.error_message || 'Failed to parse file'
            });
            continue;
          }

          // Commit import
          console.log('Committing import...');
          const commitResult = await commitImport(uploadResult.id);
          console.log('Commit result:', commitResult);
          results.push(commitResult);
        } catch (err) {
          console.error('File processing error:', err);
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
      console.error('Import error:', err);
      setError(err instanceof Error ? err.message : 'Import failed');
      setStep('select');
    } finally {
      setImporting(false);
    }
  }

  function resetImport() {
    setFiles([]);
    setSelectedAccount('');
    setImportRecords([]);
    setCurrentFileIndex(0);
    setError(null);
    setStep('select');
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <h1 className="text-4xl font-bold text-gray-900 mb-3">Import Transactions</h1>
      <p className="text-gray-600 mb-8">Upload CSV or PDF files from your bank statements</p>

      {/* Error Message */}
      {error && (
        <div className="mb-6 bg-red-50 border-l-4 border-red-500 rounded-lg p-4 shadow-sm">
          <div className="flex items-start">
            <span className="text-red-500 text-xl mr-3">⚠️</span>
            <p className="text-red-800">{error}</p>
          </div>
        </div>
      )}

      {/* Step 1: Select Account and File */}
      {step === 'select' && (
        <div className="bg-white shadow-xl rounded-xl border border-gray-200 p-8">
          <form onSubmit={handleFileUpload}>
            {/* Account Selection */}
            <div className="mb-8">
              <label htmlFor="account" className="block text-base font-semibold text-gray-800 mb-3">
                1. Select Account
              </label>
              <select
                id="account"
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                className="block w-full px-4 py-3 border-2 border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-base transition-all"
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
            <div className="mb-8">
              <label htmlFor="file" className="block text-base font-semibold text-gray-800 mb-3">
                2. Upload File
              </label>
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 hover:border-indigo-400 transition-colors">
                <input
                  type="file"
                  id="file"
                  accept=".csv,.pdf"
                  multiple
                  onChange={(e) => setFiles(e.target.files ? Array.from(e.target.files) : [])}
                  className="block w-full text-base text-gray-700
                    file:mr-4 file:py-3 file:px-6
                    file:rounded-lg file:border-0
                    file:text-sm file:font-semibold
                    file:bg-gradient-to-r file:from-indigo-500 file:to-purple-600
                    file:text-white hover:file:from-indigo-600 hover:file:to-purple-700
                    file:cursor-pointer file:transition-all"
                  required
                />
                {files.length > 0 && (
                  <div className="mt-3 text-sm text-gray-700">
                    <strong>{files.length}</strong> file{files.length !== 1 ? 's' : ''} selected
                  </div>
                )}
                <p className="mt-3 text-sm text-gray-500 flex items-center">
                  <span className="mr-2">📄</span>
                  Supported formats: CSV, PDF (up to 10MB each). You can select multiple files.
                </p>
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={importing || !selectedAccount || files.length === 0}
              className="w-full flex justify-center items-center py-4 px-6 border border-transparent rounded-lg shadow-lg text-base font-semibold text-white bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:from-gray-400 disabled:to-gray-400 disabled:cursor-not-allowed transition-all transform hover:scale-105"
            >
              {importing ? (
                <>
                  <span className="animate-spin mr-2">⏳</span>
                  Importing...
                </>
              ) : (
                <>
                  <span className="mr-2">🚀</span>
                  {files.length > 0 ? `Import ${files.length} File${files.length !== 1 ? 's' : ''}` : 'Import Transactions'}
                </>
              )}
            </button>
          </form>
        </div>
      )}

      {/* Step 2: Processing */}
      {(step === 'upload' || step === 'processing') && (
        <div className="bg-white shadow-xl rounded-xl border border-gray-200 p-8">
          <div className="text-center">
            <div className="animate-spin rounded-full h-16 w-16 border-4 border-indigo-200 border-t-indigo-600 mx-auto mb-6"></div>
            <p className="text-xl text-gray-800 font-semibold mb-2">
              {step === 'upload' ? 'Uploading files...' : 'Processing transactions...'}
            </p>
            <p className="text-base text-gray-600 mb-4">
              Processing file {currentFileIndex + 1} of {files.length}
            </p>
            <div className="w-full bg-gray-200 rounded-full h-2 max-w-md mx-auto">
              <div
                className="bg-gradient-to-r from-indigo-500 to-purple-600 h-2 rounded-full transition-all duration-500"
                style={{ width: `${((currentFileIndex + 1) / files.length) * 100}%` }}
              ></div>
            </div>
            <p className="text-sm text-gray-500 mt-4">This may take a moment...</p>
          </div>
        </div>
      )}

      {/* Step 3: Complete */}
      {step === 'complete' && importRecords.length > 0 && (
        <div className="bg-white shadow-xl rounded-xl border border-gray-200 p-8">
          <div className="text-center mb-8">
            <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-green-100 mb-4">
              <svg
                className="h-8 w-8 text-green-600"
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
            <h3 className="text-2xl font-bold text-gray-900">Import Complete!</h3>
            <p className="text-gray-600 mt-2">
              Processed {importRecords.length} file{importRecords.length !== 1 ? 's' : ''}
            </p>
          </div>

          {/* Import Summary for each file */}
          <div className="space-y-4 mb-8">
            {importRecords.map((record, index) => (
              <div key={index} className={`border rounded-lg p-4 ${
                record.status === 'FAILED' ? 'border-red-200 bg-red-50' : 'border-green-200 bg-green-50'
              }`}>
                <div className="flex justify-between items-start mb-3">
                  <div className="flex-1">
                    <div className="font-semibold text-gray-900 mb-1">{record.filename}</div>
                    <div className={`text-sm font-medium ${
                      record.status === 'FAILED' ? 'text-red-600' : 'text-green-600'
                    }`}>
                      {record.status}
                    </div>
                  </div>
                  {record.status !== 'FAILED' && (
                    <div className="text-right">
                      <div className="text-lg font-bold text-green-600">
                        +{record.transactions_imported}
                      </div>
                      <div className="text-xs text-gray-500">imported</div>
                    </div>
                  )}
                </div>
                {record.status === 'FAILED' && record.error_message && (
                  <div className="text-sm text-red-700 mt-2">
                    Error: {record.error_message}
                  </div>
                )}
                {record.status !== 'FAILED' && (
                  <div className="flex justify-between text-sm text-gray-600">
                    <span>{record.transactions_duplicate} duplicates skipped</span>
                  </div>
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
              className="flex-1 py-3 px-6 border-2 border-gray-300 rounded-lg shadow-sm text-base font-semibold text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-all"
            >
              Import More Files
            </button>
            <a
              href="/transactions"
              className="flex-1 py-3 px-6 border border-transparent rounded-lg shadow-lg text-base font-semibold text-white bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 text-center transition-all"
            >
              View Transactions
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
