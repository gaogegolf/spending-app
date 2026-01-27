"""LLM-based PDF transaction extractor using Claude Vision."""

import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from anthropic import Anthropic

from app.config import settings
from app.services.file_parser.base import ParseResult

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT = """Analyze this bank or brokerage statement and extract all transactions.

Return a JSON object with this exact structure:
{
    "institution": "Bank Name (e.g., Chase, Bank of America, Wells Fargo)",
    "account_type": "CREDIT_CARD" or "CHECKING" or "SAVINGS" or "BROKERAGE",
    "account_last4": "1234" (last 4 digits of account number if visible, null otherwise),
    "statement_date": "YYYY-MM-DD" (closing date of the statement),
    "transactions": [
        {
            "date": "YYYY-MM-DD",
            "description": "Original merchant/transaction description as shown",
            "amount": 123.45,
            "is_credit": false
        }
    ]
}

Important rules:
1. For amount values:
   - Use positive numbers for purchases, charges, debits, withdrawals
   - is_credit=true for payments to the account, refunds, deposits, credits
   - is_credit=false for purchases, charges, debits, withdrawals

2. Date formatting:
   - Always use ISO format YYYY-MM-DD
   - If only MM/DD is shown, infer the year from the statement date

3. Include ALL transactions from ALL pages
   - Don't skip any transactions
   - Include pending transactions if shown

4. Do NOT include:
   - Summary totals (e.g., "Total Purchases", "Previous Balance")
   - Account opening/closing balances
   - Interest rate information
   - Fee descriptions without actual charges

5. Return ONLY valid JSON, no additional text or explanation.
"""


