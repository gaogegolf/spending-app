#!/usr/bin/env python3
"""Extract full text from page 3 where transactions are."""

import pdfplumber

pdf_path = "/Users/I858764/Documents/Spending/Fidelity® Rewards Visa Signature® Card/2025-11-24 Statement - Card...4855.pdf"

with pdfplumber.open(pdf_path) as pdf:
    # Page 3 (index 2)
    page = pdf.pages[2]

    text = page.extract_text()

    print("="*80)
    print("PAGE 3 - FULL TEXT")
    print("="*80)
    print(text)
