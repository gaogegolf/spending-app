"""LLM-based transaction classifier using Claude API."""

import json
from typing import List, Dict, Any
from anthropic import Anthropic
import logging

from app.config import settings
from app.services.classifier.prompts import SYSTEM_PROMPT, build_classification_prompt
from app.models.transaction import TransactionType

logger = logging.getLogger(__name__)


class LLMClassifier:
    """Transaction classifier using Claude API."""

    def __init__(self, api_key: str = None):
        """Initialize LLM classifier.

        Args:
            api_key: Anthropic API key (defaults to settings.ANTHROPIC_API_KEY)
        """
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set")

        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-3-5-sonnet-20241022"

    def classify_batch(self, transactions: List[Dict[str, Any]],
                      batch_size: int = 20) -> List[Dict[str, Any]]:
        """Classify a batch of transactions.

        Args:
            transactions: List of transaction dicts with date, description_raw, amount
            batch_size: Number of transactions to process per API call

        Returns:
            List of classifications with transaction_type, category, is_spend, etc.
        """
        all_classifications = []

        for i in range(0, len(transactions), batch_size):
            batch = transactions[i:i + batch_size]
            try:
                batch_classifications = self._classify_single_batch(batch)
                all_classifications.extend(batch_classifications)
            except Exception as e:
                logger.error(f"Failed to classify batch {i//batch_size + 1}: {e}")
                # Return default classifications for failed batch
                for txn in batch:
                    all_classifications.append(self._default_classification(txn))

        return all_classifications

    def _classify_single_batch(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Classify a single batch using Claude API.

        Args:
            transactions: List of transaction dicts

        Returns:
            List of classifications
        """
        # Build prompt
        user_prompt = build_classification_prompt(transactions)

        # Call Claude API
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": user_prompt
            }]
        )

        # Parse response
        response_text = response.content[0].text

        # Try to parse JSON
        try:
            classifications = self._parse_json_response(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response text: {response_text}")
            # Return default classifications
            return [self._default_classification(txn) for txn in transactions]

        # Validate and enforce business rules
        validated = self._validate_classifications(classifications, transactions)

        return validated

    def _parse_json_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse JSON response from Claude.

        Args:
            response_text: Raw text from Claude

        Returns:
            Parsed JSON array

        Raises:
            json.JSONDecodeError: If JSON is invalid
        """
        # Remove markdown code blocks if present
        cleaned = response_text.strip()
        if cleaned.startswith('```'):
            # Remove markdown code blocks
            lines = cleaned.split('\n')
            cleaned = '\n'.join(lines[1:-1] if len(lines) > 2 else lines)
            if cleaned.startswith('json'):
                cleaned = cleaned[4:].strip()

        return json.loads(cleaned)

    def _validate_classifications(self, classifications: List[Dict[str, Any]],
                                  transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate LLM classifications against business rules.

        CRITICAL: This enforces the business rules that:
        - PAYMENT/TRANSFER must have is_spend=false
        - INCOME must have is_income=true, is_spend=false
        - REFUND must have is_spend=false
        - FEE_INTEREST must have is_spend=true

        Args:
            classifications: Raw classifications from LLM
            transactions: Original transaction data

        Returns:
            Validated and corrected classifications
        """
        validated = []

        for i, classification in enumerate(classifications):
            # Get original transaction for reference
            original = transactions[i] if i < len(transactions) else {}

            # Ensure all required fields exist
            txn_type = classification.get('transaction_type', 'EXPENSE')

            # CRITICAL BUSINESS RULE ENFORCEMENT
            if txn_type in ['PAYMENT', 'TRANSFER']:
                classification['is_spend'] = False
                classification['is_income'] = False

            elif txn_type == 'INCOME':
                classification['is_income'] = True
                classification['is_spend'] = False

            elif txn_type == 'REFUND':
                classification['is_spend'] = False
                classification['is_income'] = False

            elif txn_type == 'FEE_INTEREST':
                classification['is_spend'] = True
                classification['is_income'] = False

            elif txn_type == 'EXPENSE':
                classification['is_spend'] = True
                classification['is_income'] = False

            # Ensure confidence is in valid range
            confidence = classification.get('confidence', 0.8)
            classification['confidence'] = max(0.0, min(1.0, confidence))

            # Set needs_review flag for low confidence
            classification['needs_review'] = confidence < 0.6

            # Ensure category is null for non-expense types
            if txn_type not in ['EXPENSE', 'FEE_INTEREST']:
                classification['category'] = None
                classification['subcategory'] = None

            # Remove fields that are not part of the Transaction model
            # (e.g., 'reasoning', 'original_index')
            allowed_fields = {
                'transaction_type', 'category', 'subcategory', 'tags',
                'is_spend', 'is_income', 'confidence', 'needs_review',
                'classification_method'
            }

            # Filter to only allowed fields
            filtered = {k: v for k, v in classification.items() if k in allowed_fields}

            # Set classification method
            filtered['classification_method'] = 'LLM'

            validated.append(filtered)

        return validated

    def _default_classification(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Create a default classification for a transaction when LLM fails.

        Args:
            transaction: Transaction dict

        Returns:
            Default classification
        """
        description = transaction.get('description_raw', '').upper()

        # Try to detect type from keywords
        if any(keyword in description for keyword in ['PAYMENT', 'AUTOPAY', 'THANK YOU']):
            txn_type = 'PAYMENT'
            is_spend = False
            is_income = False
        elif any(keyword in description for keyword in ['PAYROLL', 'SALARY', 'DIRECT DEP']):
            txn_type = 'INCOME'
            is_spend = False
            is_income = True
        elif any(keyword in description for keyword in ['TRANSFER', 'ZELLE', 'VENMO']):
            txn_type = 'TRANSFER'
            is_spend = False
            is_income = False
        elif any(keyword in description for keyword in ['REFUND', 'RETURN']):
            txn_type = 'REFUND'
            is_spend = False
            is_income = False
        else:
            txn_type = 'EXPENSE'
            is_spend = True
            is_income = False

        return {
            'transaction_type': txn_type,
            'category': 'Other' if is_spend else None,
            'subcategory': None,
            'is_spend': is_spend,
            'is_income': is_income,
            'confidence': 0.5,
            'needs_review': True,
            'classification_method': 'DEFAULT'
        }