class LLMPDFExtractor:
    """Extract transactions from PDFs using Claude Vision."""

    def __init__(self):
        """Initialize the LLM PDF extractor."""
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set for LLM PDF extraction")

        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-sonnet-4-20250514"

    def extract(self, pdf_path: str) -> ParseResult:
        """Extract transactions from a PDF using Claude Vision.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            ParseResult with extracted transactions
        """
        errors = []
        warnings = []

        try:
            # Read PDF as base64
            pdf_data = self._read_pdf_as_base64(pdf_path)

            if not pdf_data:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["Failed to read PDF file"],
                    warnings=[],
                    metadata={"extraction_method": "llm_vision"}
                )

            # Call Claude API with PDF
            response = self._call_claude_vision(pdf_data)

            # Parse the JSON response
            extracted_data = self._parse_response(response)

            if not extracted_data:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["Failed to parse LLM response"],
                    warnings=["LLM extraction was attempted but response parsing failed"],
                    metadata={"extraction_method": "llm_vision"}
                )

            # Convert to transaction format
            transactions = self._convert_to_transactions(extracted_data)

            if not transactions:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["No transactions found by LLM extraction"],
                    warnings=[],
                    metadata={
                        "extraction_method": "llm_vision",
                        "institution": extracted_data.get("institution"),
                        "account_type": extracted_data.get("account_type"),
                    }
                )

            return ParseResult(
                success=True,
                transactions=transactions,
                errors=errors,
                warnings=warnings,
                metadata={
                    "total_transactions": len(transactions),
                    "source": "pdf",
                    "format": "llm_vision",
                    "extraction_method": "llm_vision",
                },
                detected_institution=extracted_data.get("institution"),
                detected_account_type=extracted_data.get("account_type")
            )

        except Exception as e:
            logger.error(f"LLM PDF extraction failed: {e}")
            return ParseResult(
                success=False,
                transactions=[],
                errors=[f"LLM extraction error: {str(e)}"],
                warnings=["Consider using CSV format for more reliable parsing."],
                metadata={"extraction_method": "llm_vision"}
            )

    def _read_pdf_as_base64(self, pdf_path: str) -> Optional[str]:
        """Read PDF file and encode as base64.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Base64 encoded PDF data
        """
        try:
            pdf_file = Path(pdf_path)
            if not pdf_file.exists():
                logger.error(f"PDF file not found: {pdf_path}")
                return None

            with open(pdf_file, "rb") as f:
                pdf_bytes = f.read()

            return base64.standard_b64encode(pdf_bytes).decode("utf-8")

        except Exception as e:
            logger.error(f"Failed to read PDF as base64: {e}")
            return None

    def _call_claude_vision(self, pdf_base64: str) -> str:
        """Call Claude API with PDF document.

        Args:
            pdf_base64: Base64 encoded PDF data

        Returns:
            Response text from Claude
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
        )

        return response.content[0].text

    def _parse_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON response from Claude.

        Args:
            response_text: Raw text from Claude

        Returns:
            Parsed JSON dict or None if parsing fails
        """
        try:
            # Remove markdown code blocks if present
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                # Remove first and last lines (code block markers)
                cleaned = "\n".join(lines[1:-1] if len(lines) > 2 else lines)
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].strip()

            return json.loads(cleaned)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response text: {response_text[:500]}...")
            return None

    def _convert_to_transactions(
        self, extracted_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Convert LLM extracted data to transaction format.

        Args:
            extracted_data: Parsed JSON from LLM

        Returns:
            List of transaction dicts
        """
        transactions = []
        statement_date = extracted_data.get("statement_date")
        statement_year = None

        if statement_date:
            try:
                statement_year = datetime.fromisoformat(statement_date).year
            except ValueError:
                statement_year = datetime.now().year

        raw_transactions = extracted_data.get("transactions", [])

        for i, txn in enumerate(raw_transactions):
            try:
                # Parse date
                date_str = txn.get("date", "")
                try:
                    parsed_date = datetime.fromisoformat(date_str).date()
                except ValueError:
                    # Try common formats
                    for fmt in ["%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%Y-%m-%d"]:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    else:
                        logger.warning(f"Could not parse date: {date_str}")
                        continue

                # Parse amount
                amount = float(txn.get("amount", 0))
                is_credit = txn.get("is_credit", False)

                # Credits (payments, refunds) are stored as negative amounts
                if is_credit:
                    amount = -abs(amount)
                else:
                    amount = abs(amount)

                description = txn.get("description", "Unknown")

                # Detect if this is a payment to the card
                is_payment = any(
                    kw in description.upper()
                    for kw in ["PAYMENT", "AUTOPAY", "THANK YOU", "ACH PAYMENT"]
                )

                transactions.append(
                    {
                        "date": parsed_date.isoformat(),
                        "description_raw": description,
                        "merchant_normalized": self._clean_merchant(description),
                        "amount": amount,
                        "is_payment": is_payment,
                        "currency": "USD",
                        "row_index": i,
                    }
                )

            except Exception as e:
                logger.warning(f"Failed to convert transaction: {txn}, error: {e}")
                continue

        return transactions

    def _clean_merchant(self, description: str) -> str:
        """Clean merchant description.

        Args:
            description: Raw merchant description

        Returns:
            Cleaned merchant name
        """
        import re

        # Remove common suffixes/prefixes
        cleaned = description

        # Remove card number patterns (e.g., "XXXX1234")
        cleaned = re.sub(r"X{2,}\d{4}", "", cleaned)

        # Remove reference numbers
        cleaned = re.sub(r"#\d+", "", cleaned)
        cleaned = re.sub(r"REF\s*#?\s*\d+", "", cleaned, flags=re.IGNORECASE)

        # Remove trailing state/country codes
        cleaned = re.sub(r"\s+[A-Z]{2}\s*$", "", cleaned)

        # Remove trailing phone numbers
        cleaned = re.sub(r"\s+\d{3}[-.]?\d{3}[-.]?\d{4}\s*$", "", cleaned)

        # Remove excessive whitespace
        cleaned = " ".join(cleaned.split())

        return cleaned.strip() or description
