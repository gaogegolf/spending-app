#!/usr/bin/env python3
"""End-to-end API test - Create account and import Fidelity PDF."""

import requests
import json
from pathlib import Path

BASE_URL = "http://localhost:8000/api/v1"

def test_e2e_import():
    print("="*80)
    print("End-to-End API Test: Create Account & Import Fidelity PDF")
    print("="*80)

    # Step 1: Create an account
    print("\n1. Creating account...")
    account_data = {
        "name": "Fidelity Credit Card",
        "institution": "Fidelity",
        "account_type": "CREDIT_CARD",
        "account_number_last4": "4855",
        "currency": "USD"
    }

    response = requests.post(f"{BASE_URL}/accounts", json=account_data)
    print(f"   Status: {response.status_code}")

    if response.status_code != 201:
        print(f"   ERROR: {response.text}")
        return False

    account = response.json()
    account_id = account['id']
    print(f"   ✅ Account created: {account_id}")
    print(f"   Name: {account['name']}")

    # Step 2: Upload Fidelity PDF
    print("\n2. Uploading Fidelity PDF...")
    pdf_path = "/Users/I858764/Documents/Spending/Fidelity® Rewards Visa Signature® Card/2025-11-24 Statement - Card...4855.pdf"

    with open(pdf_path, 'rb') as f:
        files = {'file': f}
        data = {'account_id': account_id}
        response = requests.post(f"{BASE_URL}/imports/upload", files=files, data=data)

    print(f"   Status: {response.status_code}")

    if response.status_code != 201:
        print(f"   ERROR: {response.text}")
        return False

    import_record = response.json()
    import_id = import_record['id']
    print(f"   ✅ File uploaded: {import_id}")
    print(f"   Filename: {import_record['filename']}")
    print(f"   Status: {import_record['status']}")

    # Step 3: Parse the file
    print("\n3. Parsing file...")
    response = requests.post(f"{BASE_URL}/imports/{import_id}/parse")
    print(f"   Status: {response.status_code}")

    if response.status_code != 200:
        print(f"   ERROR: {response.text}")
        return False

    preview = response.json()
    print(f"   ✅ File parsed successfully")
    print(f"   Total transactions: {preview['total_count']}")
    print(f"   Duplicates: {preview['duplicate_count']}")
    print(f"   Warnings: {preview.get('warnings', [])}")

    print(f"\n   Preview (first 5):")
    for i, txn in enumerate(preview['transactions_preview'][:5], 1):
        print(f"      {i}. {txn['date']} | ${txn['amount']:.2f} | {txn['description_raw'][:40]}")

    # Step 4: Commit the import
    print("\n4. Committing import (classifying & inserting transactions)...")
    response = requests.post(f"{BASE_URL}/imports/{import_id}/commit")
    print(f"   Status: {response.status_code}")

    if response.status_code != 200:
        print(f"   ERROR: {response.text}")
        return False

    final_import = response.json()
    print(f"   ✅ Import completed successfully")
    print(f"   Status: {final_import['status']}")
    print(f"   Transactions imported: {final_import['transactions_imported']}")
    print(f"   Duplicates skipped: {final_import['transactions_duplicate']}")

    # Step 5: List transactions
    print("\n5. Listing imported transactions...")
    response = requests.get(f"{BASE_URL}/transactions?account_id={account_id}")
    print(f"   Status: {response.status_code}")

    if response.status_code != 200:
        print(f"   ERROR: {response.text}")
        return False

    transactions = response.json()
    print(f"   ✅ Transactions retrieved")
    print(f"   Total: {transactions['total']}")

    print(f"\n   All Transactions:")
    for i, txn in enumerate(transactions['transactions'], 1):
        txn_type = txn['transaction_type']
        is_spend = txn['is_spend']
        amount = float(txn['amount'])
        print(f"      {i}. {txn['date']} | ${amount:.2f} | {txn_type:12} | is_spend={is_spend} | {txn['merchant_normalized']}")

    # Step 6: Get monthly stats
    print("\n6. Getting monthly spending stats...")
    response = requests.get(f"{BASE_URL}/stats/monthly?year=2026&month=11")
    print(f"   Status: {response.status_code}")

    if response.status_code != 200:
        print(f"   ERROR: {response.text}")
        return False

    stats = response.json()
    print(f"   ✅ Monthly stats calculated")
    print(f"   Total Spending: ${stats['total_spend']:.2f}")
    print(f"   Total Income: ${stats['total_income']:.2f}")
    print(f"   Net: ${stats['net']:.2f}")

    print(f"\n   Category Breakdown:")
    for cat in stats.get('category_breakdown', []):
        print(f"      {cat['category']:20} ${cat['amount']:8.2f} ({cat['percentage']:.1f}%)")

    # Verify spending total
    print("\n" + "="*80)
    print("VERIFICATION")
    print("="*80)
    print(f"Expected spending: $428.00 (excludes payment $373 and refund $355)")
    print(f"Actual spending:   ${stats['total_spend']:.2f}")

    if abs(stats['total_spend'] - 428.00) < 0.01:
        print("✅ SUCCESS: Spending total matches expected value!")
        return True
    else:
        print("❌ FAILED: Spending total does not match expected value")
        return False


if __name__ == "__main__":
    success = test_e2e_import()
    exit(0 if success else 1)
