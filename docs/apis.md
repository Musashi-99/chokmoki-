# API Documentation

## Base URL

**Local Development:**
```
http://localhost:8000/api
```

**Production (Vercel):**
```
https://your-domain.vercel.app/api
```

## Request Format

All requests are **POST** requests to a single endpoint. The request body follows this structure:

```json
{
  "type": "query" | "mutation",
  "operation": "operation.name",
  "params": {
    // operation-specific parameters
  }
}
```

## Response Format

**Success Response:**
```json
{
  "data": {
    // response data
  },
  "count": 0  // for list operations
}
```

**Error Response:**
```json
{
  "error": "Error message"
}
```

## React Frontend Example

```typescript
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

async function callAPI(type: 'query' | 'mutation', operation: string, params: any) {
  const response = await fetch(`${API_BASE_URL}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      type,
      operation,
      params,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'API request failed');
  }

  return response.json();
}

// Usage example
const products = await callAPI('query', 'product.list', { skip: 0, limit: 20 });
```

---

## Product Operations

### Query: product.list

List all products with optional filters.

**Request:**
```json
{
  "type": "query",
  "operation": "product.list",
  "params": {
    "skip": 0,
    "limit": 20,
    "active": true,
    "category_id": "category_id_string",
    "include_categories": true
  }
}
```

**Response:**
```json
{
  "data": [
    <PRODUCT_SCHEMA>
  ],
  "count": 10
}
```

**Product Schema:**
```typescript
{
  "_id": "string",
  "name": "string",
  "brand": "string",
  "categories": ["string"],
  "product_description": "string",
  "mrp_price": 0.0,
  "selling_price": 0.0,
  "tags": ["string"],
  "medias": [
    {
      "url": "string",
      "mimetype": "string",
      "size": 0
    }
  ],
  "features": ["string"],
  "active": true,
  "product_variants": [
    {
      "variant_name": "string",
      "variant_values": [
        {
          "label": "string",
          "active": true
        }
      ]
    }
  ],
  "category_details": [
    {
      "_id": "string",
      "name": "string",
      "description": "string",
      "discount": {
        "rate": 0.0,
        "type": "percentage" | "direct"
      },
      "medias": []
    }
  ]
}
```

### Query: product.get

Get a single product by ID.

**Request:**
```json
{
  "type": "query",
  "operation": "product.get",
  "params": {
    "id": "product_id_string"
  }
}
```

**Response:**
```json
{
  "data": <PRODUCT_SCHEMA>
}
```

### Query: product.search

Search products by name, brand, tags, or description.

**Request:**
```json
{
  "type": "query",
  "operation": "product.search",
  "params": {
    "search_term": "search string",
    "skip": 0,
    "limit": 20,
    "include_categories": true
  }
}
```

**Response:**
```json
{
  "data": [
    <PRODUCT_SCHEMA>
  ],
  "count": 5
}
```

### Mutation: product.create

Create a new product.

**Request:**
```json
{
  "type": "mutation",
  "operation": "product.create",
  "params": {
    "name": "string",
    "brand": "string",
    "categories": ["category_id_string"],
    "product_description": "string",
    "mrp_price": 0.0,
    "selling_price": 0.0,
    "tags": ["string"],
    "medias": [
      {
        "url": "string",
        "mimetype": "string",
        "size": 0
      }
    ],
    "features": ["string"],
    "active": true,
    "product_variants": [
      {
        "variant_name": "string",
        "variant_values": [
          {
            "label": "string",
            "active": true
          }
        ]
      }
    ]
  }
}
```

**Note:** If `product_variants` is empty or not provided, a default variant will be created automatically.

**Response:**
```json
{
  "data": <PRODUCT_SCHEMA>
}
```

### Mutation: product.update

Update an existing product.

**Request:**
```json
{
  "type": "mutation",
  "operation": "product.update",
  "params": {
    "id": "product_id_string",
    "name": "string",
    "selling_price": 0.0
    // ... any other product fields to update
  }
}
```

**Response:**
```json
{
  "data": <PRODUCT_SCHEMA>
}
```

### Mutation: product.delete

Delete a product.

**Request:**
```json
{
  "type": "mutation",
  "operation": "product.delete",
  "params": {
    "id": "product_id_string"
  }
}
```

**Response:**
```json
{
  "success": true
}
```

---

## Category Operations

### Query: category.list

List all categories.

**Request:**
```json
{
  "type": "query",
  "operation": "category.list",
  "params": {
    "skip": 0,
    "limit": 20
  }
}
```

**Response:**
```json
{
  "data": [
    <CATEGORY_SCHEMA>
  ],
  "count": 5
}
```

**Category Schema:**
```typescript
{
  "_id": "string",
  "name": "string",
  "description": "string",
  "medias": [
    {
      "url": "string",
      "mimetype": "string",
      "size": 0
    }
  ],
  "discount": {
    "rate": 0.0,
    "type": "percentage" | "direct"
  }
}
```

### Query: category.get

Get a single category by ID.

**Request:**
```json
{
  "type": "query",
  "operation": "category.get",
  "params": {
    "id": "category_id_string"
  }
}
```

**Response:**
```json
{
  "data": <CATEGORY_SCHEMA>
}
```

### Mutation: category.create

Create a new category.

**Request:**
```json
{
  "type": "mutation",
  "operation": "category.create",
  "params": {
    "name": "string",
    "description": "string",
    "medias": [
      {
        "url": "string",
        "mimetype": "string",
        "size": 0
      }
    ],
    "discount": {
      "rate": 0.0,
      "type": "percentage"
    }
  }
}
```

**Response:**
```json
{
  "data": <CATEGORY_SCHEMA>
}
```

### Mutation: category.update

Update an existing category.

**Request:**
```json
{
  "type": "mutation",
  "operation": "category.update",
  "params": {
    "id": "category_id_string",
    "name": "string",
    "discount": {
      "rate": 0.0,
      "type": "percentage"
    }
    // ... any other category fields to update
  }
}
```

**Response:**
```json
{
  "data": <CATEGORY_SCHEMA>
}
```

### Mutation: category.delete

Delete a category.

**Request:**
```json
{
  "type": "mutation",
  "operation": "category.delete",
  "params": {
    "id": "category_id_string"
  }
}
```

**Response:**
```json
{
  "success": true
}
```

---

## Order Operations

### Query: order.list

List all orders.

**Request:**
```json
{
  "type": "query",
  "operation": "order.list",
  "params": {
    "skip": 0,
    "limit": 20
  }
}
```

**Response:**
```json
{
  "data": [
    <ORDER_SCHEMA>
  ],
  "count": 10
}
```

**Order Schema:**
```typescript
{
  "_id": "string",
  "total_amount": 0.0,
  "total_discount": 0.0,
  "order_items": [
    {
      "product": {},  // full product object
      "quantity": 0
    }
  ],
  "shipping_details": {
    "phone": "string",
    "email": "string",
    "clerk_token": "string",
    "address": "string"
  },
  "status": {
    "type": "accepted" | "rejected" | "rejected_by_user" | "delivered" | "out_for_delivery" | "agent" | "agent_changed" | "in_hub",
    "reason": "string",
    "extras": {}
  }
}
```

### Query: order.get

Get a single order by ID.

**Request:**
```json
{
  "type": "query",
  "operation": "order.get",
  "params": {
    "id": "order_id_string"
  }
}
```

**Response:**
```json
{
  "data": <ORDER_SCHEMA>
}
```

### Mutation: order.create

Create a new order.

**Request:**
```json
{
  "type": "mutation",
  "operation": "order.create",
  "params": {
    "total_amount": 0.0,
    "total_discount": 0.0,
    "order_items": [
      {
        "product": {},  // full product object with all details
        "quantity": 0
      }
    ],
    "shipping_details": {
      "phone": "string",
      "email": "string",
      "clerk_token": "string",
      "address": "string"
    }
  }
}
```

**Note:** Clerk token validation should be done manually in the backend. The `clerk_token` is stored for admin verification.

**Response:**
```json
{
  "data": <ORDER_SCHEMA>
}
```

### Mutation: order.updateStatus

Update order status.

**Request:**
```json
{
  "type": "mutation",
  "operation": "order.updateStatus",
  "params": {
    "id": "order_id_string",
    "status": {
      "type": "accepted" | "rejected" | "delivered" | "out_for_delivery" | "agent" | "agent_changed" | "in_hub",
      "reason": "string",
      "extras": {
        "agent_phone": "string"
      }
    }
  }
}
```

**Response:**
```json
{
  "data": <ORDER_SCHEMA>
}
```

---

## Error Codes

- **400 Bad Request**: Invalid request parameters or validation error
- **500 Internal Server Error**: Server-side error

All errors return:
```json
{
  "error": "Error message"
}
```

