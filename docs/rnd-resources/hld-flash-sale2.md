HLD: Design Flash Sale
======================

In a flash sale, the biggest challenges are traffic spikes, low latency, and preventing overselling

* * *

By Shashank Mishra

6 min. read

View original

* * *

**Functional Requirements**

1.  System should allow admins to create, schedule, pause, and end flash sales with time-bound discounts and limited inventory.
    
2.  System should display real-time product availability, pricing, and countdown timers to users during the sale.
    
3.  System should handle high-concurrency purchase requests and ensure no overselling of inventory.
    
4.  System should reserve inventory for a short TTL once a user initiates checkout.
    
5.  System should process orders, payments, and confirmations atomically during the sale window.
    
6.  System should provide post-sale reporting for orders, inventory sold, failures, and revenue.
    

**Non-Functional Requirements**

1.  **Scalability:** System must handle sudden traffic spikes (10–100× normal load) during sale start.
    
2.  **Low Latency:** Product listing and inventory checks should respond within <100 ms.
    
3.  **High Availability:** System should remain available (99.99%) during flash sale windows.
    
4.  **Consistency:** Inventory and order creation must be strongly consistent to prevent overselling.
    
5.  **Fault Tolerance:** System should gracefully handle partial failures (payment, cache, node crashes).
    
6.  **Security:** Prevent bot abuse, fraud, and ensure secure payment and user data handling.
    

**API’s**

**1\. Create Flash Sale (Admin)**  
`POST /api/admin/flash-sale`

**Request**

    {
      "saleId": "FS1001",
      "startTime": "2026-01-20T10:00:00Z",
      "endTime": "2026-01-20T12:00:00Z",
      "discountPercent": 40,
      "products": [
        { "productId": "P101", "totalQty": 1000 },
        { "productId": "P102", "totalQty": 500 }
      ]
    }
    

**Response**

    {
      "status": "SUCCESS",
      "message": "Flash sale created successfully"
    }
    

**2\. Get Active Flash Sales**  
`GET /api/flash-sale/active`

**Response**

    {
      "sales": [
        {
          "saleId": "FS1001",
          "startTime": "2026-01-20T10:00:00Z",
          "endTime": "2026-01-20T12:00:00Z"
        }
      ]
    }
    

**3\. Get Flash Sale Products**  
`GET /api/flash-sale/{saleId}/products`

**Response**

    {
      "saleId": "FS1001",
      "products": [
        {
          "productId": "P101",
          "originalPrice": 1000,
          "salePrice": 600,
          "availableQty": 320,
          "saleEndsAt": "2026-01-20T12:00:00Z"
        }
      ]
    }
    

**4\. Reserve Inventory (Start Checkout)**  
`POST /api/flash-sale/{saleId}/reserve`

**Request**

    {
      "userId": "U9001",
      "productId": "P101",
      "quantity": 1
    }
    

**Response**

    {
      "reservationId": "R78901",
      "expiresAt": "2026-01-20T10:05:00Z",
      "status": "RESERVED"
    }
    

**5\. Confirm Order (After Payment)**  
`POST /api/flash-sale/{saleId}/confirm`

**Request**

    {
      "reservationId": "R78901",
      "paymentId": "PAY4567"
    }
    

**Response**

    {
      "orderId": "O56789",
      "status": "CONFIRMED"
    }
    

**6\. Release Inventory (Timeout / Cancel)**  
`POST /api/flash-sale/{saleId}/release`

**Request**

    {
      "reservationId": "R78901"
    }
    

**Response**

    {
      "status": "RELEASED"
    }
    

**Databases**

### 1\. **Relational DB (MySQL / PostgreSQL)**

_Used for orders, payments, users, sale configuration_

**flash\_sales**

    sale_id (PK)
    start_time
    end_time
    discount_percent
    status
    

**flash\_sale\_products**

    id (PK)
    sale_id (FK)
    product_id
    total_qty
    price
    

**orders**

    order_id (PK)
    user_id
    sale_id
    total_amount
    status
    created_at
    

### 2\. **In-Memory Store (Redis)**

_Used for ultra-fast inventory control & reservations_

**Keys**

    FS_INV_{saleId}_{productId} -> availableQty
    FS_RES_{reservationId} -> { userId, productId, qty, expiry }
    

### 3\. **NoSQL DB (Cassandra / DynamoDB)**

_Used for high-write order events & sale activity logs_

**flash\_sale\_events**

    sale_id (PK)
    event_time (CK)
    event_type
    user_id
    product_id
    quantity
    

### 4\. **Search / Cache DB (Elasticsearch / Redis Cache)**

