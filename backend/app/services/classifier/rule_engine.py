"""Rule engine for user-defined transaction classification rules."""

import re
import json
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.rule import Rule, RuleType
from app.models.transaction import Transaction


class RuleEngine:
    """Engine for applying user-defined classification rules to transactions."""

    def __init__(self, db: Session):
        """Initialize rule engine.

        Args:
            db: Database session
        """
        self.db = db
        self._rules_cache: Optional[List[Rule]] = None

    def load_active_rules(self, user_id: str) -> List[Rule]:
        """Load active rules from database, sorted by priority.

        Args:
            user_id: User ID to load rules for

        Returns:
            List of active rules, sorted by priority (lower number = higher priority)
        """
        self._rules_cache = self.db.query(Rule).filter(
            Rule.user_id == user_id,
            Rule.is_active == True
        ).order_by(Rule.priority.asc()).all()

        return self._rules_cache

    def match_transaction(self, transaction: Transaction, user_id: Optional[str] = None) -> Optional[Rule]:
        """Find the first matching rule for a transaction.

        Rules are applied in priority order (lower priority number = higher priority).
        Returns the first rule that matches.

        Args:
            transaction: Transaction to match
            user_id: User ID for loading rules (optional, will try to get from transaction.account)

        Returns:
            Matching Rule or None
        """
        if not self._rules_cache:
            # Get user_id from account if not provided
            if not user_id and hasattr(transaction, 'account') and transaction.account:
                user_id = transaction.account.user_id
            if user_id:
                self.load_active_rules(user_id)
            else:
                return None  # No user_id available, can't load rules

        for rule in self._rules_cache or []:
            if self._rule_matches(rule, transaction):
                # Update rule match statistics
                rule.match_count += 1
                rule.last_matched_at = datetime.utcnow()
                return rule

        return None

    def _rule_matches(self, rule: Rule, transaction: Transaction) -> bool:
        """Check if a rule matches a transaction.

        Args:
            rule: Rule to check
            transaction: Transaction to match against

        Returns:
            True if rule matches
        """
        if rule.rule_type == RuleType.MERCHANT_MATCH:
            return self._merchant_match(rule.pattern, transaction)

        elif rule.rule_type == RuleType.DESCRIPTION_REGEX:
            return self._description_regex_match(rule.pattern, transaction)

        elif rule.rule_type == RuleType.AMOUNT_RANGE:
            return self._amount_range_match(rule.pattern, transaction)

        elif rule.rule_type == RuleType.COMPOSITE:
            return self._composite_match(rule.pattern, transaction)

        return False

    def _merchant_match(self, pattern: str, transaction: Transaction) -> bool:
        """Match based on merchant name (substring match, case-insensitive).

        Args:
            pattern: Pattern string to match
            transaction: Transaction to match

        Returns:
            True if pattern found in merchant or description
        """
        pattern_lower = pattern.lower()

        merchant = (transaction.merchant_normalized or '').lower()
        description = (transaction.description_raw or '').lower()

        return pattern_lower in merchant or pattern_lower in description

    def _description_regex_match(self, pattern: str, transaction: Transaction) -> bool:
        """Match based on regex pattern in description.

        Args:
            pattern: Regex pattern string
            transaction: Transaction to match

        Returns:
            True if regex matches
        """
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            description = transaction.description_raw or ''
            return bool(regex.search(description))
        except re.error:
            return False

    def _amount_range_match(self, pattern: str, transaction: Transaction) -> bool:
        """Match based on amount range.

        Pattern should be JSON: {"min": 0, "max": 100}

        Args:
            pattern: JSON string with min/max
            transaction: Transaction to match

        Returns:
            True if amount in range
        """
        try:
            range_data = json.loads(pattern)
            min_amount = range_data.get('min', 0)
            max_amount = range_data.get('max', float('inf'))

            amount = float(transaction.amount)
            return min_amount <= amount <= max_amount
        except (json.JSONDecodeError, ValueError, KeyError):
            return False

    def _composite_match(self, pattern: str, transaction: Transaction) -> bool:
        """Match based on multiple conditions (AND logic).

        Pattern should be JSON with multiple conditions:
        {
            "merchant": "Amazon",
            "amount_min": 10,
            "amount_max": 100,
            "description_regex": "PRIME"
        }

        Args:
            pattern: JSON string with conditions
            transaction: Transaction to match

        Returns:
            True if all conditions match
        """
        try:
            conditions = json.loads(pattern)

            # Check merchant condition
            if 'merchant' in conditions:
                if not self._merchant_match(conditions['merchant'], transaction):
                    return False

            # Check amount range
            if 'amount_min' in conditions or 'amount_max' in conditions:
                amount = float(transaction.amount)
                if 'amount_min' in conditions and amount < conditions['amount_min']:
                    return False
                if 'amount_max' in conditions and amount > conditions['amount_max']:
                    return False

            # Check regex
            if 'description_regex' in conditions:
                if not self._description_regex_match(conditions['description_regex'], transaction):
                    return False

            return True

        except (json.JSONDecodeError, ValueError):
            return False

    def apply_rule(self, rule: Rule, transaction: Transaction) -> Transaction:
        """Apply a rule's action to a transaction.

        The rule's action is a JSON dict that can specify:
        - transaction_type
        - category
        - subcategory
        - is_spend
        - is_income
        - tags

        Args:
            rule: Rule to apply
            transaction: Transaction to modify

        Returns:
            Modified transaction
        """
        action = rule.action

        # Apply transaction type
        if 'transaction_type' in action:
            transaction.transaction_type = action['transaction_type']

        # Apply category/subcategory
        if 'category' in action:
            transaction.category = action['category']
        if 'subcategory' in action:
            transaction.subcategory = action['subcategory']

        # Apply spending flags (only if explicitly set to True/False, not None)
        if action.get('is_spend') is not None:
            transaction.is_spend = action['is_spend']
        if action.get('is_income') is not None:
            transaction.is_income = action['is_income']

        # If transaction_type was set but is_spend/is_income weren't, infer from type
        if 'transaction_type' in action:
            txn_type = action['transaction_type']
            if action.get('is_spend') is None:
                transaction.is_spend = txn_type == 'EXPENSE'
            if action.get('is_income') is None:
                transaction.is_income = txn_type == 'INCOME'

        # Apply tags
        if 'tags' in action:
            transaction.tags = action['tags']

        # Mark as classified by rule
        transaction.matched_rule_id = rule.id
        transaction.classification_method = 'RULE'
        transaction.confidence = 1.0  # Rules are deterministic
        transaction.needs_review = False  # Rules are user-defined, no review needed

        return transaction

    def match_transaction_data(self, txn_data: dict, user_id: Optional[str] = None) -> Optional[Rule]:
        """Find the first matching rule for transaction data (dict, before DB insert).

        Args:
            txn_data: Transaction data dictionary
            user_id: User ID for loading rules

        Returns:
            Matching Rule or None
        """
        if not self._rules_cache and user_id:
            self.load_active_rules(user_id)

        for rule in self._rules_cache or []:
            if self._rule_matches_data(rule, txn_data):
                # Update rule match statistics
                rule.match_count += 1
                rule.last_matched_at = datetime.utcnow()
                return rule

        return None

    def _rule_matches_data(self, rule: Rule, txn_data: dict) -> bool:
        """Check if a rule matches transaction data.

        Args:
            rule: Rule to check
            txn_data: Transaction data dict to match against

        Returns:
            True if rule matches
        """
        if rule.rule_type == RuleType.MERCHANT_MATCH:
            return self._merchant_match_data(rule.pattern, txn_data)

        elif rule.rule_type == RuleType.DESCRIPTION_REGEX:
            return self._description_regex_match_data(rule.pattern, txn_data)

        elif rule.rule_type == RuleType.AMOUNT_RANGE:
            return self._amount_range_match_data(rule.pattern, txn_data)

        elif rule.rule_type == RuleType.COMPOSITE:
            return self._composite_match_data(rule.pattern, txn_data)

        return False

    def _merchant_match_data(self, pattern: str, txn_data: dict) -> bool:
        """Match based on merchant name (for transaction data)."""
        pattern_lower = pattern.lower()
        merchant = (txn_data.get('merchant_normalized') or '').lower()
        description = (txn_data.get('description_raw') or '').lower()
        return pattern_lower in merchant or pattern_lower in description

    def _description_regex_match_data(self, pattern: str, txn_data: dict) -> bool:
        """Match based on regex pattern (for transaction data)."""
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            description = txn_data.get('description_raw') or ''
            return bool(regex.search(description))
        except re.error:
            return False

    def _amount_range_match_data(self, pattern: str, txn_data: dict) -> bool:
        """Match based on amount range (for transaction data)."""
        try:
            range_data = json.loads(pattern)
            min_amount = range_data.get('min', 0)
            max_amount = range_data.get('max', float('inf'))
            amount = float(txn_data.get('amount', 0))
            return min_amount <= amount <= max_amount
        except (json.JSONDecodeError, ValueError, KeyError):
            return False

    def _composite_match_data(self, pattern: str, txn_data: dict) -> bool:
        """Match based on multiple conditions (for transaction data)."""
        try:
            conditions = json.loads(pattern)

            if 'merchant' in conditions:
                if not self._merchant_match_data(conditions['merchant'], txn_data):
                    return False

            if 'amount_min' in conditions or 'amount_max' in conditions:
                amount = float(txn_data.get('amount', 0))
                if 'amount_min' in conditions and amount < conditions['amount_min']:
                    return False
                if 'amount_max' in conditions and amount > conditions['amount_max']:
                    return False

            if 'description_regex' in conditions:
                if not self._description_regex_match_data(conditions['description_regex'], txn_data):
                    return False

            return True

        except (json.JSONDecodeError, ValueError):
            return False

    def apply_rule_to_data(self, rule: Rule, txn_data: dict) -> dict:
        """Apply a rule's action to transaction data (dict, before DB insert).

        Args:
            rule: Rule to apply
            txn_data: Transaction data dictionary

        Returns:
            Modified transaction data dictionary
        """
        action = rule.action

        # Create copy to avoid modifying original
        result = txn_data.copy()

        # Apply transaction type
        if 'transaction_type' in action:
            result['transaction_type'] = action['transaction_type']

        # Apply category/subcategory
        if 'category' in action:
            result['category'] = action['category']
        if 'subcategory' in action:
            result['subcategory'] = action['subcategory']

        # Apply spending flags (only if explicitly set to True/False, not None)
        if action.get('is_spend') is not None:
            result['is_spend'] = action['is_spend']
        if action.get('is_income') is not None:
            result['is_income'] = action['is_income']

        # If transaction_type was set but is_spend/is_income weren't, infer from type
        if 'transaction_type' in action:
            txn_type = action['transaction_type']
            if action.get('is_spend') is None:
                result['is_spend'] = txn_type == 'EXPENSE'
            if action.get('is_income') is None:
                result['is_income'] = txn_type == 'INCOME'

        # Apply tags
        if 'tags' in action:
            result['tags'] = action['tags']

        # Mark as classified by rule
        result['matched_rule_id'] = rule.id
        result['classification_method'] = 'RULE'
        result['confidence'] = 1.0
        result['needs_review'] = False

        return result
