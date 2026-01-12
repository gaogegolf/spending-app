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

        CRITICAL: This enforces the business rules for 4 transaction types:
        - EXPENSE → is_spend=true, is_income=false
        - INCOME → is_spend=false, is_income=true
        - TRANSFER → is_spend=false, is_income=false
        - UNCATEGORIZED → is_spend=false, is_income=false

        Args:
            classifications: Raw classifications from LLM
            transactions: Original transaction data

        Returns:
            Validated and corrected classifications
        """
        validated = []
        valid_types = {'EXPENSE', 'INCOME', 'TRANSFER', 'UNCATEGORIZED'}

        for i, classification in enumerate(classifications):
            # Get original transaction for reference
            original = transactions[i] if i < len(transactions) else {}

            # Ensure all required fields exist
            txn_type = classification.get('transaction_type', 'EXPENSE')

            # Map old types to new types if LLM returns them
            type_mapping = {
                'PAYMENT': 'TRANSFER',
                'REFUND': 'INCOME',
                'FEE_INTEREST': 'EXPENSE',
            }
            if txn_type in type_mapping:
                txn_type = type_mapping[txn_type]
                classification['transaction_type'] = txn_type

            # Default to UNCATEGORIZED if type is invalid
            if txn_type not in valid_types:
                txn_type = 'UNCATEGORIZED'
                classification['transaction_type'] = txn_type

            # CRITICAL BUSINESS RULE ENFORCEMENT
            if txn_type == 'EXPENSE':
                classification['is_spend'] = True
                classification['is_income'] = False

            elif txn_type == 'INCOME':
                classification['is_income'] = True
                classification['is_spend'] = False

            elif txn_type == 'TRANSFER':
                classification['is_spend'] = False
                classification['is_income'] = False

            elif txn_type == 'UNCATEGORIZED':
                classification['is_spend'] = False
                classification['is_income'] = False
                classification['category'] = 'Uncategorized'

            # Ensure confidence is in valid range
            confidence = classification.get('confidence', 0.8)
            classification['confidence'] = max(0.0, min(1.0, confidence))

            # Set needs_review flag for low confidence or uncategorized
            classification['needs_review'] = confidence < 0.6 or txn_type == 'UNCATEGORIZED'

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

        Uses 4 transaction types: EXPENSE, INCOME, TRANSFER, UNCATEGORIZED

        IMPORTANT: Negative amounts in credit card statements represent refunds/credits
        and should be classified as INCOME, not EXPENSE.

        Args:
            transaction: Transaction dict

        Returns:
            Default classification
        """
        description = transaction.get('description_raw', '').upper()
        amount = float(transaction.get('amount', 0))

        # Priority 0: Check if this is a payment to the credit card (transfer)
        if any(keyword in description for keyword in ['PAYMENT', 'AUTOPAY', 'THANK YOU']):
            txn_type = 'TRANSFER'
            is_spend = False
            is_income = False
            category = 'Credit Card Payments'
        elif any(keyword in description for keyword in ['PAYROLL', 'SALARY', 'DIRECT DEP']):
            txn_type = 'INCOME'
            is_spend = False
            is_income = True
            category = 'Paychecks/Salary'
        elif any(keyword in description for keyword in ['TRANSFER', 'ZELLE', 'VENMO', 'CASHOUT']):
            txn_type = 'TRANSFER'
            is_spend = False
            is_income = False
            category = 'Transfers'
        elif amount < 0:
            # NEGATIVE AMOUNTS = Refunds/Credits = INCOME
            # This includes merchant refunds, card benefit credits, returned purchases
            txn_type = 'INCOME'
            is_spend = False
            is_income = True
            # Try to categorize based on description
            if any(keyword in description for keyword in ['REFUND', 'RETURN', 'REVERSAL', 'MERCHANDISE/SERVICE RETURN']):
                category = 'Refunds & Reimbursements'
            elif any(keyword in description for keyword in ['CREDIT', 'REIMBURSEMENT', 'CASHBACK']):
                category = 'Refunds & Reimbursements'
            else:
                # Use merchant-based category for better tracking
                category = self._categorize_by_merchant(description)
                if category == 'Other Expenses':
                    category = 'Refunds & Reimbursements'
        elif any(keyword in description for keyword in ['REFUND', 'RETURN', 'REVERSAL', 'MERCHANDISE/SERVICE RETURN']):
            # Explicit refund keywords even with positive amount (edge case)
            txn_type = 'INCOME'
            is_spend = False
            is_income = True
            category = 'Refunds & Reimbursements'
        elif any(keyword in description for keyword in ['LATE FEE', 'ANNUAL FEE', 'OVERDRAFT', 'INTEREST CHARGE']):
            txn_type = 'EXPENSE'
            is_spend = True
            is_income = False
            category = 'Service Charges/Fees'
        else:
            # Positive amount = EXPENSE
            txn_type = 'EXPENSE'
            is_spend = True
            is_income = False
            # Smart category matching based on merchant patterns
            category = self._categorize_by_merchant(description)

        return {
            'transaction_type': txn_type,
            'category': category,
            'subcategory': None,
            'is_spend': is_spend,
            'is_income': is_income,
            'confidence': 0.7,
            'needs_review': False,
            'classification_method': 'DEFAULT'
        }

    def _categorize_by_merchant(self, description: str) -> str:
        """Categorize transaction based on merchant name patterns using Empower categories.

        Args:
            description: Transaction description (should be uppercase)

        Returns:
            Category name
        """
        # Restaurants (most specific food category)
        restaurant_keywords = ['RESTAURANT', 'CAFE', 'COFFEE', 'STARBUCKS', 'MCDONALDS', 'BURGER', 'PIZZA',
                              'CHIPOTLE', 'PANERA', 'SUBWAY', 'DOORDASH', 'UBER EATS', 'GRUBHUB', 'POSTMATES',
                              'DINING', 'KITCHEN', 'BISTRO', 'GRILL', 'SUSHI', 'BAR', 'LUNCH', 'BREAKFAST',
                              'WENDYS', 'TACO BELL', 'KFC', 'ARBYS', 'DOMINO', 'DINER', 'BUFFET',
                              'CHILI', 'RAMEN', 'MANDARIN', 'CUISINE', 'CREPEVINE', 'PANDA EXPRESS',
                              'IN-N-OUT', 'FIVE GUYS', 'SHAKE SHACK', 'OLIVE GARDEN', 'APPLEBEES',
                              'OUTBACK', 'TEXAS ROADHOUSE', 'CHEESECAKE FACTORY', 'PF CHANG',
                              'BENIHANA', 'BOBA', 'TEA HOUSE', 'POKE', 'TAQUERIA', 'BBQ', 'STEAKHOUSE',
                              'SQ *', 'PY *', 'NUTRITION']  # Square & PayPal payments often restaurants
        if any(kw in description for kw in restaurant_keywords):
            return 'Restaurants'

        # Groceries (separate from restaurants)
        grocery_keywords = ['WHOLE FOODS', 'SAFEWAY', 'TRADER JOE', 'GROCERY', 'MARKET', 'KROGER',
                           'ALBERTSONS', 'FOOD LION', 'PUBLIX', 'WEGMANS', 'HEB', 'ALDI', 'COSTCO',
                           'SAMS CLUB', 'SUPERMARKET', 'FRESH', 'PRODUCE', 'WEEE', 'FOODLAND',
                           'FARMERS MARKET', 'ASIAN MARKET', 'RANCH 99', '99 RANCH']
        if any(kw in description for kw in grocery_keywords):
            return 'Groceries'

        # Gasoline/Fuel (specific category)
        fuel_keywords = ['SHELL', 'CHEVRON', 'MOBIL', 'EXXON', 'BP ', 'ARCO', 'VALERO', '76', 'MARATHON',
                        'GAS STATION', 'FUEL', 'PETRO', 'CIRCLE K', 'SPEEDWAY', 'PILOT', 'FLYING J']
        if any(kw in description for kw in fuel_keywords):
            return 'Gasoline/Fuel'

        # Automotive (car-related but not fuel)
        automotive_keywords = ['AUTO', 'CAR WASH', 'JIFFY LUBE', 'MIDAS', 'TIRE', 'BRAKE', 'MEINEKE',
                              'PEP BOYS', 'AUTOZONE', 'NAPA', 'O REILLY', 'CAR PARTS', 'MECHANIC',
                              'SMOG', 'REGISTRATION', 'DMV', 'PARKING', 'GARAGE', 'CHARGEPOINT',
                              'CARFAX', 'CALTRAIN', 'TRANSIT', 'TRAIN', 'METRO', 'BUS', 'BART',
                              'TOLL', 'FASTRAK', 'EZ PASS']
        if any(kw in description for kw in automotive_keywords):
            return 'Automotive'

        # Travel (hotels, airlines, etc.)
        travel_keywords = ['AIRLINE', 'AIRWAYS', 'UNITED', 'DELTA', 'AMERICAN AIR', 'SOUTHWEST', 'JETBLUE',
                          'HOTEL', 'MARRIOTT', 'HILTON', 'HYATT', 'AIRBNB', 'EXPEDIA', 'BOOKING.COM',
                          'TRAVEL', 'TRIP', 'VACATION', 'RESORT', 'INN', 'MOTEL', 'RENTAL CAR',
                          'HERTZ', 'ENTERPRISE', 'AVIS', 'BUDGET']
        if any(kw in description for kw in travel_keywords):
            return 'Travel'

        # Utilities
        utilities_keywords = ['PG&E', 'EDISON', 'ELECTRIC', 'GAS COMPANY', 'WATER DISTRICT', 'UTILITY',
                             'POWER', 'ENERGY', 'WATER BILL', 'SEWER', 'WASTE MANAGEMENT', 'TRASH']
        if any(kw in description for kw in utilities_keywords):
            return 'Utilities'

        # Cable/Satellite & Internet
        cable_keywords = ['COMCAST', 'XFINITY', 'SPECTRUM', 'COX', 'FRONTIER', 'CENTURYLINK',
                         'DIRECTV', 'DISH NETWORK', 'CABLE', 'INTERNET', 'BROADBAND', 'FIBER']
        if any(kw in description for kw in cable_keywords):
            return 'Cable/Satellite'

        # Telephone
        phone_keywords = ['VERIZON', 'AT&T', 'T-MOBILE', 'SPRINT', 'PHONE', 'WIRELESS', 'CELLULAR',
                         'MOBILE', 'CRICKET', 'METRO PCS', 'BOOST MOBILE']
        if any(kw in description for kw in phone_keywords):
            return 'Telephone'

        # Healthcare/Medical
        healthcare_keywords = ['CVS', 'WALGREENS', 'RITE AID', 'PHARMACY', 'KAISER', 'BLUE SHIELD',
                              'DOCTOR', 'DENTAL', 'DENTIST', 'MEDICAL', 'HOSPITAL', 'CLINIC',
                              'OPTOMETRY', 'VISION', 'HEALTH', 'URGENT CARE', 'LABS', 'IMAGING']
        if any(kw in description for kw in healthcare_keywords):
            return 'Healthcare/Medical'

        # Insurance
        insurance_keywords = ['INSURANCE', 'GEICO', 'STATE FARM', 'ALLSTATE', 'PROGRESSIVE', 'LIBERTY MUTUAL',
                             'FARMERS INS', 'USAA', 'AAA', 'POLICY', 'PREMIUM']
        if any(kw in description for kw in insurance_keywords):
            return 'Insurance'

        # Personal Care
        personal_keywords = ['GYM', 'FITNESS', '24 HOUR', 'LA FITNESS', 'PLANET FITNESS', 'EQUINOX',
                            'SALON', 'BARBER', 'SPA', 'MASSAGE', 'SEPHORA', 'ULTA', 'BEAUTY',
                            'NAILS', 'HAIRCUT', 'YOGA', 'CROSSFIT']
        if any(kw in description for kw in personal_keywords):
            return 'Personal Care'

        # Entertainment
        entertainment_keywords = ['NETFLIX', 'HULU', 'DISNEY', 'HBO', 'SPOTIFY', 'APPLE MUSIC',
                                 'YOUTUBE', 'TWITCH', 'THEATER', 'CINEMA', 'MOVIE', 'AMC', 'REGAL',
                                 'PLAYSTATION', 'XBOX', 'NINTENDO', 'STEAM', 'GAME', 'CONCERT',
                                 'TICKETMASTER', 'STUBHUB', 'AQUARIUM', 'MUSEUM', 'ZOO', 'AMUSEMENT',
                                 'THEME PARK', 'CHUCK E CHEESE', 'DAVE AND BUSTER', 'BOWL', 'ARCADE',
                                 'WINERY', 'VINEYARD', 'SCENIC', 'CURIODYSSEY', 'MONTEREY BAY']
        if any(kw in description for kw in entertainment_keywords):
            return 'Entertainment'

        # Dues & Subscriptions
        subscription_keywords = ['ADOBE', 'MICROSOFT 365', 'OFFICE 365', 'ICLOUD', 'DROPBOX',
                                'GITHUB', 'LINKEDIN', 'PATREON', 'SUBSTACK', 'SUBSCRIPTION',
                                'MEMBERSHIP', 'ANNUAL FEE', 'MONTHLY FEE']
        if any(kw in description for kw in subscription_keywords):
            return 'Dues & Subscriptions'

        # Home Improvement
        home_improvement_keywords = ['HOME DEPOT', 'LOWES', 'ACE HARDWARE', 'MENARDS', 'TRUE VALUE',
                                    'HARDWARE', 'LUMBER', 'CONSTRUCTION', 'REMODEL', 'RENOVATION',
                                    'SOLAR', 'PANEL', 'ROOFING']
        if any(kw in description for kw in home_improvement_keywords):
            return 'Home Improvement'

        # Home Maintenance
        home_maintenance_keywords = ['PLUMBER', 'ELECTRICIAN', 'CONTRACTOR', 'REPAIR', 'MAINTENANCE',
                                    'HVAC', 'HEATING', 'COOLING', 'ROOFING', 'PAINTING', 'CLEANING',
                                    'LAWN', 'GARDEN', 'LANDSCAPE', 'MAID', 'HANDYMAN']
        if any(kw in description for kw in home_maintenance_keywords):
            return 'Home Maintenance'

        # Pets/Pet Care
        pet_keywords = ['PETCO', 'PETSMART', 'VET', 'VETERINARY', 'PET', 'ANIMAL HOSPITAL',
                       'DOG', 'CAT', 'GROOMING']
        if any(kw in description for kw in pet_keywords):
            return 'Pets/Pet Care'

        # Education
        education_keywords = ['UNIVERSITY', 'COLLEGE', 'SCHOOL', 'TUITION', 'COURSERA', 'UDEMY',
                             'EDUCATION', 'LEARNING', 'TEXTBOOK', 'HOMEROOM', 'ACADEMY', 'INSTITUTE',
                             'BOOKSTORE', 'BOOKS', 'LINDEN TREE']
        if any(kw in description for kw in education_keywords):
            return 'Education'

        # Electronics
        electronics_keywords = ['BEST BUY', 'APPLE STORE', 'MICROSOFT STORE', 'ELECTRONICS', 'COMPUTER',
                               'LAPTOP', 'PHONE STORE', 'TECH', 'GEEK SQUAD', 'MICRO CENTER']
        if any(kw in description for kw in electronics_keywords):
            return 'Electronics'

        # Clothing/Shoes
        clothing_keywords = ['MACYS', 'NORDSTROM', 'KOHLS', 'GAP ', 'OLD NAVY', 'BANANA REPUBLIC',
                            'FOREVER 21', 'H&M', ' HM ', 'ZARA', 'NIKE', 'ADIDAS', 'CLOTHING', 'APPAREL',
                            'SHOES', 'FOOTWEAR', 'FASHION', 'UNIQLO', 'CROCS', 'JEANS', 'VANS',
                            'CONVERSE', 'SKECHERS', 'DRESS', 'SUIT', 'TUXEDO', 'DILLARD', 'BLOOMINGDALE',
                            'NEIMAN MARCUS', 'SAKS', 'JCPENNEY', 'NORDSTROM RACK', 'OFF 5TH',
                            'ATHLETIC', 'FOOTLOCKER', 'FINISH LINE', 'DICK SPORTING', 'REI']
        if any(kw in description for kw in clothing_keywords):
            return 'Clothing/Shoes'

        # Charitable Giving
        charity_keywords = ['DONATION', 'CHARITY', 'FOUNDATION', 'NON-PROFIT', 'GOODWILL',
                           'SALVATION ARMY', 'RED CROSS', 'UNITED WAY', 'GIVING']
        if any(kw in description for kw in charity_keywords):
            return 'Charitable Giving'

        # Gifts
        gift_keywords = ['GIFT', 'FLOWERS', 'FLORIST', '1-800-FLOWERS', 'EDIBLE ARRANGEMENTS',
                        'HALLMARK', 'CARD STORE']
        if any(kw in description for kw in gift_keywords):
            return 'Gifts'

        # Hobbies
        hobby_keywords = ['HOBBY', 'CRAFT', 'MICHAELS', 'JOANN', 'FABRIC', 'ART SUPPLY',
                         'MUSIC STORE', 'INSTRUMENT', 'SPORTING GOODS', 'BICYCLE', 'BIKE SHOP',
                         'SPORTS', 'TENNIS', 'GOLF', 'SWIM']
        if any(kw in description for kw in hobby_keywords):
            return 'Hobbies'

        # Online Services
        online_keywords = ['PAYPAL', 'VENMO', 'SQUARE', 'STRIPE', 'ONLINE', 'DIGITAL', 'CLOUD',
                          'HOSTING', 'DOMAIN', 'WEB']
        if any(kw in description for kw in online_keywords):
            return 'Online Services'

        # Taxes
        tax_keywords = ['TAX BOARD', 'FRANCHISE TAX', 'IRS', 'TAX PAYMENT', 'PROPERTY TAX',
                       'INCOME TAX', 'STATE TAX', 'FEDERAL TAX', 'TAX RETURN', 'US TREAS TAX']
        if any(kw in description for kw in tax_keywords):
            return 'Taxes'

        # ATM/Cash
        atm_keywords = ['ATM', 'CASH WITHDRAWAL', 'CASH ADVANCE', 'WITHDRAW']
        if any(kw in description for kw in atm_keywords):
            return 'ATM/Cash'

        # Groceries (additional patterns - check again for meat/butcher shops & convenience stores)
        grocery_keywords2 = ['MEAT HOUSE', 'BUTCHER', 'SEAFOOD', 'FISH MARKET', '7-ELEVEN', '7 ELEVEN',
                            'CONVENIENCE', 'CORNER STORE', 'MINI MART', 'ABC STORE', 'ABC #']
        if any(kw in description for kw in grocery_keywords2):
            return 'Groceries'

        # Pets/Pet Care (additional patterns)
        pet_keywords2 = ['CHEWY', 'PET SUPPLIES', 'PET FOOD']
        if any(kw in description for kw in pet_keywords2):
            return 'Pets/Pet Care'

        # Travel (additional patterns - cruise lines, vacation packages, scenic drives)
        travel_keywords2 = ['CRUISE', 'DCL', 'CARNIVAL', 'ROYAL CARIBBEAN', 'NORWEGIAN',
                           'PRINCESS CRUISES', 'VACATION PACKAGE', '17 MILE DRIVE', 'SCENIC DRIVE',
                           'GATES', 'RESERVATIONS']
        if any(kw in description for kw in travel_keywords2):
            return 'Travel'

        # General Merchandise (big box stores)
        general_merchandise_keywords = ['AMAZON', 'TARGET', 'WALMART', 'COSTCO', 'SAMS CLUB',
                                       'BJS', 'DOLLAR', 'TJ MAXX', 'MARSHALLS', 'ROSS',
                                       'BED BATH', 'IKEA', 'JEWI', 'JEWELRY']
        if any(kw in description for kw in general_merchandise_keywords):
            return 'General Merchandise'

        # Default to Other Expenses for unrecognized merchants
        return 'Other Expenses'
