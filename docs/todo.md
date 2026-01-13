#todo
1. i want a rating system, so on order items page, for users, when an order is made and its status delivered, then the user can give rating, store them in a different collection.
2. checks are like - status delivered, and in order to give rating, it will be on order details page, below, user can choose stars and comment of 2000 words at max, and it wil be sumbitted, and for product description page, load all orders, paginated wise, latest first. do the backend, schema and frontnend, admin wont touch this, thus making it non biased.
3. do both the backend and frontend. for each successful delivers users will be eligible to submit the review. the request will look like
{
    email: "user@gmail.com",
    rating: 4.7,
    comment: "",
}
4. for product display page, show 5 lines, how many 5 stars how many 4 stars and how many 2 stars, and below that load the ratings.