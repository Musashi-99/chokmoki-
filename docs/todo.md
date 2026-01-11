# todo
1. i want python based serverless vercel functions
2. the function will be one thing, everything is post, and single endpoint like graphql, considering there isnt any media upload, just normal http requests.
3. it will follow CQRS pattern it will use CommandQuery and CommandMutation, with mongo layer.
4. code base should follow SOLID principals
5. use patterns like singleton for mongo, to not exhaust the connection pool, sidecar pattern for plugins supports for logging in console, later i will offload it to.
6. i want product listing, product searching, product ordering, category will be there for products, so that discounts can be given on a category and it will reflect on all products.
7. i dont want users model, i will use clerk, and login will be done by clerk, and in backend during order place i will do it manually clerk token validation, put a comment thats it for that, rest take shipping data, order items and order totals, and everything that can save the state for those products, this creates redundency but its good for admins to verify.
8. use service based patterns for database methods, use async await for everything
9. use config using pydantic classes.

# model 
product model

if no vairant isnt given, at product creation will create a default vairant with the name is created. so that product creation is easy
{
name,
brand,
categories: [objectId1, objectId2],
produtct_description: "",
mrp_price,
selling_price,
tags: [" ", "", ""]
medias: [{url, mimetype, size}],
features: ["", "", ""],
active: true
product_variants: [
{
vairant_name: "size",
variant_values: [{
label: "XL",
active: false
}, {
label: "L",
active: true
}]
}, {
vairant: "color",
...... bule green
}
]
}

category model
{
name,
medias: [{url, mimetype, size}, .....],
description: "",
discount: {
rate: 0,
type: "percentage" | "direct",
}
}

order model
{
total_amount:,
total_discount:,
order_items: [{product, quantity}],
shipping_details: {
phone, email, clerk_token, address
}
}

order status - accepted, rejected, rejected_by_user, delivered, out_for_delivery, agent, agent_changed, in_hub
{
type: "accepted",
reason: "",
extras: {
agent_phone: "", // this extras are dynamic
}
}

