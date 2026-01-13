#todo
1. i think webhook secret is needed to verify, its given in config

logs
----------------
 bash run_server.sh 
Server running on http://localhost:8000
Press Ctrl+C to stop the server
INFO:     Started server process [10245]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
2026-01-13 11:02:50,938 - lowkey_ecom - INFO - Analytics event tracked: product_view - 6965d900b4472e95365dd3ad
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
2026-01-13 11:02:51,010 - lowkey_ecom - INFO - Analytics event tracked: add_to_cart - 6965d901b4472e95365dd3ae
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
2026-01-13 11:03:08,136 - lowkey_ecom - INFO - Razorpay order created: order_S3FUHjCnmaKb6u
2026-01-13 11:03:08,136 - lowkey_ecom - INFO - Order initiated: fa74385b-2387-49a9-b28b-7da0e60dc69a, Razorpay order: order_S3FUHjCnmaKb6u
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
2026-01-13 11:03:19,277 - lowkey_ecom - WARNING - Incomplete webhook data: {'entity': 'event', 'account_id': 'acc_IyLEas6tHb9wEu', 'event': 'payment.captured', 'contains': ['payment'], 'payload': {'payment': {'entity': {'id': 'pay_S3FURpadZoC8pv', 'entity': 'payment', 'amount': 29900, 'currency': 'INR', 'status': 'captured', 'order_id': 'order_S3FUHjCnmaKb6u', 'invoice_id': None, 'international': False, 'method': 'upi', 'amount_refunded': 0, 'refund_status': None, 'captured': True, 'description': 'Order #fa74385b-2387-49a9-b28b-7da0e60dc69a', 'card_id': None, 'bank': None, 'wallet': None, 'vpa': 'success@razorpay', 'email': 'souravsunju@gmail.com', 'contact': '+916291048482', 'notes': {'order_id': 'fa74385b-2387-49a9-b28b-7da0e60dc69a', 'user_email': 'souravsunju@gmail.com'}, 'fee': 706, 'tax': 108, 'error_code': None, 'error_description': None, 'error_source': None, 'error_step': None, 'error_reason': None, 'acquirer_data': {'rrn': '675794955281', 'upi_transaction_id': 'A801FCC3EDADAF182847EB95A1DAB74F'}, 'created_at': 1768282397, 'reward': None, 'upi': {'vpa': 'success@razorpay', 'flow': 'collect'}, 'base_amount': 29900}}}, 'created_at': 1768282398}
INFO:     52.66.75.174:0 - "POST /webhook/razorpay HTTP/1.1" 200 OK
2026-01-13 11:03:33,139 - lowkey_ecom - INFO - Payment verified and order created: fa74385b-2387-49a9-b28b-7da0e60dc69a
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
2026-01-13 11:03:34,022 - lowkey_ecom - INFO - Analytics event tracked: order_placed - 6965d92db4472e95365dd3b1
INFO:     103.59.72.52:0 - "POST / HTTP/1.1" 200 OK
^CINFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [10245]

