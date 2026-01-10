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

  if (!response.ok) {
    const errorText = await response.text();
    console.error('Upload failed:', response.status, errorText);
    throw new Error(`Failed to upload file: ${response.status} - ${errorText}`);
  }

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

  if (!response.ok) {
    const errorText = await response.text();
    console.error('Commit failed:', response.status, errorText);
    throw new Error(`Failed to commit import: ${response.status} - ${errorText}`);
  }

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
  description?: string;
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

export async function deleteTransaction(id: string) {
  const response = await fetch(`${API_BASE_URL}/transactions/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete transaction');
}

export async function bulkDeleteTransactions(transactionIds: string[]) {
  const response = await fetch(`${API_BASE_URL}/transactions/bulk-delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(transactionIds),
  });
  if (!response.ok) throw new Error('Failed to delete transactions');
  return response.json();
}

export async function reclassifyAllTransactions() {
  const response = await fetch(`${API_BASE_URL}/transactions/reclassify-all`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to reclassify transactions');
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

export async function getYearlySummary(year: number, accountId?: string) {
  const queryParams = new URLSearchParams({ year: String(year) });
  if (accountId) {
    queryParams.append('account_id', accountId);
  }

  const response = await fetch(`${API_BASE_URL}/stats/yearly?${queryParams}`);
  if (!response.ok) throw new Error('Failed to fetch yearly summary');
  return response.json();
}

export async function getCategoryBreakdown(startDate: string, endDate: string, accountId?: string) {
  const queryParams = new URLSearchParams({ start_date: startDate, end_date: endDate });
  if (accountId) {
    queryParams.append('account_id', accountId);
  }

  const response = await fetch(`${API_BASE_URL}/stats/category-breakdown?${queryParams}`);
  if (!response.ok) throw new Error('Failed to fetch category breakdown');
  return response.json();
}

export async function getMerchantAnalysis(startDate: string, endDate: string, limit: number = 10) {
  const queryParams = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    limit: String(limit)
  });

  const response = await fetch(`${API_BASE_URL}/stats/merchant-analysis?${queryParams}`);
  if (!response.ok) throw new Error('Failed to fetch merchant analysis');
  return response.json();
}

// Merchant Categories API
export async function getMerchantCategories(params?: {
  merchant_search?: string;
  source?: string;
  category?: string;
  page?: number;
  page_size?: number;
}) {
  const queryParams = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, String(value));
      }
    });
  }

  const url = `${API_BASE_URL}/merchant-categories${queryParams.toString() ? `?${queryParams}` : ''}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error('Failed to fetch merchant categories');
  return response.json();
}

export async function getMerchantCategoryCategories() {
  const response = await fetch(`${API_BASE_URL}/merchant-categories/categories`);
  if (!response.ok) throw new Error('Failed to fetch categories');
  return response.json();
}

export async function createMerchantCategory(data: {
  merchant_normalized: string;
  category: string;
  source?: string;
}) {
  const response = await fetch(`${API_BASE_URL}/merchant-categories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to create merchant category');
  return response.json();
}

export async function updateMerchantCategory(id: string, data: {
  category?: string;
  confidence?: number;
}) {
  const response = await fetch(`${API_BASE_URL}/merchant-categories/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update merchant category');
  return response.json();
}

export async function deleteMerchantCategory(id: string) {
  const response = await fetch(`${API_BASE_URL}/merchant-categories/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete merchant category');
}

export async function bulkDeleteMerchantCategories(ids: string[]) {
  const response = await fetch(`${API_BASE_URL}/merchant-categories/bulk-delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ids),
  });
  if (!response.ok) throw new Error('Failed to delete merchant categories');
  return response.json();
}

// Rules API
export async function getRules(params?: {
  rule_type?: string;
  is_active?: boolean;
  search?: string;
  page?: number;
  page_size?: number;
}) {
  const queryParams = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, String(value));
      }
    });
  }

  const url = `${API_BASE_URL}/rules${queryParams.toString() ? `?${queryParams}` : ''}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error('Failed to fetch rules');
  return response.json();
}

export async function getRule(id: string) {
  const response = await fetch(`${API_BASE_URL}/rules/${id}`);
  if (!response.ok) throw new Error('Failed to fetch rule');
  return response.json();
}

export async function createRule(data: {
  name: string;
  rule_type: string;
  pattern: string;
  action: {
    transaction_type?: string;
    category?: string;
    subcategory?: string;
    is_spend?: boolean;
    is_income?: boolean;
  };
  priority?: number;
  description?: string;
  is_active?: boolean;
}) {
  const response = await fetch(`${API_BASE_URL}/rules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to create rule: ${errorText}`);
  }
  return response.json();
}

export async function updateRule(id: string, data: {
  name?: string;
  pattern?: string;
  action?: {
    transaction_type?: string;
    category?: string;
    subcategory?: string;
    is_spend?: boolean;
    is_income?: boolean;
  };
  priority?: number;
  is_active?: boolean;
  description?: string;
}) {
  const response = await fetch(`${API_BASE_URL}/rules/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to update rule: ${errorText}`);
  }
  return response.json();
}

export async function deleteRule(id: string) {
  const response = await fetch(`${API_BASE_URL}/rules/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete rule');
}

export async function toggleRule(id: string) {
  const response = await fetch(`${API_BASE_URL}/rules/${id}/toggle`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to toggle rule');
  return response.json();
}

export async function bulkDeleteRules(ids: string[]) {
  const response = await fetch(`${API_BASE_URL}/rules/bulk-delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ids),
  });
  if (!response.ok) throw new Error('Failed to delete rules');
  return response.json();
}

export async function getRuleMatchCount(id: string) {
  const response = await fetch(`${API_BASE_URL}/rules/${id}/match-count`);
  if (!response.ok) throw new Error('Failed to get match count');
  return response.json();
}

export async function applyRuleToTransactions(id: string) {
  const response = await fetch(`${API_BASE_URL}/rules/${id}/apply`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to apply rule');
  return response.json();
}
