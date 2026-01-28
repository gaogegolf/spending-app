"""FX Rate Service - handles currency conversion with API fallback and caching."""

import logging
from typing import Optional, Tuple, List, Dict, Any
from datetime import date
from decimal import Decimal
import uuid

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.fx_rate import FxRate
from app.config import settings

logger = logging.getLogger(__name__)


class FxRateService:
    """Service for FX rate lookups and currency conversion."""

    def __init__(self, db: Session):
        """Initialize FX rate service.

        Args:
            db: Database session
        """
        self.db = db
        self.api_url = getattr(settings, 'FX_RATE_API_URL', 'https://api.exchangerate.host')
        self.enabled = getattr(settings, 'ENABLE_FX_CONVERSION', True)

    def get_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate_date: date
    ) -> Optional[Decimal]:
        """Get FX rate for a currency pair on a specific date.

        Checks database cache first, falls back to API if not found.

        Args:
            from_currency: Source currency code (e.g., "EUR")
            to_currency: Target currency code (e.g., "USD")
            rate_date: Date for the rate

        Returns:
            Exchange rate as Decimal, or None if not available
        """
        if from_currency == to_currency:
            return Decimal("1.0")

        if not self.enabled:
            logger.debug("FX conversion disabled, returning None")
            return None

        # Check database cache first
        cached_rate = self._get_cached_rate(from_currency, to_currency, rate_date)
        if cached_rate is not None:
            logger.debug(f"Using cached rate for {from_currency}/{to_currency} on {rate_date}: {cached_rate}")
            return cached_rate

        # Fetch from API
        api_rate = self._fetch_rate_from_api(from_currency, to_currency, rate_date)
        if api_rate is not None:
            # Cache the result
            self._cache_rate(from_currency, to_currency, rate_date, api_rate)
            return api_rate

        logger.warning(f"Could not get FX rate for {from_currency}/{to_currency} on {rate_date}")
        return None

    def convert_to_usd(
        self,
        amount: Decimal,
        currency: str,
        transaction_date: date
    ) -> Tuple[Optional[Decimal], Optional[Decimal], str]:
        """Convert an amount to USD.

        Args:
            amount: Amount in original currency
            currency: Source currency code
            transaction_date: Date for the conversion rate

        Returns:
            Tuple of (amount_usd, rate_used, source)
            - amount_usd: Converted amount in USD, or None if conversion failed
            - rate_used: The FX rate used, or None
            - source: "statement", "api", or "none"
        """
        if currency is None or currency.upper() == "USD":
            return (amount, None, "none")

        currency = currency.upper()

        if not self.enabled:
            return (None, None, "none")

        rate = self.get_rate(currency, "USD", transaction_date)
        if rate is None:
            return (None, None, "none")

        amount_usd = amount * rate
        # Round to 2 decimal places
        amount_usd = Decimal(str(round(float(amount_usd), 2)))

        # Determine source (check if rate came from statement or API)
        cached = self._get_cached_rate_record(currency, "USD", transaction_date)
        source = cached.source if cached else "api"

        return (amount_usd, rate, source)

    def batch_convert(
        self,
        transactions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert a batch of transactions to USD.

        Optimizes by grouping transactions by currency and date to minimize API calls.

        Args:
            transactions: List of transaction dicts with 'amount', 'currency', 'date' keys

        Returns:
            List of transaction dicts with added 'amount_usd', 'fx_rate_used',
            'fx_rate_date', 'fx_rate_source' fields
        """
        if not self.enabled:
            # If FX conversion is disabled, just set USD transactions and return
            for txn in transactions:
                currency = txn.get('currency', 'USD')
                if currency is None or currency.upper() == 'USD':
                    txn['amount_usd'] = txn.get('amount')
                    txn['fx_rate_used'] = None
                    txn['fx_rate_date'] = None
                    txn['fx_rate_source'] = 'none'
                else:
                    txn['amount_usd'] = None
                    txn['fx_rate_used'] = None
                    txn['fx_rate_date'] = None
                    txn['fx_rate_source'] = 'none'
            return transactions

        # Group by (currency, date) to batch API calls
        rate_cache: Dict[Tuple[str, date], Tuple[Optional[Decimal], str]] = {}

        for txn in transactions:
            currency = txn.get('currency', 'USD')
            txn_date = txn.get('date')

            # Handle date parsing
            if isinstance(txn_date, str):
                from datetime import datetime
                txn_date = datetime.fromisoformat(txn_date).date()

            if currency is None or currency.upper() == 'USD':
                txn['amount_usd'] = txn.get('amount')
                txn['fx_rate_used'] = None
                txn['fx_rate_date'] = None
                txn['fx_rate_source'] = 'none'
                continue

            currency = currency.upper()
            cache_key = (currency, txn_date)

            # Check our local batch cache first
            if cache_key not in rate_cache:
                rate = self.get_rate(currency, 'USD', txn_date)
                # Determine source
                cached_record = self._get_cached_rate_record(currency, 'USD', txn_date)
                source = cached_record.source if cached_record else 'api'
                rate_cache[cache_key] = (rate, source)

            rate, source = rate_cache[cache_key]

            if rate is not None:
                amount = Decimal(str(txn.get('amount', 0)))
                amount_usd = amount * rate
                amount_usd = Decimal(str(round(float(amount_usd), 2)))

                txn['amount_usd'] = amount_usd
                txn['fx_rate_used'] = rate
                txn['fx_rate_date'] = txn_date
                txn['fx_rate_source'] = source
            else:
                txn['amount_usd'] = None
                txn['fx_rate_used'] = None
                txn['fx_rate_date'] = None
                txn['fx_rate_source'] = 'none'

        return transactions

    def _get_cached_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate_date: date
    ) -> Optional[Decimal]:
        """Get a cached rate from the database."""
        record = self._get_cached_rate_record(from_currency, to_currency, rate_date)
        return record.rate if record else None

    def _get_cached_rate_record(
        self,
        from_currency: str,
        to_currency: str,
        rate_date: date
    ) -> Optional[FxRate]:
        """Get a cached rate record from the database."""
        return self.db.query(FxRate).filter(
            and_(
                FxRate.from_currency == from_currency.upper(),
                FxRate.to_currency == to_currency.upper(),
                FxRate.rate_date == rate_date
            )
        ).first()

    def _cache_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate_date: date,
        rate: Decimal
    ) -> None:
        """Cache a rate in the database."""
        fx_rate = FxRate(
            id=str(uuid.uuid4()),
            snapshot_id=None,  # No snapshot for API-fetched rates
            from_currency=from_currency.upper(),
            to_currency=to_currency.upper(),
            rate=rate,
            rate_date=rate_date,
            source="api"
        )
        self.db.add(fx_rate)
        self.db.commit()
        logger.info(f"Cached FX rate: {from_currency}/{to_currency} = {rate} for {rate_date}")

    def _fetch_rate_from_api(
        self,
        from_currency: str,
        to_currency: str,
        rate_date: date
    ) -> Optional[Decimal]:
        """Fetch FX rate from external API.

        Uses Frankfurter API (free, no API key required) for historical rates.

        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            rate_date: Date for the rate

        Returns:
            Exchange rate as Decimal, or None if API call failed
        """
        try:
            # Format: https://api.frankfurter.app/2024-01-15?from=EUR&to=USD
            date_str = rate_date.isoformat()
            url = f"{self.api_url}/{date_str}"
            params = {
                "from": from_currency.upper(),
                "to": to_currency.upper()
            }

            logger.info(f"Fetching FX rate from API: {url} with params {params}")

            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()

                data = response.json()

                # Check for error response
                if "error" in data:
                    logger.error(f"API returned error: {data}")
                    return None

                # Extract rate from response
                # Frankfurter format: {"amount":1.0,"base":"EUR","date":"2024-01-15","rates":{"USD":1.0945}}
                rates = data.get("rates", {})
                rate = rates.get(to_currency.upper())

                if rate is not None:
                    rate = Decimal(str(rate))
                    logger.info(f"Fetched FX rate: {from_currency}/{to_currency} = {rate} for {rate_date}")
                    return rate
                else:
                    logger.warning(f"Rate not found in API response: {data}")
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching FX rate: {e}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error fetching FX rate: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching FX rate: {e}")
            return None
