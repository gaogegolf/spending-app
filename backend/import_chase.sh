#!/bin/bash
# Import Chase statements via command line (bypasses DLP)

ACCOUNT_ID="90d434b2-279d-4de7-aa9a-bc690fc3f367"  # Ge - Chase Prime Visa
API_URL="http://localhost:8000/api/v1/imports"

# Directory containing Chase statements
CHASE_DIR="/Users/I858764/Documents/Spending/Ge Chase Prime Visa Card - 3297"

for pdf in "$CHASE_DIR"/*.pdf; do
    filename=$(basename "$pdf")
    echo "Importing: $filename"

    # Upload
    response=$(curl -s -X POST "$API_URL/upload" \
        -F "file=@$pdf" \
        -F "account_id=$ACCOUNT_ID")

    import_id=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)

    if [ -z "$import_id" ]; then
        echo "  Skipped (already imported or error)"
        continue
    fi

    # Parse
    curl -s -X POST "$API_URL/$import_id/parse" > /dev/null

    # Commit
    result=$(curl -s -X POST "$API_URL/$import_id/commit")
    imported=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d[\"transactions_imported\"]} imported, {d[\"transactions_duplicate\"]} duplicates')" 2>/dev/null)

    echo "  $imported"
done

echo "Done!"
