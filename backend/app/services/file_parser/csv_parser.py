"""CSV file parser with automatic column detection and amount normalization."""

import pandas as pd
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from app.services.file_parser.base import BaseParser, ParseResult


class CSVParser(BaseParser):
    """Parser for CSV statement files."""

    def __init__(self, file_path: str, column_mapping: Optional[Dict[str, str]] = None,
                 amount_convention: str = "auto"):
        """Initialize CSV parser.

        Args:
            file_path: Path to CSV file
            column_mapping: Optional manual column mapping
            amount_convention: How to interpret amounts:
                - "auto": Auto-detect
                - "negative_is_expense": Negative amounts are expenses
                - "positive_is_expense": Positive amounts are expenses
                - "debit_credit": Separate debit/credit columns
        """
        self.file_path = file_path
        self.column_mapping = column_mapping
        self.amount_convention = amount_convention
        self.df: Optional[pd.DataFrame] = None

    def parse(self) -> ParseResult:
        """Parse CSV file and return transactions."""
        errors = []
        warnings = []
        transactions = []

        try:
            # Read CSV file
            self.df = pd.read_csv(self.file_path, encoding='utf-8-sig')

            # Detect or apply column mapping
            if not self.column_mapping:
                detected = self.detect_format()
                self.column_mapping = detected.get('suggested_mapping', {})
                if not detected.get('confidence', 0) > 0.7:
                    warnings.append("Low confidence in column detection. Please verify mapping.")

            # Validate column mapping
            validation_errors = self.validate()
            if validation_errors:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=validation_errors,
                    warnings=warnings,
                    metadata={}
                )

            # Normalize amounts
            self._normalize_amounts()

            # Convert to transactions
            transactions = self._to_transactions()

            return ParseResult(
                success=True,
                transactions=transactions,
                errors=errors,
                warnings=warnings,
                metadata={
                    'total_rows': len(self.df),
                    'column_mapping': self.column_mapping,
                    'amount_convention': self.amount_convention,
                }
            )

        except Exception as e:
            errors.append(f"Failed to parse CSV: {str(e)}")
            return ParseResult(
                success=False,
                transactions=[],
                errors=errors,
                warnings=warnings,
                metadata={}
            )

    def detect_format(self) -> Dict[str, Any]:
        """Detect CSV format and suggest column mappings."""
        if self.df is None:
            self.df = pd.read_csv(self.file_path, encoding='utf-8-sig')

        columns = self.df.columns.tolist()
        suggested_mapping = {}
        confidence_scores = {}

        # Detect date column
        date_candidates = self._find_date_columns(columns)
        if date_candidates:
            suggested_mapping['date'] = date_candidates[0]
            confidence_scores['date'] = 0.9

        # Detect description column
        desc_candidates = self._find_description_columns(columns)
        if desc_candidates:
            suggested_mapping['description'] = desc_candidates[0]
            confidence_scores['description'] = 0.8

        # Detect amount columns
        amount_info = self._find_amount_columns(columns)
        if amount_info['type'] == 'single':
            suggested_mapping['amount'] = amount_info['columns'][0]
            confidence_scores['amount'] = 0.9
        elif amount_info['type'] == 'debit_credit':
            suggested_mapping['debit'] = amount_info['columns'][0]
            suggested_mapping['credit'] = amount_info['columns'][1]
            confidence_scores['amount'] = 0.9
            self.amount_convention = "debit_credit"

        # Overall confidence
        avg_confidence = sum(confidence_scores.values()) / len(confidence_scores) if confidence_scores else 0

        return {
            'suggested_mapping': suggested_mapping,
            'confidence': avg_confidence,
            'amount_convention': amount_info.get('convention', 'auto'),
            'all_columns': columns,
        }

    def _find_date_columns(self, columns: List[str]) -> List[str]:
        """Find columns that likely contain dates."""
        date_keywords = ['date', 'trans', 'transaction', 'post', 'posting']
        candidates = []

        for col in columns:
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in date_keywords):
                # Verify it contains date-like data
                sample = self.df[col].dropna().head(5)
                if self._looks_like_dates(sample):
                    candidates.append(col)

        return candidates

    def _find_description_columns(self, columns: List[str]) -> List[str]:
        """Find columns that likely contain transaction descriptions."""
        desc_keywords = ['description', 'merchant', 'name', 'details', 'memo']
        candidates = []

        for col in columns:
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in desc_keywords):
                candidates.append(col)

        # If no keyword match, find longest text column
        if not candidates:
            text_lengths = {}
            for col in columns:
                if self.df[col].dtype == 'object':
                    avg_len = self.df[col].str.len().mean()
                    text_lengths[col] = avg_len
            if text_lengths:
                longest = max(text_lengths, key=text_lengths.get)
                candidates.append(longest)

        return candidates

    def _find_amount_columns(self, columns: List[str]) -> Dict[str, Any]:
        """Find columns that contain monetary amounts."""
        amount_keywords = ['amount', 'total', 'sum']
        debit_keywords = ['debit', 'withdrawal', 'payment', 'charge']
        credit_keywords = ['credit', 'deposit', 'income']

        amount_cols = []
        debit_cols = []
        credit_cols = []

        for col in columns:
            col_lower = col.lower()

            # Check if column contains numeric data
            if not pd.api.types.is_numeric_dtype(self.df[col]):
                try:
                    pd.to_numeric(self.df[col], errors='coerce')
                except:
                    continue

            if any(keyword in col_lower for keyword in debit_keywords):
                debit_cols.append(col)
            elif any(keyword in col_lower for keyword in credit_keywords):
                credit_cols.append(col)
            elif any(keyword in col_lower for keyword in amount_keywords):
                amount_cols.append(col)

        # Determine format
        if len(debit_cols) == 1 and len(credit_cols) == 1:
            return {
                'type': 'debit_credit',
                'columns': [debit_cols[0], credit_cols[0]],
                'convention': 'debit_credit'
            }
        elif amount_cols:
            # Check if amounts have +/- signs
            sample = self.df[amount_cols[0]].dropna()
            has_negative = (sample < 0).any()
            return {
                'type': 'single',
                'columns': [amount_cols[0]],
                'convention': 'negative_is_expense' if has_negative else 'positive_is_expense'
            }
        else:
            return {'type': 'unknown', 'columns': [], 'convention': 'auto'}

    def _looks_like_dates(self, series: pd.Series) -> bool:
        """Check if a series looks like it contains dates."""
        try:
            pd.to_datetime(series, errors='raise')
            return True
        except:
            return False

    def _normalize_amounts(self):
        """Normalize amounts based on convention."""
        if self.amount_convention == "debit_credit":
            # Combine debit and credit columns
            debit_col = self.column_mapping.get('debit')
            credit_col = self.column_mapping.get('credit')

            if debit_col and credit_col:
                self.df['amount'] = self.df[debit_col].fillna(0) - self.df[credit_col].fillna(0)
                self.df['amount'] = self.df['amount'].abs()  # Always positive
                self.df['is_credit'] = self.df[credit_col].notna() & (self.df[credit_col] > 0)
        elif self.amount_convention == "negative_is_expense":
            amount_col = self.column_mapping.get('amount')
            if amount_col:
                self.df['amount'] = self.df[amount_col].abs()
                self.df['is_credit'] = self.df[amount_col] > 0
        elif self.amount_convention == "positive_is_expense":
            amount_col = self.column_mapping.get('amount')
            if amount_col:
                self.df['amount'] = self.df[amount_col].abs()
                self.df['is_credit'] = self.df[amount_col] < 0

    def _to_transactions(self) -> List[Dict[str, Any]]:
        """Convert DataFrame to transaction dictionaries."""
        transactions = []

        date_col = self.column_mapping.get('date')
        desc_col = self.column_mapping.get('description')

        for row_index, (_, row) in enumerate(self.df.iterrows()):
            try:
                # Parse date
                date_str = str(row[date_col])
                parsed_date = pd.to_datetime(date_str).date()

                # Get description
                description = str(row[desc_col]) if desc_col else ""

                # Get amount
                amount = float(row['amount'])

                transaction = {
                    'date': parsed_date.isoformat(),
                    'description_raw': description,
                    'amount': amount,
                    'currency': 'USD',  # Default, can be detected or specified
                    'metadata': row.to_dict(),
                    'row_index': row_index,  # Track position in file for deduplication
                }

                # Add is_credit flag if available
                if 'is_credit' in row:
                    transaction['is_credit'] = bool(row['is_credit'])

                transactions.append(transaction)

            except Exception as e:
                # Skip rows that can't be parsed
                continue

        return transactions

    def validate(self) -> List[str]:
        """Validate CSV data."""
        errors = []

        if self.df is None:
            errors.append("No data loaded")
            return errors

        # Check required columns exist
        required_fields = ['date', 'description']
        for field in required_fields:
            if field not in self.column_mapping:
                errors.append(f"Missing required field mapping: {field}")

        # Check amount column(s) exist
        if self.amount_convention == "debit_credit":
            if 'debit' not in self.column_mapping or 'credit' not in self.column_mapping:
                errors.append("Missing debit or credit column mapping")
        else:
            if 'amount' not in self.column_mapping:
                errors.append("Missing amount column mapping")

        # Validate mapped columns exist in DataFrame
        for field, col_name in self.column_mapping.items():
            if col_name not in self.df.columns:
                errors.append(f"Mapped column '{col_name}' not found in CSV")

        return errors
