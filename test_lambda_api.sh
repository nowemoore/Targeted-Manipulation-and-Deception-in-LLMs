#!/bin/bash
# Quick test script for Lambda Cloud API connection

set -e

echo "Testing Lambda Cloud API connection..."
echo "=========================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ ERROR: .env file not found"
    echo "Please create .env file with your LAMBDA_CLOUD_API_KEY"
    echo "See .env.example for template"
    exit 1
fi

# Check if LAMBDA_CLOUD_API_KEY is set
LAMBDA_KEY=$(grep LAMBDA_CLOUD_API_KEY .env | cut -d= -f2 | tr -d ' "'"'"'')

if [ -z "$LAMBDA_KEY" ]; then
    echo "❌ ERROR: LAMBDA_CLOUD_API_KEY not found in .env file"
    exit 1
fi

echo "✓ Found Lambda Cloud API key"
echo ""

# Test API connection
echo "Testing API connection..."
RESPONSE=$(curl -s -u "${LAMBDA_KEY}:" https://cloud.lambda.ai/api/v1/instances)

# Check if response contains error
if echo "$RESPONSE" | grep -q '"error"'; then
    echo "❌ API Error:"
    echo "$RESPONSE" | jq '.error' 2>/dev/null || echo "$RESPONSE"
    exit 1
fi

echo "✓ API connection successful!"
echo ""

# Show current instances
INSTANCE_COUNT=$(echo "$RESPONSE" | jq '.data | length' 2>/dev/null || echo "0")
echo "Current instances: $INSTANCE_COUNT"

if [ "$INSTANCE_COUNT" -gt 0 ]; then
    echo ""
    echo "Active instances:"
    echo "$RESPONSE" | jq -r '.data[] | "  - \(.name // .id): \(.instance_type.name) in \(.region.name) (\(.status))"' 2>/dev/null || echo "  (details unavailable)"
fi

echo ""
echo "=========================================="
echo "✅ All tests passed!"
echo ""
echo "Next steps:"
echo "  1. List available instance types:"
echo "     python lambda_cloud_utils.py list-instance-types"
echo ""
echo "  2. Launch experiments (dry run first):"
echo "     python launch_kto_experiments.py --ssh-key-name <your-key> --dry-run"
echo ""
echo "  3. See LAMBDA_CLOUD_QUICKSTART.md for more details"
