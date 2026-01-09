const API_BASE_URL = '/api/v1';

// Accounts API
export async function getAccounts() {
  const response = await fetch(`${API_BASE_URL}/accounts`);
  if (!response.ok) throw new Error('Failed to fetch accounts');
  return response.json();
}

export async function createAccount(data: {
  name: string;
  institution?: string;
  account_type: string;
  account_number_last4?: string;
  currency?: string;
}) {
  const response = await fetch(`${API_BASE_URL}/accounts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to create account');
  return response.json();
}

// Imports API
export async function uploadFile(accountId: string, file: File) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('account_id', accountId);

  const response = await fetch(`${API_BASE_URL}/imports/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) throw new Error('Failed to upload file');
  return response.json();
}

export async function parseImport(importId: string) {
  const response = await fetch(`${API_BASE_URL}/imports/${importId}/parse`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to parse import');
  return response.json();
}

export async function commitImport(importId: string) {
  const response = await fetch(`${API_BASE_URL}/imports/${importId}/commit`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to commit import');
  return response.json();
}

export async function getImportStatus(importId: string) {
  const response = await fetch(`${API_BASE_URL}/imports/${importId}`);
  if (!response.ok) throw new Error('Failed to get import status');
  return response.json();
}

// Transactions API
export async function getTransactions(params?: {
  account_id?: string;
  start_date?: string;
  end_date?: string;
  transaction_type?: string;
  category?: string;
  needs_review?: boolean;
  page?: number;
  page_size?: number;
}) {
  const queryParams = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        queryParams.append(key, String(value));
      }
    });
  }

  const url = `${API_BASE_URL}/transactions${queryParams.toString() ? `?${queryParams}` : ''}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error('Failed to fetch transactions');
  return response.json();
}

export async function updateTransaction(id: string, data: {
  transaction_type?: string;
  category?: string;
  subcategory?: string;
  user_note?: string;
}) {
  const response = await fetch(`${API_BASE_URL}/transactions/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update transaction');
  return response.json();
}

// Stats API
export async function getMonthlySummary(year: number, month: number, accountId?: string) {
  const queryParams = new URLSearchParams({ year: String(year), month: String(month) });
  if (accountId) {
    queryParams.append('account_id', accountId);
  }

  const response = await fetch(`${API_BASE_URL}/stats/monthly?${queryParams}`);
  if (!response.ok) throw new Error('Failed to fetch monthly summary');
  return response.json();
}