_Used for fast product listing during flash sale_

**flash\_sale\_product\_index**

    sale_id
    product_id
    sale_price
    available_qty
    sale_end_time
    

### 5\. **Analytics / OLAP DB (BigQuery / Redshift / ClickHouse)**

_Used for post-sale analytics & reporting_

**flash\_sale\_metrics**

    sale_id
    product_id
    units_sold
    revenue
    failure_count
    

👉 **Why this mix?**

### **Microservices**

1.  **Flash Sale Service**
    
2.  **Product Catalog Service**
    
    *   Provides product details, base price, images, metadata
        
    *   Read-heavy, cached aggressively
        
3.  **Inventory Service**
    
4.  **Order Service**
    
5.  **Payment Service**
    
6.  **User Service**
    
7.  **Notification Service**
    
8.  **Analytics / Reporting Service**
    

### **Service Interaction Flow**

**1\. Sale Setup (Admin Flow)**

    Admin → Flash Sale Service → DB
    

**2\. User Browsing**

    User → API Gateway → Flash Sale Service
                             → Product Catalog Service
                             → Cache / Search
    

**3\. Inventory Reservation (High QPS Path)**

    User → API Gateway → Inventory Service (Redis Atomic Ops)
                             → Reservation Created (TTL)
    

**4\. Order & Payment Flow**

    User → Order Service → Payment Service
    Payment Service → Event Bus → Order Service
    Order Service → Inventory Service (Confirm)
    

**5\. Failure / Timeout Handling**

    Reservation TTL Expiry → Inventory Service → Stock Released
    Payment Failure → Order Service → Inventory Service (Release)
    

**6\. Async Events & Analytics**

    All Services → Event Bus (Kafka)
    Event Bus → Analytics Service / Notification Service
    

### **Key HLD Principles Used**

**Block Diagram**

                         ┌───────────────┐
                         │     Admin     │
                         └───────┬───────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │ Flash Sale       │
                        │ Service          │
                        └───────┬──────────┘
                                 │
                                 ▼
                           ┌─────────┐
                           │  RDBMS  │
                           │(Sale DB)│
                           └─────────┘
    
    
     ┌───────────┐
     │   User    │
     └─────┬─────┘
           │
           ▼
    ┌────────────────┐
    │  API Gateway   │  (Auth, Rate Limit, Throttling)
    └─────┬──────────┘
          │
          ├──────────────► Product Catalog Service
          │                         │
          │                         ▼
          │                    Product DB
          │
          ├──────────────► Flash Sale Service
          │                         │
          │                         ▼
          │                    Cache / Search
          │
          ├──────────────► Inventory Service
          │                         │
          │                         ▼
          │                      Redis
          │              (Atomic Stock + TTL)
          │
          └──────────────► Order Service
                                    │
                                    ▼
                            ┌─────────────┐
                            │ Payment     │
                            │ Service     │
                            └──────┬──────┘
                                   │
                                   ▼
                             Payment Gateway
    
    
            ┌───────────────────────────────────────┐
            │               Event Bus (Kafka)        │
            └──────────────┬───────────────┬────────┘
                           │               │
                           ▼               ▼
                  Notification Service   Analytics Service
                           │               │
                           ▼               ▼
                      Email / SMS       OLAP DB
    

### **Key Notes (1-Line Each)**

*   **API Gateway** absorbs traffic spikes & protects backend
    
*   **Inventory Service + Redis** ensures no overselling
    
*   **Order & Payment** decoupled via events
    
*   **Kafka** enables async, fault-tolerant processing
    
*   **Analytics & Notifications** don’t impact critical path
    

“In a flash sale, the biggest challenges are **traffic spikes, low latency, and preventing overselling**.

Users first hit the **API Gateway**, which handles authentication, rate-limiting, and bot protection.

For browsing, requests go to the **Flash Sale Service** and **Product Catalog Service**, which are heavily cached to serve reads quickly.

When a user starts checkout, the request goes to the **Inventory Service**, which uses **Redis atomic operations** to reserve stock with a short TTL. This guarantees strong consistency and prevents overselling even under very high concurrency.

After reservation, the **Order Service** creates an order and calls the **Payment Service**. Payment success or failure is published to **Kafka**.

Based on the event, inventory is either confirmed or released.

Non-critical operations like **notifications and analytics** consume events asynchronously, so they never impact the purchase flow.

This event-driven, cache-heavy design allows the system to scale horizontally and remain highly available during flash sales.”

1️⃣ Common Interviewer Questions & Crisp Answers
------------------------------------------------

