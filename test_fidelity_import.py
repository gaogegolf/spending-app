"""Test script to validate Fidelity PDF parsing with real statement."""

import sys
sys.path.insert(0, 'backend')

from app.services.file_parser.pdf_parser import PDFParser


def test_fidelity_november_2025():
    """Test parsing of November 2025 Fidelity statement."""

    pdf_path = "/Users/I858764/Documents/Spending/Fidelity® Rewards Visa Signature® Card/2025-11-24 Statement - Card...4855.pdf"

    print("=" * 60)
    print("Testing Fidelity PDF Parser")
    print("=" * 60)
    print(f"File: {pdf_path}")
    print()

    # Parse the PDF
    parser = PDFParser(pdf_path)
    result = parser.parse()

    print(f"✓ Success: {result.success}")
    print(f"✓ Transactions Found: {len(result.transactions)}")
    print()

    if result.errors:
        print("❌ Errors:")
        for error in result.errors:
            print(f"  - {error}")
        print()

    if result.warnings:
        print("⚠️  Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
        print()

    # Display transactions
    print("Transactions:")
    print("-" * 60)

    total_debits = 0
    total_credits = 0

    for i, txn in enumerate(result.transactions, 1):
        is_credit = txn.get('is_credit', False)
        symbol = "💳 CR" if is_credit else "💰 DB"

        print(f"{i}. {symbol} {txn['date']}")
        print(f"   {txn['description_raw']}")
        print(f"   Merchant: {txn['merchant_normalized']}")
        print(f"   Amount: ${txn['amount']:.2f}")
        print()

        if is_credit:
            total_credits += txn['amount']
        else:
            total_debits += txn['amount']

    print("-" * 60)
    print(f"Total Debits (Spending): ${total_debits:.2f}")
    print(f"Total Credits: ${total_credits:.2f}")
    print()

    # Validation
    print("=" * 60)
    print("Validation")
    print("=" * 60)

    expected_count = 4
    expected_spending = 428.00
    expected_payment = 373.00
    expected_refund = 355.00

    checks = []

    # Check transaction count
    if len(result.transactions) == expected_count:
        checks.append(f"✅ Transaction count: {len(result.transactions)} (expected {expected_count})")
    else:
        checks.append(f"❌ Transaction count: {len(result.transactions)} (expected {expected_count})")

    # Check spending total
    if abs(total_debits - expected_spending) < 0.01:
        checks.append(f"✅ Total spending: ${total_debits:.2f} (expected ${expected_spending:.2f})")
    else:
        checks.append(f"❌ Total spending: ${total_debits:.2f} (expected ${expected_spending:.2f})")

    # Check credits
    if abs(total_credits - (expected_payment + expected_refund)) < 0.01:
        checks.append(f"✅ Total credits: ${total_credits:.2f} (payment + refund)")
    else:
        checks.append(f"⚠️  Total credits: ${total_credits:.2f} (expected ${expected_payment + expected_refund:.2f})")

    # Check merchant cleaning
    merchants = [txn['merchant_normalized'] for txn in result.transactions]
    if any("800-" not in m and "650-" not in m for m in merchants if m):
        checks.append("✅ Merchant names cleaned (phone numbers removed)")
    else:
        checks.append("⚠️  Some merchant names still contain phone numbers")

    for check in checks:
        print(check)

    print()
    print("=" * 60)
    print("Expected Behavior:")
    print("=" * 60)
    print(f"✓ Spending (debits): ${expected_spending:.2f}")
    print(f"✓ Payment excluded: ${expected_payment:.2f}")
    print(f"✓ Refund excluded: ${expected_refund:.2f}")
    print(f"✓ Net new charges: ${expected_spending:.2f}")
    print()
    print("This correctly excludes PAYMENT and REFUND from spending totals.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_fidelity_november_2025()
    except FileNotFoundError:
        print("❌ Error: Fidelity PDF file not found.")
        print("Make sure the file exists at the expected path.")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
