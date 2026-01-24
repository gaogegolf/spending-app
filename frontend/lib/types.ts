// Account types
export type AccountType = 'CREDIT_CARD' | 'CHECKING' | 'SAVINGS' | 'INVESTMENT' | 'OTHER' | 'BROKERAGE' | 'IRA_ROTH' | 'IRA_TRADITIONAL' | 'RETIREMENT_401K' | 'STOCK_PLAN';

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
  // Bank account stats
  transaction_count: number;
  import_count: number;
  // Investment account stats
  snapshot_count: number;
  position_count: number;
}

// Transaction types
export type TransactionType = 'EXPENSE' | 'INCOME' | 'TRANSFER' | 'UNCATEGORIZED';
export type ClassificationMethod = 'LLM' | 'RULE' | 'MANUAL' | 'DEFAULT' | 'LEARNED' | 'RECLASSIFIED';

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

// Brokerage/Investment types
export type PositionType = 'STOCK' | 'ETF' | 'MUTUAL_FUND' | 'BOND' | 'CASH' | 'MONEY_MARKET' | 'RSU' | 'ESPP' | 'OPTION' | 'OTHER';
export type AssetClass = 'EQUITY' | 'FIXED_INCOME' | 'CASH' | 'ALTERNATIVE' | 'UNKNOWN';

export interface Position {
  id: string;
  symbol: string | null;
  security_name: string;
  security_type: PositionType;
  quantity: number | null;
  price: number | null;
  market_value: number;
  cost_basis: number | null;
  asset_class: AssetClass;
  // Multi-currency support
  currency?: string;
  market_value_usd?: number | null;
  fx_rate_used?: number | null;
}

export interface HoldingsSnapshot {
  id: string;
  account_id: string;
  account_name: string;
  account_type: AccountType;
  statement_date: string;
  total_value: number;
  total_cash: number;
  total_securities: number;
  is_reconciled: boolean;
  position_count: number;
  positions?: Position[];
  // Multi-currency support
  base_currency?: string;
  cash_balances?: Record<string, number>;
  fx_rates?: Record<string, number>;
}

export interface NetWorthData {
  current_total: number;
  accounts: {
    account_id: string;
    account_name: string;
    account_type: string;
    latest_value: number;
    statement_date: string;
  }[];
  history: {
    date: string;
    total: number;
  }[];
}

export interface BrokerageParseResult {
  import_id: string;
  provider: string;
  account_type: string;
  account_identifier: string;
  statement_date: string | null;
  total_value: number;
  total_cash: number;
  total_securities: number;
  calculated_total: number;
  is_reconciled: boolean;
  reconciliation_diff: number;
  positions: {
    symbol: string | null;
    security_name: string;
    security_type: string;
    quantity: number | null;
    price: number | null;
    market_value: number;
    cost_basis: number | null;
    asset_class: string;
    // Multi-currency support
    currency?: string;
    market_value_usd?: number | null;
    fx_rate_used?: number | null;
  }[];
  warnings: string[];
  // Multi-currency support
  base_currency?: string;
  fx_rates?: Record<string, number>;
  cash_by_currency?: Record<string, number>;
  // Multi-account support (set when parsing multi-account statements like IBKR)
  is_multi_account?: boolean;
  account_count?: number;
  accounts?: BrokerageParseResult[];
}

// Net worth by account breakdown
export interface NetWorthByAccountData {
  accounts: {
    account_id: string;
    account_name: string;
    account_type: string;
  }[];
  history: {
    date: string;
    total: number;
    accounts: {
      account_id: string;
      account_name: string;
      account_type: string;
      value: number;
    }[];
  }[];
}

// Asset class breakdown
export interface AssetClassBreakdown {
  current: {
    equity: number;
    fixed_income: number;
    cash: number;
    alternative: number;
    unknown: number;
    total: number;
  };
  history: {
    date: string;
    equity: number;
    fixed_income: number;
    cash: number;
    alternative: number;
    unknown: number;
    total: number;
  }[];
}

// Reports types
export interface YoYComparisonMonth {
  month: number;
  month_name: string;
  year1_spend: number;
  year2_spend: number;
  change: number;
  change_pct: number;
}

export interface YoYComparisonResponse {
  year1: number;
  year2: number;
  year1_total_spend: number;
  year2_total_spend: number;
  spend_change: number;
  spend_change_pct: number;
  year1_total_income: number;
  year2_total_income: number;
  income_change: number;
  income_change_pct: number;
  monthly_comparison: YoYComparisonMonth[];
}

export interface CategoryYoYComparison {
  category: string;
  year1_amount: number;
  year2_amount: number;
  change: number;
  change_pct: number;
}

export interface YoYMonthlyComparisonResponse {
  month: number;
  month_name: string;
  year1: number;
  year2: number;
  year1_summary: MonthlySummary;
  year2_summary: MonthlySummary;
  spend_change: number;
  spend_change_pct: number;
  category_comparison: CategoryYoYComparison[];
}

export interface VelocityMonth {
  year: number;
  month: number;
  month_name: string;
  total_spend: number;
  total_income: number;
  net: number;
}

export interface SpendingVelocityResponse {
  months_analyzed: number;
  monthly_data: VelocityMonth[];
  avg_monthly_spend: number;
  avg_monthly_income: number;
  avg_monthly_net: number;
  trend_slope: number;
  trend_direction: 'increasing' | 'decreasing' | 'stable' | 'insufficient_data';
}
