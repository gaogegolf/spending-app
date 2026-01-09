#!/usr/bin/env python3
"""Test the fixed PDF parser with text extraction fallback."""

import sys
import os
from pathlib import Path

# Add backend/app to Python path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from app.services.file_parser.pdf_parser import PDFParser

# Path to real Fidelity PDF
pdf_path = "/Users/I858764/Documents/Spending/Fidelity® Rewards Visa Signature® Card/2025-11-24 Statement - Card...4855.pdf"

if __name__ == "__main__":
    print("="*80)
    print("Testing Fixed PDF Parser with Text Extraction Fallback")
    print("="*80)

    if not os.path.exists(pdf_path):
        print(f"ERROR: PDF file not found at: {pdf_path}")
        sys.exit(1)

    print(f"\nParsing PDF: {pdf_path}")
    print()

    # Create parser and parse
    parser = PDFParser(pdf_path)
    result = parser.parse()

    print(f"Success: {result.success}")
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")
    print(f"Metadata: {result.metadata}")
    print(f"\nTransactions found: {len(result.transactions)}")
    print()

    if result.transactions:
        print("Parsed Transactions:")
        print("-" * 80)

        total_amount = 0

        for i, txn in enumerate(result.transactions, 1):
            date = txn.get('date')
            desc = txn.get('description_raw', '')[:50]  # Truncate long descriptions
            merchant = txn.get('merchant_normalized', '')
            amount = txn.get('amount', 0)
            is_credit = txn.get('is_credit', False)

            print(f"{i}. {date} | ${amount:,.2f} | {'CREDIT' if is_credit else 'DEBIT'}")
            print(f"   Merchant: {merchant}")
            print(f"   Raw: {desc}")
            print()

            # Calculate total spending (debits only, exclude credits)
            if not is_credit:
                total_amount += amount

        print("-" * 80)
        print(f"Total Debit Amount (Spending): ${total_amount:,.2f}")
        print()
        print("Expected for Nov 2025 Fidelity statement:")
        print("  - 2 debits (purchases) = $428.00")
        print("  - 1 credit (payment) = $373.00 (excluded from spending)")
        print("  - 1 credit (refund) = $355.00 (excluded from spending)")
        print()

        if total_amount == 428.00:
            print("✅ SUCCESS: Spending total matches expected value!")
        else:
            print(f"⚠️  WARNING: Spending total ${total_amount:,.2f} does not match expected $428.00")
    else:
        print("❌ FAILED: No transactions extracted")
        print()
        print("This means the text extraction fallback also failed.")
        print("Check the error messages above for details.")
