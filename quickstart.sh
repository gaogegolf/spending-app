#!/bin/bash

# Personal Finance App - Quick Start Script
# This script sets up and tests the basic functionality

echo "=================================================="
echo "Personal Finance App - Quick Start"
echo "=================================================="
echo ""

# Check if we're in the right directory
if [ ! -f "README.md" ]; then
    echo "❌ Error: Please run this script from the spending-app directory"
    exit 1
fi

echo "Step 1: Setting up Python virtual environment..."
cd backend

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

echo ""
echo "Step 2: Activating virtual environment..."
source venv/bin/activate

echo ""
echo "Step 3: Installing dependencies..."
pip install -q -r requirements.txt
echo "✅ Dependencies installed"

echo ""
echo "Step 4: Checking environment configuration..."
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo ""
    echo "📝 IMPORTANT: Edit backend/.env and add your ANTHROPIC_API_KEY"
    echo "   Get your API key from: https://console.anthropic.com/"
    echo ""
    read -p "Press Enter after you've added your API key to backend/.env..."
fi

# Check if API key is set
source .env
if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "sk-ant-xxxxx" ]; then
    echo ""
    echo "❌ Error: ANTHROPIC_API_KEY not set in .env file"
    echo "   Please edit backend/.env and add your API key"
    exit 1
fi
echo "✅ API key configured"

echo ""
echo "Step 5: Initializing database..."
alembic upgrade head
echo "✅ Database initialized"

echo ""
echo "Step 6: Running Fidelity PDF test..."
cd ..
python test_fidelity_import.py

echo ""
echo "=================================================="
echo "Quick Start Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Start the API server:"
echo "   cd backend"
echo "   source venv/bin/activate"
echo "   uvicorn app.main:app --reload"
echo ""
echo "2. API will be available at: http://localhost:8000"
echo ""
echo "3. Try the demo CSV files:"
echo "   - demo-data/chase_credit_card.csv"
echo "   - demo-data/bank_checking.csv"
echo ""
echo "4. Check the comprehensive README.md for detailed usage"
echo ""
echo "=================================================="
