#todo
1. so telegram service will send all data when trigged about all orders, thats not okay.
2. store the total number of orders, total items, total price accumulated and last 3 ordered items with name and quantity, thats all, then only in one invokeaction it will work, else i dont know the size, and expire this after 24hrs, cause all data is stored in mongo so no issues if things miss.