// Transaction types and their associated categories

export const TRANSACTION_TYPES = ['EXPENSE', 'INCOME', 'TRANSFER', 'UNCATEGORIZED'] as const;
export type TransactionType = typeof TRANSACTION_TYPES[number];

export interface Category {
  id: number;
  name: string;
}

export const CATEGORIES_BY_TYPE: Record<TransactionType, Category[]> = {
  EXPENSE: [
    { id: 2, name: "Advertising" },
    { id: 58, name: "Advisory Fee" },
    { id: 1, name: "ATM/Cash" },
    { id: 3, name: "Automotive" },
    { id: 4, name: "Business Miscellaneous" },
    { id: 5, name: "Cable/Satellite" },
    { id: 6, name: "Charitable Giving" },
    { id: 7, name: "Checks" },
    { id: 8, name: "Child/Dependent" },
    { id: 9, name: "Clothing/Shoes" },
    { id: 10, name: "Dues & Subscriptions" },
    { id: 11, name: "Education" },
    { id: 12, name: "Electronics" },
    { id: 13, name: "Entertainment" },
    { id: 14, name: "Gasoline/Fuel" },
    { id: 15, name: "General Merchandise" },
    { id: 16, name: "Gifts" },
    { id: 17, name: "Groceries" },
    { id: 18, name: "Healthcare/Medical" },
    { id: 19, name: "Hobbies" },
    { id: 20, name: "Home Improvement" },
    { id: 21, name: "Home Maintenance" },
    { id: 22, name: "Insurance" },
    { id: 23, name: "Loans" },
    { id: 24, name: "Mortgages" },
    { id: 25, name: "Office Maintenance" },
    { id: 26, name: "Office Supplies" },
    { id: 27, name: "Online Services" },
    { id: 28, name: "Other Bills" },
    { id: 29, name: "Other Expenses" },
    { id: 30, name: "Personal Care" },
    { id: 31, name: "Pets/Pet Care" },
    { id: 32, name: "Postage & Shipping" },
    { id: 33, name: "Printing" },
    { id: 34, name: "Rent" },
    { id: 35, name: "Restaurants" },
    { id: 36, name: "Service Charges/Fees" },
    { id: 37, name: "Taxes" },
    { id: 38, name: "Telephone" },
    { id: 39, name: "Travel" },
    { id: 40, name: "Utilities" },
    { id: 41, name: "Wages Paid" },
  ],
  INCOME: [
    { id: 42, name: "Consulting" },
    { id: 43, name: "Deposits" },
    { id: 68, name: "Dividends Received" },
    { id: 69, name: "Dividends Received (tax-advantaged)" },
    { id: 44, name: "Interest" },
    { id: 45, name: "Investment Income" },
    { id: 46, name: "Other Income" },
    { id: 47, name: "Paychecks/Salary" },
    { id: 73, name: "Refunds & Reimbursements" },
    { id: 48, name: "Retirement Income" },
    { id: 72, name: "Rewards" },
    { id: 49, name: "Sales" },
    { id: 50, name: "Services" },
  ],
  TRANSFER: [
    { id: 62, name: "Allocated Excess Cash" },
    { id: 60, name: "Cash Raised" },
    { id: 65, name: "Client Request" },
    { id: 51, name: "Credit Card Payments" },
    { id: 61, name: "Diversified Transferred-in Securities" },
    { id: 57, name: "Expense Reimbursement" },
    { id: 63, name: "General Rebalance" },
    { id: 66, name: "Not Traded" },
    { id: 59, name: "Personal Strategy Implementation" },
    { id: 70, name: "Portfolio Management" },
    { id: 55, name: "Retirement Contributions" },
    { id: 52, name: "Savings" },
    { id: 53, name: "Securities Trades" },
    { id: 67, name: "Strategy Change" },
    { id: 71, name: "Tax Location" },
    { id: 64, name: "Tax Loss Harvesting" },
    { id: 54, name: "Transfers" },
  ],
  UNCATEGORIZED: [
    { id: 56, name: "Uncategorized" },
  ],
};

// Get all categories as a flat list
export const ALL_CATEGORIES: Category[] = Object.values(CATEGORIES_BY_TYPE).flat();

// Get category names for a specific type
export function getCategoriesForType(type: TransactionType | string | null): Category[] {
  if (!type || !(type in CATEGORIES_BY_TYPE)) {
    return ALL_CATEGORIES;
  }
  return CATEGORIES_BY_TYPE[type as TransactionType];
}

// Get all category names as a flat list (for backwards compatibility)
export const CATEGORY_NAMES: string[] = ALL_CATEGORIES.map(c => c.name).sort();

// Find which type a category belongs to
export function getTypeForCategory(categoryName: string): TransactionType | null {
  for (const [type, categories] of Object.entries(CATEGORIES_BY_TYPE)) {
    if (categories.some(c => c.name === categoryName)) {
      return type as TransactionType;
    }
  }
  return null;
}
