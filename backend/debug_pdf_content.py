#!/usr/bin/env python3
"""Debug script to inspect PDF content."""

import sys
import pdfplumber

pdf_path = "/Users/I858764/Documents/Spending/Fidelity® Rewards Visa Signature® Card/2025-11-24 Statement - Card...4855.pdf"

if __name__ == "__main__":
    print("="*80)
    print("Debugging PDF Content")
    print("="*80)

    with pdfplumber.open(pdf_path) as pdf:
        print(f"\nTotal pages: {len(pdf.pages)}\n")

        for i, page in enumerate(pdf.pages, 1):
            print(f"\n{'='*80}")
            print(f"PAGE {i}")
            print('='*80)

            # Extract tables
            tables = page.extract_tables()
            print(f"\nTables found: {len(tables)}")

            for j, table in enumerate(tables, 1):
                print(f"\nTable {j}:")
                print(f"  Rows: {len(table)}")
                if table:
                    print(f"  Headers: {table[0]}")
                    if len(table) > 1:
                        print(f"  First row: {table[1]}")
                    if len(table) > 2:
                        print(f"  Second row: {table[2]}")

            # Extract raw text (first 2000 characters)
            text = page.extract_text()
            if text:
                print(f"\n\nRaw Text (first 2000 chars):")
                print("-" * 80)
                print(text[:2000])
                print("-" * 80)

            # Show all pages
            # if i >= 1:
            #     break