**Q1. How do you prevent overselling?**  
→ Use **Redis atomic operations (DECR / Lua scripts)** to reserve inventory with a **TTL**. Inventory is confirmed only after payment success.

**Q2. Why not update inventory directly in DB?**  
→ DB locks don’t scale under flash traffic. Redis provides **single-threaded atomicity + low latency**.

**Q3. What if payment succeeds but inventory confirm fails?**  
→ Use **idempotent confirm APIs** and **event retries**. Inventory confirm is retried via Kafka until success.

**Q4. How do you handle bots?**  
→ API Gateway rate limiting, CAPTCHA at checkout, per-user quotas, and behavioral heuristics.

**Q5. How do you scale at sale start (traffic burst)?**  
→ Pre-warm cache, autoscale stateless services, Redis cluster, and queue-based async flows.

2️⃣ Failure Scenarios & Recovery (Very Important)
-------------------------------------------------

### 🔴 Redis Goes Down

### 🔴 Payment Success but Order Service Crashes

### 🔴 Reservation TTL Expiry

### 🔴 Duplicate Requests (User retries)

3️⃣ Back-of-the-Envelope Estimation (Quick)
-------------------------------------------

**Assume**

**Reads**

**Writes**

**Why it works**

4️⃣ Redis Inventory Lua Script (Interview Gold)
-----------------------------------------------

    if redis.call("GET", KEYS[1]) >= ARGV[1] then
      redis.call("DECRBY", KEYS[1], ARGV[1])
      return 1
    else
      return 0
    end
    

➡️ Ensures **check + decrement is atomic**

5️⃣ Final One-Liner (Use at End)
--------------------------------

> “Flash sale success depends on **atomic inventory control, aggressive caching, and async recovery paths**, not on strong DB locking.”

Redis vs Database Locking – Deep Comparison

    | Aspect          | Redis                      | Database Locking           |
    | --------------- | -------------------------- | -------------------------- |
    | Primary goal    | Speed + atomic ops         | Strong consistency         |
    | Execution model | Single-threaded, in-memory | Multi-threaded, disk-based |
    | Typical usage   | Hot counters, reservations | Final source of truth      |
    

### 2️⃣ Concurrency Handling

#### **Redis**

#### **DB Locking**

👉 **Winner: Redis**

3️⃣ Latency Profile

    | Operation        | Redis  | DB Lock        |
    | ---------------- | ------ | -------------- |
    | Inventory check  | ~1 ms  | 5–20 ms        |
    | Lock acquisition | N/A    | Unbounded wait |
    | Scale under load | Linear | Degrades badly |
    

### 4️⃣ Failure Scenarios (Very Important)

#### Redis Failure

#### DB Lock Failure

*   Long transactions
    
*   Lock leaks
    
*   Cascading failures
    
*   Entire system slows down
    

👉 Redis fails **fast**, DB fails **slowly and system-wide**

### 5️⃣ TTL & Reservation Handling

#### Redis

#### DB

*   Needs cron jobs
    
*   Complex cleanup logic
    
*   Slow recovery
    

👉 Redis is **designed** for reservations

### 6️⃣ Scaling Behavior (Key Interview Topic)

#### Redis

    Add more Redis shards → scale writes
    Stateless services → scale horizontally
    

#### DB

    Vertical scaling
    Read replicas don’t help writes
    Sharding + locking = nightmare
    

👉 DB locking does **not scale for flash sales**

### 7️⃣ Consistency Model (Tricky Question)

    | Layer           | Consistency           |
    | --------------- | --------------------- |
    | Redis inventory | Strong (atomic ops)   |
    | DB orders       | Strong (transactions) |
    | End-to-end      | Eventual but safe     |
    

✔️ **Business invariant** maintained: _No overselling_

### 8️⃣ Real-World Failure Story (Interview Gold)

> “We once used DB locking for inventory. During a flash sale, GC pauses caused lock holding threads to freeze, queues piled up, and the DB became the bottleneck. Redis eliminated this by avoiding locks entirely.”

(You already mentioned seeing similar GC + lock issues — this is a huge plus.)

Hybrid Model (Best Practice)
----------------------------

    Redis → Fast, atomic reservation
    Kafka → Event durability
    DB → Final consistency & audit
    

Redis is **not the source of truth**, it is the **traffic shock absorber**.

When DB Locking _Is_ Acceptable
-------------------------------

❌ **Never for flash sales**

Final Interview One-Liner
-------------------------

> “DB locking provides correctness but collapses under contention, whereas Redis provides atomicity without contention. That’s why Redis is used as the first line of defense, with DB as the final source of truth.”
