docker compose up -d

# look up any IP
curl "localhost:8080/lookup?ip=8.8.8.8"

# look up your own IP
curl "localhost:8080/lookup"

# health + cache stats
curl "localhost:8080/health"
