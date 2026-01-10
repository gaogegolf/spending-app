// Account types
export type AccountType = 'CREDIT_CARD' | 'CHECKING' | 'SAVINGS' | 'INVESTMENT' | 'OTHER';

export interface Account {
  id: string;
  user_id: string;
  name: string;
  institution: string | null;
  account_type: AccountType;
  account_number_last4: string | null;
  currency: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// Transaction types
export type TransactionType = 'EXPENSE' | 'INCOME' | 'TRANSFER' | 'PAYMENT' | 'REFUND' | 'FEE_INTEREST';
export type ClassificationMethod = 'LLM' | 'RULE' | 'MANUAL' | 'DEFAULT';

export interface Transaction {
  id: string;
  account_id: string;
  import_id: string | null;
  date: string;
  post_date: string | null;
  description_raw: string;
  merchant_normalized: string | null;
  amount: string;
  currency: string;
  transaction_type: TransactionType;
  category: string | null;
  subcategory: string | null;
  tags: string[];
  is_spend: boolean;
  is_income: boolean;
  confidence: string | null;
  needs_review: boolean;
  reviewed_at: string | null;
  matched_rule_id: string | null;
  classification_method: ClassificationMethod | null;
  user_note: string | null;
  created_at: string;
  updated_at: string;
}

// Import types
export type SourceType = 'CSV' | 'PDF';
export type ImportStatus = 'PENDING' | 'PROCESSING' | 'SUCCESS' | 'FAILED' | 'PARTIAL';

export interface ImportRecord {
  id: string;
  account_id: string;
  source_type: SourceType;
  filename: string;
  status: ImportStatus;
  error_message: string | null;
  transactions_imported: number;
  transactions_duplicate: number;
  created_at: string;
  completed_at: string | null;
}

// Stats types
export interface MonthlySummary {
  year: number;
  month: number;
  total_spend: number;
  total_income: number;
  net: number;
  category_breakdown: CategoryBreakdown[];
}

export interface CategoryBreakdown {
  category: string;
  amount: number;
  count: number;
  percentage: number;
}

// API Response types
export interface TransactionListResponse {
  transactions: Transaction[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface AccountListResponse {
  accounts: Account[];
  total: number;
}

// Merchant Category types
export type MerchantCategorySource = 'USER' | 'AUTO' | 'LLM';

export interface MerchantCategory {
  id: string;
  user_id: string;
  merchant_normalized: string;
  category: string;
  confidence: number;
  source: MerchantCategorySource;
  times_applied: number;
  created_at: string;
  updated_at: string;
}

export interface MerchantCategoryListResponse {
  merchant_categories: MerchantCategory[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

// Rule types
export type RuleType = 'MERCHANT_MATCH' | 'DESCRIPTION_REGEX' | 'AMOUNT_RANGE' | 'CATEGORY_OVERRIDE' | 'COMPOSITE';

export interface RuleAction {
  transaction_type?: string;
  category?: string;
  subcategory?: string;
  is_spend?: boolean;
  is_income?: boolean;
}

export interface Rule {
  id: string;
  user_id: string;
  name: string;
  rule_type: RuleType;
  pattern: string;
  action: RuleAction;
  priority: number;
  is_active: boolean;
  description: string | null;
  match_count: number;
  created_at: string;
  updated_at: string;
  last_matched_at: string | null;
}

export interface RuleListResponse {
  rules: Rule[];
  total: number;
}
