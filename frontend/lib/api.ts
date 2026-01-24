const API_BASE_URL = '/api/v1';

// Helper to get auth headers
function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('accessToken') : null;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

// Helper for authenticated fetch
async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = {
    ...getAuthHeaders(),
    ...(options.headers || {}),
  };

  // Don't set Content-Type for FormData (let browser set it with boundary)
  if (options.body instanceof FormData) {
    delete (headers as Record<string, string>)['Content-Type'];
  }

  const response = await fetch(url, { ...options, headers });

  // Handle 401 - redirect to login
  if (response.status === 401 && typeof window !== 'undefined') {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
    window.location.href = '/login';
  }

  return response;
}

// Accounts API
export async function getAccounts() {
  const response = await authFetch(`${API_BASE_URL}/accounts`);
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
  const response = await authFetch(`${API_BASE_URL}/accounts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to create account');
  return response.json();
}

export async function updateAccount(id: string, data: {
  name?: string;
  institution?: string;
  account_type?: string;
  account_number_last4?: string;
  is_active?: boolean;
}) {
  const response = await authFetch(`${API_BASE_URL}/accounts/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update account');
  return response.json();
}

export async function deleteAccount(id: string, permanent: boolean = false) {
  const queryParams = permanent ? '?permanent=true' : '';
  const response = await authFetch(`${API_BASE_URL}/accounts/${id}${queryParams}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete account');
}

// Imports API
export async function uploadFile(accountId: string, file: File) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('account_id', accountId);

  const response = await authFetch(`${API_BASE_URL}/imports/upload`, {
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
  const response = await authFetch(`${API_BASE_URL}/imports/${importId}/parse`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to parse import');
  return response.json();
}

export async function commitImport(importId: string) {
  const response = await authFetch(`${API_BASE_URL}/imports/${importId}/commit`, {
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
  const response = await authFetch(`${API_BASE_URL}/imports/${importId}`);
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
  matched_rule_id?: string;
  match_rule_pattern?: string;
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
  const response = await authFetch(url);
  if (!response.ok) throw new Error('Failed to fetch transactions');
  return response.json();
}

export async function updateTransaction(id: string, data: {
  transaction_type?: string;
  category?: string;
  subcategory?: string;
  user_note?: string;
}) {
  const response = await authFetch(`${API_BASE_URL}/transactions/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update transaction');
  return response.json();
}

export async function deleteTransaction(id: string) {
  const response = await authFetch(`${API_BASE_URL}/transactions/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete transaction');
}

export async function bulkDeleteTransactions(transactionIds: string[]) {
  const response = await authFetch(`${API_BASE_URL}/transactions/bulk-delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(transactionIds),
  });
  if (!response.ok) throw new Error('Failed to delete transactions');
  return response.json();
}

export async function reclassifyAllTransactions() {
  const response = await authFetch(`${API_BASE_URL}/transactions/reclassify-all`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to reclassify transactions');
  return response.json();
}

export async function getMerchantTransactionCount(merchantNormalized: string, excludeTransactionId?: string) {
  const queryParams = new URLSearchParams();
  if (excludeTransactionId) {
    queryParams.append('exclude_transaction_id', excludeTransactionId);
  }
  const url = `${API_BASE_URL}/transactions/merchant-count/${encodeURIComponent(merchantNormalized)}${queryParams.toString() ? `?${queryParams}` : ''}`;
  const response = await authFetch(url);
  if (!response.ok) throw new Error('Failed to get merchant transaction count');
  return response.json();
}

export async function applyMerchantCategory(merchantNormalized: string, category: string, excludeTransactionId?: string) {
  const queryParams = new URLSearchParams({
    merchant_normalized: merchantNormalized,
    category: category,
  });
  if (excludeTransactionId) {
    queryParams.append('exclude_transaction_id', excludeTransactionId);
  }
  const response = await authFetch(`${API_BASE_URL}/transactions/apply-merchant-category?${queryParams}`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to apply merchant category');
  return response.json();
}

// Stats API
export async function getMonthlySummary(year: number, month: number, accountId?: string) {
  const queryParams = new URLSearchParams({ year: String(year), month: String(month) });
  if (accountId) {
    queryParams.append('account_id', accountId);
  }

  const response = await authFetch(`${API_BASE_URL}/stats/monthly?${queryParams}`);
  if (!response.ok) throw new Error('Failed to fetch monthly summary');
  return response.json();
}

export async function getYearlySummary(year: number, accountId?: string) {
  const queryParams = new URLSearchParams({ year: String(year) });
  if (accountId) {
    queryParams.append('account_id', accountId);
  }

  const response = await authFetch(`${API_BASE_URL}/stats/yearly?${queryParams}`);
  if (!response.ok) throw new Error('Failed to fetch yearly summary');
  return response.json();
}

export async function getDateRangeSummary(startDate: string, endDate: string, accountId?: string) {
  const queryParams = new URLSearchParams({ start_date: startDate, end_date: endDate });
  if (accountId) {
    queryParams.append('account_id', accountId);
  }

  const response = await authFetch(`${API_BASE_URL}/stats/date-range?${queryParams}`);
  if (!response.ok) throw new Error('Failed to fetch date range summary');
  return response.json();
}

export async function getCategoryBreakdown(startDate: string, endDate: string, accountId?: string) {
  const queryParams = new URLSearchParams({ start_date: startDate, end_date: endDate });
  if (accountId) {
    queryParams.append('account_id', accountId);
  }

  const response = await authFetch(`${API_BASE_URL}/stats/category-breakdown?${queryParams}`);
  if (!response.ok) throw new Error('Failed to fetch category breakdown');
  return response.json();
}

export async function getMerchantAnalysis(startDate: string, endDate: string, limit: number = 10) {
  const queryParams = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    limit: String(limit)
  });

  const response = await authFetch(`${API_BASE_URL}/stats/merchant-analysis?${queryParams}`);
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
  const response = await authFetch(url);
  if (!response.ok) throw new Error('Failed to fetch merchant categories');
  return response.json();
}

export async function getMerchantCategoryCategories() {
  const response = await authFetch(`${API_BASE_URL}/merchant-categories/categories`);
  if (!response.ok) throw new Error('Failed to fetch categories');
  return response.json();
}

export async function createMerchantCategory(data: {
  merchant_normalized: string;
  category: string;
  source?: string;
}) {
  const response = await authFetch(`${API_BASE_URL}/merchant-categories`, {
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
  const response = await authFetch(`${API_BASE_URL}/merchant-categories/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update merchant category');
  return response.json();
}

export async function deleteMerchantCategory(id: string) {
  const response = await authFetch(`${API_BASE_URL}/merchant-categories/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete merchant category');
}

export async function bulkDeleteMerchantCategories(ids: string[]) {
  const response = await authFetch(`${API_BASE_URL}/merchant-categories/bulk-delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ids),
  });
  if (!response.ok) throw new Error('Failed to delete merchant categories');
  return response.json();
}

export async function refreshMerchantCounts() {
  const response = await authFetch(`${API_BASE_URL}/merchant-categories/refresh-counts`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to refresh merchant counts');
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
  const response = await authFetch(url);
  if (!response.ok) throw new Error('Failed to fetch rules');
  return response.json();
}

export async function getRule(id: string) {
  const response = await authFetch(`${API_BASE_URL}/rules/${id}`);
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
  const response = await authFetch(`${API_BASE_URL}/rules`, {
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
  const response = await authFetch(`${API_BASE_URL}/rules/${id}`, {
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
  const response = await authFetch(`${API_BASE_URL}/rules/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete rule');
}

export async function toggleRule(id: string) {
  const response = await authFetch(`${API_BASE_URL}/rules/${id}/toggle`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to toggle rule');
  return response.json();
}

export async function bulkDeleteRules(ids: string[]) {
  const response = await authFetch(`${API_BASE_URL}/rules/bulk-delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ids),
  });
  if (!response.ok) throw new Error('Failed to delete rules');
  return response.json();
}

export async function getRuleMatchCount(id: string) {
  const response = await authFetch(`${API_BASE_URL}/rules/${id}/match-count`);
  if (!response.ok) throw new Error('Failed to get match count');
  return response.json();
}

export async function applyRuleToTransactions(id: string) {
  const response = await authFetch(`${API_BASE_URL}/rules/${id}/apply`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to apply rule');
  return response.json();
}

export async function refreshRuleMatchCounts() {
  const response = await authFetch(`${API_BASE_URL}/rules/refresh-counts`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to refresh match counts');
  return response.json();
}

// Export API
export async function exportTransactions(params?: {
  account_id?: string;
  start_date?: string;
  end_date?: string;
  transaction_type?: string;
  category?: string;
  description?: string;
  match_rule_pattern?: string;
}) {
  const queryParams = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, String(value));
      }
    });
  }

  const url = `${API_BASE_URL}/transactions/export${queryParams.toString() ? `?${queryParams}` : ''}`;
  const response = await authFetch(url);

  if (!response.ok) throw new Error('Failed to export transactions');

  // Get the filename from Content-Disposition header or use default
  const contentDisposition = response.headers.get('Content-Disposition');
  let filename = 'transactions.csv';
  if (contentDisposition) {
    const filenameMatch = contentDisposition.match(/filename=(.+)/);
    if (filenameMatch) {
      filename = filenameMatch[1];
    }
  }

  // Get blob and trigger download
  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(downloadUrl);
}

// Brokerage API
export async function uploadBrokerageStatement(file: File, accountId?: string) {
  const formData = new FormData();
  formData.append('file', file);
  if (accountId) {
    formData.append('account_id', accountId);
  }

  const response = await authFetch(`${API_BASE_URL}/brokerage/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to upload brokerage statement: ${errorText}`);
  }

  return response.json();
}

export async function parseBrokerageStatement(importId: string) {
  const response = await authFetch(`${API_BASE_URL}/brokerage/${importId}/parse`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to parse brokerage statement');
  return response.json();
}

export async function commitBrokerageImport(
  importId: string,
  options?: {
    accountId?: string;
    createAccount?: boolean;
    accountName?: string;
  }
) {
  const formData = new FormData();
  if (options?.accountId) formData.append('account_id', options.accountId);
  if (options?.createAccount !== undefined) formData.append('create_account', String(options.createAccount));
  if (options?.accountName) formData.append('account_name', options.accountName);

  const response = await authFetch(`${API_BASE_URL}/brokerage/${importId}/commit`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to commit brokerage import: ${errorText}`);
  }

  return response.json();
}

export async function getHoldingsSnapshots(params?: {
  accountId?: string;
  startDate?: string;
  endDate?: string;
}) {
  const queryParams = new URLSearchParams();
  if (params?.accountId) queryParams.append('account_id', params.accountId);
  if (params?.startDate) queryParams.append('start_date', params.startDate);
  if (params?.endDate) queryParams.append('end_date', params.endDate);

  const url = `${API_BASE_URL}/brokerage/snapshots${queryParams.toString() ? `?${queryParams}` : ''}`;
  const response = await authFetch(url);
  if (!response.ok) throw new Error('Failed to fetch holdings snapshots');
  return response.json();
}

export async function getSnapshotDetail(snapshotId: string) {
  const response = await authFetch(`${API_BASE_URL}/brokerage/snapshots/${snapshotId}`);
  if (!response.ok) throw new Error('Failed to fetch snapshot detail');
  return response.json();
}

export async function getNetWorth(accountIds?: string[]) {
  const queryParams = new URLSearchParams();
  if (accountIds && accountIds.length > 0) {
    queryParams.append('account_ids', accountIds.join(','));
  }

  const url = `${API_BASE_URL}/brokerage/net-worth${queryParams.toString() ? `?${queryParams}` : ''}`;
  const response = await authFetch(url);
  if (!response.ok) throw new Error('Failed to fetch net worth');
  return response.json();
}

export async function getNetWorthByAccount(accountIds?: string[]) {
  const queryParams = new URLSearchParams();
  if (accountIds && accountIds.length > 0) {
    queryParams.append('account_ids', accountIds.join(','));
  }

  const url = `${API_BASE_URL}/brokerage/net-worth/by-account${queryParams.toString() ? `?${queryParams}` : ''}`;
  const response = await authFetch(url);
  if (!response.ok) throw new Error('Failed to fetch net worth by account');
  return response.json();
}

export async function getAssetClassBreakdown(accountIds?: string[]) {
  const queryParams = new URLSearchParams();
  if (accountIds && accountIds.length > 0) {
    queryParams.append('account_ids', accountIds.join(','));
  }

  const url = `${API_BASE_URL}/brokerage/net-worth/by-asset-class${queryParams.toString() ? `?${queryParams}` : ''}`;
  const response = await authFetch(url);
  if (!response.ok) throw new Error('Failed to fetch asset class breakdown');
  return response.json();
}

export async function deleteBrokerageAccount(accountId: string) {
  const response = await authFetch(`${API_BASE_URL}/brokerage/accounts/${accountId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete brokerage account');
}

export async function deleteBrokerageSnapshot(snapshotId: string) {
  const response = await authFetch(`${API_BASE_URL}/brokerage/snapshots/${snapshotId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete snapshot');
}

// Reports API
export async function getYoYComparison(year1: number, year2: number, accountId?: string) {
  const queryParams = new URLSearchParams({
    year1: String(year1),
    year2: String(year2),
  });
  if (accountId) {
    queryParams.append('account_id', accountId);
  }

  const response = await authFetch(`${API_BASE_URL}/stats/yoy?${queryParams}`);
  if (!response.ok) throw new Error('Failed to fetch YoY comparison');
  return response.json();
}

export async function getYoYMonthlyComparison(month: number, year1: number, year2: number, accountId?: string) {
  const queryParams = new URLSearchParams({
    month: String(month),
    year1: String(year1),
    year2: String(year2),
  });
  if (accountId) {
    queryParams.append('account_id', accountId);
  }

  const response = await authFetch(`${API_BASE_URL}/stats/yoy/monthly?${queryParams}`);
  if (!response.ok) throw new Error('Failed to fetch YoY monthly comparison');
  return response.json();
}

export async function getSpendingVelocity(months: number = 12, accountId?: string) {
  const queryParams = new URLSearchParams({ months: String(months) });
  if (accountId) {
    queryParams.append('account_id', accountId);
  }

  const response = await authFetch(`${API_BASE_URL}/stats/velocity?${queryParams}`);
  if (!response.ok) throw new Error('Failed to fetch spending velocity');
  return response.json();
}

export async function exportReport(params: {
  format: 'csv' | 'excel' | 'pdf';
  start_date?: string;
  end_date?: string;
  account_id?: string;
}) {
  const queryParams = new URLSearchParams({ format: params.format });
  if (params.start_date) queryParams.append('start_date', params.start_date);
  if (params.end_date) queryParams.append('end_date', params.end_date);
  if (params.account_id) queryParams.append('account_id', params.account_id);

  const response = await authFetch(`${API_BASE_URL}/reports/export?${queryParams}`);
  if (!response.ok) throw new Error('Failed to export report');

  // Get filename from Content-Disposition header
  const contentDisposition = response.headers.get('Content-Disposition');
  let filename = `report.${params.format === 'excel' ? 'xlsx' : params.format}`;
  if (contentDisposition) {
    const filenameMatch = contentDisposition.match(/filename=(.+)/);
    if (filenameMatch) {
      filename = filenameMatch[1];
    }
  }

  // Download file
  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(downloadUrl);
}
