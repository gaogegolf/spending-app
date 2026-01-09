"""Base parser interface."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class ParseResult:
    """Result of parsing a file."""

    success: bool
    transactions: List[Dict[str, Any]]
    errors: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]


class BaseParser(ABC):
    """Abstract base class for file parsers."""

    @abstractmethod
    def parse(self) -> ParseResult:
        """Parse file and return transactions.

        Returns:
            ParseResult with transactions and any errors/warnings.
        """
        pass

    @abstractmethod
    def detect_format(self) -> Dict[str, Any]:
        """Detect file format and column mappings.

        Returns:
            Dictionary with detected format information.
        """
        pass

    @abstractmethod
    def validate(self) -> List[str]:
        """Validate file contents.

        Returns:
            List of validation errors.
        """
        pass
