#!/bin/bash

BASE_URL="https://lowkey-backend-omega.vercel.app"

echo "Testing Health Endpoint..."
echo "=========================="
curl -s "$BASE_URL/health"
echo -e "\n"

echo "Testing Product List Query..."
echo "============================="
curl -s -X POST "$BASE_URL/" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "query",
    "operation": "product.list",
    "params": {
      "page": 1,
      "pageSize": 5
    }
  }'
echo -e "\n"

echo "Testing Category List Query..."
echo "=============================="
curl -s -X POST "$BASE_URL/" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "query",
    "operation": "category.list",
    "params": {}
  }'
