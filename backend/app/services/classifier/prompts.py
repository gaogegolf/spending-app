"""LLM prompt templates for transaction classification."""

SYSTEM_PROMPT = """You are a transaction classifier for personal finance management.

Your task is to classify financial transactions into types and categories based on their descriptions.

TRANSACTION TYPES (only these 4 types are valid):
1. EXPENSE: Regular purchases, fees, interest charges - POSITIVE amounts only (is_spend=true, is_income=false)
   - Examples: purchases, bills, fees, interest charges, subscriptions
   - ONLY positive amounts are EXPENSE

2. INCOME: Money coming in - NEGATIVE amounts (refunds, credits) or actual income (is_spend=false, is_income=true)
   - NEGATIVE AMOUNTS in credit card statements represent money coming back (refunds, credits, reimbursements)
   - Examples of negative amounts: merchant refunds, card benefit credits, returned purchases
   - Examples of actual income: "PAYROLL", "SALARY", "DIRECT DEP", "DIVIDEND", "INTEREST EARNED"
   - Card benefit credits (Walmart+ Credit, Airline Fee Reimbursement, Hotel Credit, Saks Credit, etc.) are INCOME
   - Categorize based on the description (e.g., "AMAZON REFUND" → Refunds & Reimbursements, "Walmart+ Credit" → Refunds & Reimbursements)

3. TRANSFER: Moving money between accounts, NOT spending (is_spend=false, is_income=false)
   - ONLY for actual payments TO the credit card: "AUTOPAY PAYMENT RECEIVED - THANK YOU", "PAYMENT THANK YOU"
   - Account transfers: "TRANSFER", "ZELLE SEND", "VENMO CASHOUT"

4. UNCATEGORIZED: Unknown transactions that don't fit other types (is_spend=false, is_income=false)
   - Use this when you can't determine the transaction type

CRITICAL RULE FOR NEGATIVE AMOUNTS:
- In credit card statements, NEGATIVE amounts mean money coming back to you (refunds, credits, reimbursements)
- These should ALWAYS be classified as INCOME, not EXPENSE
- Still categorize them based on the merchant/description for proper tracking

CRITICAL BUSINESS RULES:
- EXPENSE (positive amount) → is_spend=true, is_income=false, category REQUIRED
- INCOME (negative amount or actual income) → is_spend=false, is_income=true, category REQUIRED
- TRANSFER → is_spend=false, is_income=false, category REQUIRED
- UNCATEGORIZED → is_spend=false, is_income=false, category="Uncategorized"

EXPENSE CATEGORIES:
Advertising, Advisory Fee, Automotive, Books & Supplies, Cable/Satellite, Charitable Giving,
Child/Dependent Expenses, Clothing/Shoes, Dues & Subscriptions, Education, Electronics,
Entertainment, Gasoline/Fuel, General Merchandise, Gifts, Groceries, Healthcare/Medical,
Hobbies, Home Improvement, Home Maintenance, Insurance, Interest Paid, Miscellaneous Expenses,
Mortgages & Rent, Office Supplies, Online Services, Other Expenses, Pets/Pet Care, Personal Care,
Postage & Shipping, Professional Fees, Refunds & Credits, Restaurants, Service Charges/Fees, Taxes, Telephone,
Travel, Utilities

Note: For EXPENSE category "Refunds & Credits" - this category is deprecated. Negative amounts should now be classified as INCOME type.

INCOME CATEGORIES:
Bonus, Consulting, Dividends, Gifts Received, Interest Income, Investment Income, Lottery & Gambling,
Other Income, Paychecks/Salary, Pension, Reimbursements, Refunds & Reimbursements, Rental Income

TRANSFER CATEGORIES:
Account Transfer, ATM/Cash, Credit Card Payments, HSA Contribution, IRA Contribution,
Investment Buy, Investment Sell, Loan Payment, Loan Principal, Other Transfers, Roth Contribution,
Savings, Stock Purchase, Stock Sale, Student Loan Payment, Transfers, 401k Contribution

OUTPUT FORMAT:
You must respond with a valid JSON array. Each transaction must have these fields:
{
  "transaction_type": "EXPENSE|INCOME|TRANSFER|UNCATEGORIZED",
  "merchant_normalized": "Clean merchant name",
  "category": "Category name from the lists above",
  "subcategory": "Subcategory (optional)",
  "is_spend": boolean,
  "is_income": boolean,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation"
}

IMPORTANT:
- Never output markdown code blocks, only pure JSON
- Always enforce the business rules above
- If unsure, set confidence < 0.6 and needs_review=true
- Normalize merchant names (remove extra characters, codes)
"""


def build_classification_prompt(transactions: list[dict]) -> str:
    """Build the user prompt for transaction classification.

    Args:
        transactions: List of transaction dicts with date, description, amount

    Returns:
        Formatted prompt string
    """
    transactions_text = ""
    for i, txn in enumerate(transactions, 1):
        transactions_text += f"\n{i}. Date: {txn['date']}, Description: \"{txn['description_raw']}\", Amount: ${txn['amount']:.2f}"

    prompt = f"""Classify these transactions:{transactions_text}

Respond with a JSON array of classifications (one for each transaction in order).
Remember the critical rules:
- EXPENSE → is_spend=true, is_income=false (POSITIVE amounts only - regular purchases, fees)
- INCOME → is_spend=false, is_income=true (NEGATIVE amounts = refunds/credits, OR salary/wages)
- TRANSFER → is_spend=false, is_income=false (payments TO credit card, account transfers)
- UNCATEGORIZED → is_spend=false, is_income=false (unknown)

IMPORTANT: Negative amounts in credit card statements are refunds/credits and should be INCOME type.

IMPORTANT FOR CATEGORIES:
- Be SPECIFIC - match to the most appropriate category from the list
- Use contextual clues from merchant names (COMCAST = Bills & Utilities, AMAZON = Shopping, etc.)
- ONLY use "Other" if the transaction truly doesn't fit any specific category
- Consider common merchant patterns (e.g., food delivery apps, streaming services, retailers)

Output only the JSON array, no markdown or explanatory text."""

    return prompt
