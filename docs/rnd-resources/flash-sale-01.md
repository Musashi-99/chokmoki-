Designing a Scalable Backend for Flash Sales
============================================

Recently, my peer group had an interesting discussion about designing a scalable backend for a...

* * *

By Budi Widhiyanto

16 min. read

View original

* * *

Recently, my peer group had an interesting discussion about designing a scalable backend for a marketplace, specifically to handle those crazy flash sales.

Flash sales bring their own set of challenges—things like sudden traffic spikes, huge demand for certain products, and the need to manage inventory in real-time. The main challenge here is making sure the system can handle all of this chaos while keeping things fast, stable, and smooth for users.

In this post, I’ll share some of the insights and strategies we discussed to tackle these issues and keep everything running smoothly.

[](#key-architecture-considerations-for-flash-sales)Key Architecture Considerations for Flash Sales
---------------------------------------------------------------------------------------------------

### [](#1-architecture-design)1\. Architecture Design

**Microservices Architecture**: When it comes to flash sales, going with a microservices architecture can make a huge difference. This design approach breaks down the backend into smaller, independent services—like user management, inventory control, order processing, and payment handling. Each of these services can scale on its own depending on how much traffic it’s handling at any given moment.

This setup offers some big advantages:

*   Each service can be built, deployed, and scaled independently.
*   Teams can work on different services at the same time without stepping on each other’s toes.
*   You can use the right technology for each service, depending on what it needs.
*   If one service fails, it won’t bring down the whole system.
*   Each service can be monitored and optimized based on its own performance.

**Event-Driven Architecture**: Flash sales are fast-paced and full of surprises, which makes an event-driven architecture a perfect fit. By using reliable message queues like Apache Kafka or RabbitMQ, you can build a system that stays strong even when things get hectic. This approach has some great perks:

*   Services can talk to each other asynchronously, so they’re less tightly coupled.
*   During peak times, the message queue can help smooth things out by buffering events.
*   If something goes wrong, you can retry operations without losing any data.
*   Complex processes can be broken down into smaller, easier-to-manage steps.
*   You can add or change system components without messing up the whole workflow.
*   Real-time event processing means the system can respond quickly to changes as they happen.

**API Gateway**: Think of the API gateway as the traffic controller of your flash sale system—it’s the first stop for all client requests. A well-designed gateway does more than just direct traffic; it handles a lot of important tasks to keep things running smoothly:

*   It smartly routes requests to the right microservices.
*   It enforces security with authentication and authorization.
*   It applies rate limiting to avoid overloading the system.
*   It transforms and validates requests/responses to make sure they’re correct.
*   It handles API versioning and keeps the docs up to date.
*   It provides analytics and monitoring to track how things are going.
*   It manages caching to speed things up.
*   It includes circuit breakers to protect the system if something goes wrong.

### [](#2-scalable-database-design)2\. Scalable Database Design

**Horizontal Scaling**: When it comes to flash sales, your database needs to be ready for some serious action. Horizontal scaling with database sharding is a great way to handle all those massive, concurrent transactions. The idea is to spread data across multiple database instances so your system can scale smoothly as demand grows. Here’s why it works:

*   You get linear scalability by adding more database nodes as needed.
*   Query performance improves since processing is spread out.
*   Fault tolerance is better because data is distributed, so if one part fails, the rest keeps going.

**Caching**: Flash sales can put your database under a ton of pressure, so efficient caching is a game-changer. By using tools like Redis or Memcached for multi-level caching, you can reduce the load on your database and boost performance. The benefits are clear:

*   Less strain on your database during peak times.
*   Instant access to frequently requested data.
*   Ability to handle sudden surges in read requests.
*   A much better user experience because things load faster.

**Read-Write Separation**: Flash sales usually involve a lot more reading than writing, so separating these operations can really help. The master-slave architecture, where the master handles writes and the slaves handle reads, is perfect for this. Here’s why:

*   It optimizes performance for read-heavy workloads (which is pretty much all of flash sales).
*   The master database can handle writes without being bogged down by all the read traffic.
*   Redundancy improves system reliability, so everything keeps running smoothly.

**Database Partitioning**: For high-volume flash sales, partitioning your database is key. By splitting your tables into logical chunks—like regions or product categories—you make things a lot more manageable and efficient. Here’s what you get:

*   Faster queries because the system is focusing on smaller chunks of data.
*   Easier database maintenance and backups since everything’s divided up.
*   Better resource use across multiple database servers.

### [](#3-traffic-management)3\. Traffic Management

**Load Balancers**: Flash sales bring in a flood of users all at once, so having a solid load balancing strategy is a must. Modern load balancers do more than just split traffic evenly—they use smart routing to make sure everything runs smoothly. Here’s why they’re essential:

*   They reduce response times by directing users to the nearest available server (geographic-based routing).
*   They improve system reliability by detecting failures and automatically rerouting traffic.
*   They ensure a better user experience by keeping sessions consistent, so users don’t get randomly disconnected.

**Rate Limiting**: When thousands (or even millions) of users hit your system at the same time, you need a way to keep things under control. Rate limiting helps prevent overload and abuse while keeping access fair for everyone. The benefits?

*   It keeps the system stable by preventing bots or excessive requests from overwhelming your servers.
*   It allows for prioritized access, so VIP users or loyal customers can get better treatment.

**Queueing**: Let’s be honest—nobody likes waiting, but sometimes it’s unavoidable. A smart queuing system can help manage traffic surges while keeping things fair and transparent. Here’s why it works:

*   It improves user satisfaction by showing real-time queue positions and estimated wait times.
*   It keeps the system efficient by organizing and prioritizing requests instead of letting chaos take over.

### [](#4-inventory-and-order-management)4\. Inventory and Order Management

**Pre-Allocate Inventory**: One of the best ways to avoid chaos in a flash sale is to plan ahead and strategically allocate inventory before the event even starts. This ensures stock is available where it's needed most and can handle the demand surge. Here’s why it’s a smart move:

*   Faster delivery times by placing stock in key regions ahead of time.
*   A built-in buffer to handle unexpected demand spikes without overselling.
*   Happier customers because products are available where demand is highest.
*   Maximized revenue by optimizing stock distribution across different customer segments.

**Optimistic Locking**: When thousands of users are trying to buy the same item at once, data consistency becomes a huge challenge. Optimistic locking helps by making sure orders don’t conflict and stock levels stay accurate—without slowing down the system. Here’s how it helps:

*   Uses version-based concurrency control to track stock changes.
*   Prevents overselling by handling conflicts automatically.
*   Monitors system performance to detect and fix lock contentions before they become an issue.

**Dedicated Flash Sale Service**: Flash sales are intense, and handling them with a dedicated service can make a huge difference. Instead of overloading the entire system, this service is built specifically to manage the unique demands of flash sales. Here’s what it does:

*   Real-time inventory tracking to prevent overselling.
*   Manages high traffic loads by processing concurrent requests efficiently.
*   Keeps caches and databases in sync, so stock levels stay accurate.

### [](#5-resiliency-and-fault-tolerance)5\. Resiliency and Fault Tolerance

**Circuit Breakers**: When flash sales push your system to its limits, the last thing you want is one failure causing a domino effect that brings everything down. That’s where circuit breakers come in. They monitor service health and automatically shut down failing components before they cause bigger problems. Here’s why they’re a must-have:

*   They detect and isolate failing services before they take down the whole system.
*   Recovery happens gradually, based on set thresholds, so the system doesn’t overload.
*   Operations teams get real-time alerts to fix issues before users even notice.

**Retries and Timeouts**: Not every failure is a disaster—some issues are just temporary. A smart retry strategy helps the system bounce back from small hiccups without making things worse. The key is knowing when to retry and when to stop. Here’s how it works:

*   Exponential backoff with jitter prevents the system from retrying too aggressively and making the problem worse.
*   Timeout settings are fine-tuned based on the type of operation to avoid unnecessary waits.
*   Integrates with circuit breakers, so retries don’t flood a service that’s already struggling.

**Graceful Degradation**: Let’s be real—sometimes the system just can’t keep up. But instead of everything breaking at once, graceful degradation allows the most important functions to keep running while less critical features get temporarily disabled. This helps by:

*   Using feature toggles to switch off non-essential functionalities when load is high.
*   Scaling back features progressively instead of shutting down everything at once.
*   Keeping users informed, so they know what’s happening instead of getting frustrated.

### [](#6-performance-optimization)6\. Performance Optimization

**CDN for Static Assets**: During a flash sale, your servers are already working overtime—so the last thing you want is them getting bogged down serving static files like images, stylesheets, or scripts. That’s where a Content Delivery Network (CDN) comes in. It delivers content from locations closer to users, reducing load times and keeping your backend free to handle the real heavy lifting. Here’s why it’s essential:

*   Multi-region distribution ensures users get assets from the nearest server, cutting down latency.
*   Automatic optimization & compression make files smaller and load faster.
*   Real-time performance monitoring helps adjust delivery for the best possible experience.

**Edge Computing**: Think of edge computing as bringing your backend closer to the action. Instead of processing every request at a central data center, edge nodes handle some of the work right where the users are, reducing latency and preventing bottlenecks. This approach is super useful for flash sales because:

*   It routes requests dynamically based on user location for the fastest response.
*   It caches data locally, reducing unnecessary hits to the main servers.
*   If one edge node fails, automatic failover kicks in to keep things running smoothly.

**Read-Only Replicas**: Flash sales generate way more read requests (users checking stock, product details, etc.) than write requests (actual purchases). To handle this without slowing down the primary database, we use read-only replicas. These help by:

*   Distributing read traffic across multiple database replicas, preventing overload.
*   Automatically switching to a replica if the main database has issues.
*   Monitoring replication lag to ensure users see the latest data without major delays.

### [](#7-realtime-monitoring-and-scaling)7\. Real-Time Monitoring and Scaling

**Auto-Scaling**: Flash sales are unpredictable—one moment, everything’s quiet, and the next, you’re drowning in traffic. That’s why auto-scaling is a game-changer. It makes sure your system has the resources it needs during peak times and scales back down to save costs when traffic slows. Here’s what makes a solid auto-scaling setup:

*   Predictive scaling that looks at past trends to prepare for spikes.
*   Multi-metric scaling that considers CPU, memory, and request rates instead of just one factor.
*   Cost-optimized resource management to prevent over-provisioning and wasted resources.

**Monitoring Tools**: You can’t fix what you can’t see, and during a flash sale, every second counts. Real-time monitoring gives you a clear view of system health, so you can catch and fix issues before they impact users. A solid monitoring setup includes:

*   Live performance dashboards to track key metrics in real-time.
*   Automated anomaly detection to spot unusual patterns before they become big problems.
*   Proactive alerts so your team gets notified the moment something starts to go wrong.

**Synthetic Testing**: You don’t want to wait until the actual flash sale to find out your system can’t handle the heat. That’s where synthetic testing comes in—by simulating real-world scenarios before launch, you can find weak spots and fix them in advance. The best testing strategies include:

*   Load testing with realistic traffic patterns to see how the system handles stress.
*   Chaos engineering to intentionally break things and ensure the system can recover.
*   End-to-end user journey validation to make sure the buying process is smooth from start to finish.

### [](#8-payment-and-checkout-scalability)8\. Payment and Checkout Scalability

**Tokenize Checkout Process**: During a flash sale, hundreds (or even thousands) of users try to check out at the same time, which can put a serious strain on payment processing. A **tokenized checkout process** helps streamline payments while keeping things secure. Here’s why it’s a great approach:

*   Securely handles payment info, so sensitive data never touches your servers.
*   Pre-authorizes payments, ensuring users don’t lose items while completing checkout.
*   Integrates fraud detection to prevent bad actors from gaming the system.

**Third-Party Payment Gateways**: Payment failures during checkout are a nightmare for users and a disaster for revenue. Using multiple, reliable payment gateways ensures smooth transactions—even under heavy traffic. Key things to consider:

*   Redundancy with multiple gateways to prevent single points of failure.
*   Automatic failover, so if one gateway goes down, another takes over instantly.
*   Real-time transaction monitoring to quickly spot and fix payment issues.

**Queue Checkout Requests**: When too many users hit checkout at once, you need a system that prevents crashes while keeping things fair. A checkout queue helps manage the madness in an orderly way. Here’s what makes it work:

*   Priority-based request handling, so VIP customers or faster checkouts don’t clog the system.
*   Dynamic queue management to adjust processing based on traffic load.
*   Transaction isolation and recovery, ensuring payments go through smoothly—even if something fails mid-process.

* * *

[](#bridging-to-inventory-challenges-overselling-and-underselling)Bridging to Inventory Challenges: Overselling and Underselling
--------------------------------------------------------------------------------------------------------------------------------

One of the biggest headaches in flash sales? **Overselling and underselling.** When thousands of users are racing to grab limited stock, inventory management becomes a high-speed balancing act.

**Overselling** happens when more items get sold than what’s actually available—leading to canceled orders, unhappy customers, and major logistical mess-ups. Meanwhile, **underselling** is the opposite problem—when stock is reserved but never actually purchased, leaving you with unsold inventory and missed revenue.

Fixing these issues is key to keeping customers happy and maximizing sales. By using smart strategies to prevent both overselling and underselling, you can create an inventory system that’s fast, reliable, and efficient—exactly what’s needed to survive the chaos of a flash sale.

[](#addressing-overselling-and-underselling-critical-challenges-in-flash-sales)Addressing Overselling and Underselling: Critical Challenges in Flash Sales
----------------------------------------------------------------------------------------------------------------------------------------------------------

### [](#understanding-overselling-a-major-risk-to-customer-trust)Understanding Overselling: A Major Risk to Customer Trust

One of the biggest nightmares in flash sales? Overselling. This happens when the system mistakenly sells more items than are actually in stock. It’s a mess—not just for logistics, but also for customer trust. Here’s why it happens:

*   Race Conditions: Too many people trying to buy the same item at the same time, and the system can’t update inventory fast enough.
*   Cache Inconsistencies: Inventory data isn’t synced quickly between cache and database, leading to incorrect stock counts.
*   System Latency: High traffic slows down inventory updates, causing duplicate sales.
*   Database Lock Contention: Multiple transactions fighting over the same stock, leading to conflicting updates.

And the consequences? Not pretty:

*   Customers lose trust in your brand.
*   Frustrated buyers flood customer support with complaints.
*   Possible legal trouble if overselling happens at scale.
*   Lost future sales because people hesitate to buy from you again.

### [](#understanding-underselling-the-hidden-revenue-killer)Understanding Underselling: The Hidden Revenue Killer

On the flip side, **underselling** can be just as bad—but it’s harder to notice. This happens when inventory is locked up or reserved too cautiously, leading to missed sales. Here’s what causes it:

*   Over-aggressive Locking: Holding onto inventory for too long while users are still deciding.
*   Conservative Stock Allocation: Keeping too much buffer stock instead of making it available for purchase.
*   Inefficient Queue Management: Poor handling of customer queues leading to wasted sales opportunities.
*   System Timeouts: Inventory stays locked for too long due to slow checkout processes.

The result?

*   Missed revenue and lower flash sale success.
*   Extra costs from holding unnecessary inventory.
*   Frustrated customers who see an "out of stock" message even when stock is available.
*   Inefficient use of system resources.

### [](#preventing-overselling-and-underselling-a-strategic-approach)Preventing Overselling and Underselling: A Strategic Approach

The best way to fix this? A well-designed **Inventory Reservation System.** This system helps keep things balanced by:

*   Tracking inventory in real-time to prevent miscounts.
*   Temporarily reserving stock for users who are checking out.
*   Releasing inventory if a user abandons their cart or times out.
*   Keeping stock updates consistent across all systems (database, cache, frontend).
*   Optimizing reservation timing so stock doesn’t sit unused for too long.

It’s all about finding the right balance—preventing overselling without losing revenue to underselling. A strong reservation system helps:

*   Keep things fair for customers.
*   Maintain fast performance even during traffic spikes.
*   Maximize sales without breaking inventory limits.
*   Ensure accurate and real-time stock updates.

[](#inventory-reservation-system-the-solution)Inventory Reservation System: The Solution
----------------------------------------------------------------------------------------

### [](#what-is-an-inventory-reservation-system)What is an Inventory Reservation System?

An **Inventory Reservation System** is like a temporary hold button for stock. It makes sure that when a user adds an item to their cart, it’s reserved just for them—but only for a limited time. This prevents both **overselling** (selling more than you have) and **underselling** (holding stock too cautiously and missing out on sales).

### [](#how-does-it-work)How Does It Work?

Here’s the step-by-step breakdown of how it keeps everything running smoothly:

1.  Check Inventory: First, the system verifies if the item is actually available in stock.
2.  Reserve Inventory in Cache: The item is temporarily reserved using a fast in-memory store like Redis, with a time-to-live (TTL) to prevent stock from being locked up forever.
3.  Sync with Database: Every so often, the system updates the database to keep the stock count accurate.
4.  Update Stock: When a user completes the checkout, the system deducts the reserved stock from the database.
5.  Handle Expirations: If a user doesn’t finish the purchase in time, the reservation expires and the item goes back into available inventory.

### [](#best-practices)Best Practices

To make sure the system works efficiently, here are a few must-dos:

*   Use a dedicated cache for speed—don’t rely on your main database for quick stock checks.
*   Set a TTL (time-to-live) on reservations, so items don’t get locked up indefinitely.
*   Keep the cache and database in sync to avoid inconsistencies and stock mismatches.

[](#designing-the-inventory-reservation-system)Designing the Inventory Reservation System
-----------------------------------------------------------------------------------------

To make sure inventory is managed efficiently, here’s how the system flows:

### [](#reservation-flow)**Reservation Flow**

When a user tries to reserve an item, the process looks like this:  

    User -> API Gateway -> Reservation Service  
           -> Check Inventory (DB)  
           -> Reserve in Cache (Redis with TTL)  
           -> Sync Reservation to DB  
           -> Deduct Stock in DB  
    

This ensures that stock is temporarily held for the user while they check out, without immediately affecting the database.

### [](#expiry-handling-flow)**Expiry Handling Flow**

Not every user completes their purchase—some abandon their cart. To prevent stock from getting stuck, an expiry job runs periodically:  

    Timer/Job (runs periodically) -> Check Expired Reservations in DB  
                                    -> Return Stock to Inventory (DB)  
                                    -> Remove Expired Reservations from DB  
    

This way, any unused reservations are cleared, and stock is put back into circulation.

### [](#checkout-flow)**Checkout Flow**

When a user completes their purchase, here’s what happens:  

    User -> API Gateway -> Checkout Service  
           -> Verify Reservation in Cache (Redis)  
           -> Mark Reservation as Completed (DB)  
           -> Remove Reservation from Cache (Redis)  
    

This confirms the purchase, updates stock levels, and cleans up any temporary reservations.

By using this hybrid approach—a mix of real-time caching, periodic database updates, and automated cleanup—we can avoid overselling and underselling while keeping the system fast, reliable, and scalable under high traffic.

[](#sample-implementation)Sample Implementation
-----------------------------------------------

To demonstrate these concepts in practice, here's a Java implementation of the Inventory Reservation System that showcases the integration between a relational database and Redis cache:  

    import java.time.LocalDateTime;
    import java.time.Duration;
    import java.util.*;
    import java.util.concurrent.*;
    import redis.clients.jedis.Jedis;
    import javax.persistence.*;
    
    // -----------------------------
    // Database Setup
    // -----------------------------
    @Entity
    @Table(name = "inventory")
    class Inventory {
        @Id
        @GeneratedValue(strategy = GenerationType.IDENTITY)
        private Long id;
    
        @Column(unique = true, nullable = false)
        private String productId;
    
        @Column(nullable = false)
        private int stock;
    
        // Getters and Setters
        // ...
    }
    
    @Entity
    @Table(name = "reservation")
    class Reservation {
        @Id
        @GeneratedValue(strategy = GenerationType.IDENTITY)
        private Long id;
    
        @Column(nullable = false)
        private String productId;
    
        @Column(nullable = false)
        private String userId;
    
        @Column(nullable = false)
        private int quantity;
    
        @Column(nullable = false)
        private LocalDateTime reservedAt;
    
        @Column(nullable = false)
        private LocalDateTime expiresAt;
    
        @Column(nullable = false)
        private boolean completed = false;
    
        // Getters and Setters
        // ...
    }
    
    // -----------------------------
    // Redis Setup
    // -----------------------------
    class RedisClient {
        private static final Jedis jedis = new Jedis("localhost", 6379);
    
        public static Jedis getInstance() {
            return jedis;
        }
    }
    
    // -----------------------------
    // Constants
    // -----------------------------
    class Constants {
        public static final int RESERVATION_TTL = 300; // 5 minutes
    }
    
    // -----------------------------
    // Reservation Logic
    // -----------------------------
    class ReservationService {
    
        private final EntityManagerFactory emf;
    
        public ReservationService(EntityManagerFactory emf) {
            this.emf = emf;
        }
    
        public Map<String, Object> reserveItem(String productId, String userId, int quantity) {
            EntityManager em = emf.createEntityManager();
            EntityTransaction transaction = em.getTransaction();
    
            try {
                transaction.begin();
    
                // Step 1: Check inventory availability
                Inventory inventory = em.createQuery("SELECT i FROM Inventory i WHERE i.productId = :productId", Inventory.class)
                        .setParameter("productId", productId)
                        .getSingleResult();
    
                if (inventory == null || inventory.getStock() < quantity) {
                    return Map.of("success", false, "message", "Insufficient stock.");
                }
    
                // Step 2: Create reservation in Redis
                Jedis redis = RedisClient.getInstance();
                String reservationKey = "reservation:" + productId + ":" + userId;
                if (redis.exists(reservationKey)) {
                    return Map.of("success", false, "message", "Item already reserved by this user.");
                }
                redis.setex(reservationKey, Constants.RESERVATION_TTL, String.valueOf(quantity));
    
                // Step 3: Sync reservation to the database
                LocalDateTime expiresAt = LocalDateTime.now().plusSeconds(Constants.RESERVATION_TTL);
                Reservation reservation = new Reservation();
                reservation.setProductId(productId);
                reservation.setUserId(userId);
                reservation.setQuantity(quantity);
                reservation.setReservedAt(LocalDateTime.now());
                reservation.setExpiresAt(expiresAt);
    
                em.persist(reservation);
    
                // Step 4: Update inventory in database
                inventory.setStock(inventory.getStock() - quantity);
                em.merge(inventory);
    
                transaction.commit();
    
                return Map.of("success", true, "message", "Reservation successful.");
            } catch (Exception e) {
                if (transaction.isActive()) transaction.rollback();
                e.printStackTrace();
                return Map.of("success", false, "message", "Reservation failed.");
            } finally {
                em.close();
            }
        }
    
        public Map<String, Object> checkoutItem(String productId, String userId) {
            EntityManager em = emf.createEntityManager();
            EntityTransaction transaction = em.getTransaction();
    
            try {
                transaction.begin();
    
                // Step 1: Verify reservation in Redis
                Jedis redis = RedisClient.getInstance();
                String reservationKey = "reservation:" + productId + ":" + userId;
                if (!redis.exists(reservationKey)) {
                    return Map.of("success", false, "message", "No active reservation.");
                }
    
                // Step 2: Mark reservation as completed
                Reservation reservation = em.createQuery("SELECT r FROM Reservation r WHERE r.productId = :productId AND r.userId = :userId AND r.completed = false", Reservation.class)
                        .setParameter("productId", productId)
                        .setParameter("userId", userId)
                        .getSingleResult();
    
                if (reservation == null) {
                    return Map.of("success", false, "message", "Reservation not found in database.");
                }
    
                reservation.setCompleted(true);
                em.merge(reservation);
    
                // Step 3: Remove reservation from Redis
                redis.del(reservationKey);
    
                transaction.commit();
    
                return Map.of("success", true, "message", "Checkout successful.");
            } catch (Exception e) {
                if (transaction.isActive()) transaction.rollback();
                e.printStackTrace();
                return Map.of("success", false, "message", "Checkout failed.");
            } finally {
                em.close();
            }
        }
    
        public void expireReservations() {
            EntityManager em = emf.createEntityManager();
            EntityTransaction transaction = em.getTransaction();
    
            try {
                transaction.begin();
    
                LocalDateTime now = LocalDateTime.now();
                List<Reservation> expiredReservations = em.createQuery("SELECT r FROM Reservation r WHERE r.expiresAt < :now AND r.completed = false", Reservation.class)
                        .setParameter("now", now)
                        .getResultList();
    
                for (Reservation reservation : expiredReservations) {
                    Inventory inventory = em.createQuery("SELECT i FROM Inventory i WHERE i.productId = :productId", Inventory.class)
                            .setParameter("productId", reservation.getProductId())
                            .getSingleResult();
                    if (inventory != null) {
                        inventory.setStock(inventory.getStock() + reservation.getQuantity());
                        em.merge(inventory);
                    }
                    em.remove(reservation);
                }
    
                transaction.commit();
            } catch (Exception e) {
                if (transaction.isActive()) transaction.rollback();
                e.printStackTrace();
            } finally {
                em.close();
            }
    
            // Reschedule the expiry handler
            ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
            scheduler.schedule(this::expireReservations, 60, TimeUnit.SECONDS);
        }
    }
    
    // -----------------------------
    // Main Application
    // -----------------------------
    public class FlashSaleApp {
        public static void main(String[] args) {
            EntityManagerFactory emf = Persistence.createEntityManagerFactory("flash_sale");
            ReservationService service = new ReservationService(emf);
    
            // Initialize Inventory
            EntityManager em = emf.createEntityManager();
            em.getTransaction().begin();
            Inventory inventory = new Inventory();
            inventory.setProductId("P123");
            inventory.setStock(100);
            em.persist(inventory);
            em.getTransaction().commit();
            em.close();
    
            // Start Expiry Handler
            service.expireReservations();
    
            // Simulate Reservations and Checkouts
            System.out.println(service.reserveItem("P123", "U1", 2));
            System.out.println(service.reserveItem("P123", "U2", 3));
            System.out.println(service.checkoutItem("P123", "U1"));
        }
    }
    

This implementation brings to life the key concepts we’ve covered in this article, including:

*   **Seamless integration** between Redis (for fast caching) and a relational database (for persistence).
*   **Transaction management** to ensure data consistency, even under high traffic.
*   **Automatic expiration** of reservations to free up inventory in case of abandoned checkouts.
*   **Error handling and rollback mechanisms** to prevent stock mismatches and failed transactions.

* * *

With this scalable, resilient, and high-performance design, flash sales can run smoothly without the typical overselling or underselling chaos.

I’d love to hear your thoughts! Got any experiences or insights on handling flash sale backends? Drop them in the comments! 🚀
