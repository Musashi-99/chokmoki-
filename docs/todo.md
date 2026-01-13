# todo
1. track status for online payment, and reflect that on order details page, what is the payment method and is it successful or not.
2. secondly its not working properly, do check it
3. why invalid webhook signature its going in mongo successfully
4. the order data look likes this
{
    "data": {
        "_id": "6965d4887b22ec59f62049cb",
        "order_id": "8fbf65eb-9efb-4c94-8320-661ed5263761",
        "user_email": "souravsunju@gmail.com",
        "shipping_address": {
            "email": "souravsunju@gmail.com",
            "full_name": "Sourav Ahmed",
            "phone": "06291048482",
            "address_line1": "Kolkata Airport  Po",
            "address_line2": "",
            "city": "Kolkata",
            "state": "West Bengal",
            "postal_code": "700052",
            "country": "India",
            "is_default": true,
            "created_at": "2026-01-11T16:31:17.477000",
            "updated_at": "2026-01-11T16:31:17.477000"
        },
        "items": [
            {
                "product_id": "6964bcfaf5312c25e029338a",
                "product_name": "Itachi Blood Premium Glass Cover for Realme 11 5G",
                "variant": {
                    "Device Model": "Realme 11 5G"
                },
                "quantity": 1,
                "unit_price": 299.0,
                "total_price": 299.0
            }
        ],
        "special_message": "razorpay test",
        "subtotal": 299.0,
        "discount": 0.0,
        "shipping": 0.0,
        "total_amount": 299.0,
        "payment_method": "razorpay",
        "payment_status": "completed",
        "razorpay_order_id": "order_S3F7AAVNueIhHX",
        "razorpay_payment_id": "pay_S3F9WmbMuMuiEy",
        "status": {
            "type": "accepted",
            "reason": "",
            "extras": {}
        },
        "created_at": "2026-01-13T05:11:14.307000",
        "raw_order_log": {
            "shippingAddress": {
                "email": "souravsunju@gmail.com",
                "full_name": "Sourav Ahmed",
                "phone": "06291048482",
                "address_line1": "Kolkata Airport  Po",
                "address_line2": "",
                "city": "Kolkata",
                "state": "West Bengal",
                "postal_code": "700052",
                "country": "India",
                "is_default": true,
                "created_at": "2026-01-11T16:31:17.477000",
                "updated_at": "2026-01-11T16:31:17.477000"
            },
            "items": [
                {
                    "productId": "6964bcfaf5312c25e029338a",
                    "productName": "Itachi Blood Premium Glass Cover for Realme 11 5G",
                    "variant": {
                        "Device Model": "Realme 11 5G"
                    },
                    "quantity": 1,
                    "price": 299.0,
                    "total": 299.0
                }
            ],
            "specialMessage": "razorpay test",
            "pricing": {
                "subtotal": 299.0,
                "discount": 0.0,
                "shipping": 0.0,
                "total": 299.0
            },
            "userEmail": "souravsunju@gmail.com",
            "timestamp": "2026-01-13T05:11:14.080Z",
            "paymentMethod": "razorpay",
            "order_id": "8fbf65eb-9efb-4c94-8320-661ed5263761",
            "received_at": "2026-01-13T05:11:14.307830"
        }
    }
}
5. its working, but there are still errors why? and for online orders show them properly in order details page for both admin and user, data is given properly.



logs:
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
2026-01-13 10:38:45,737 - lowkey_ecom - INFO - Razorpay order created: order_S3F4XST1em4EjH
2026-01-13 10:38:45,737 - lowkey_ecom - INFO - Order initiated: aa8b6ae0-f06e-4822-bab0-96778b2c92b0, Razorpay order: order_S3F4XST1em4EjH
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
2026-01-13 10:40:55,363 - lowkey_ecom - INFO - Analytics event tracked: product_view - 6965d3de7b22ec59f62049ca
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
2026-01-13 10:41:14,798 - lowkey_ecom - INFO - Razorpay order created: order_S3F7AAVNueIhHX
2026-01-13 10:41:14,798 - lowkey_ecom - INFO - Order initiated: 8fbf65eb-9efb-4c94-8320-661ed5263761, Razorpay order: order_S3F7AAVNueIhHX
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
2026-01-13 10:43:30,659 - lowkey_ecom - WARNING - Invalid webhook signature
INFO:     52.66.76.63:0 - "POST /webhook/razorpay HTTP/1.1" 400 Bad Request
2026-01-13 10:43:44,369 - lowkey_ecom - INFO - Payment verified and order created: 8fbf65eb-9efb-4c94-8320-661ed5263761
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
2026-01-13 10:43:45,454 - lowkey_ecom - INFO - Analytics event tracked: order_placed - 6965d4887b22ec59f62049cd
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
2026-01-13 10:45:05,225 - lowkey_ecom - WARNING - Invalid webhook signature
INFO:     52.66.75.174:0 - "POST /webhook/razorpay HTTP/1.1" 400 Bad Request
2026-01-13 10:46:10,558 - lowkey_ecom - WARNING - Invalid webhook signature
INFO:     52.66.75.174:0 - "POST /webhook/razorpay HTTP/1.1" 400 Bad Request
^CINFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [8012]
