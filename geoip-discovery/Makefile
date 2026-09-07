BINARY := geoip-server
DB     ?= dip.mmdb

.PHONY: build run run-block-india tidy test vet

build:
	go build -o $(BINARY) ./cmd/server

run: build
	./$(BINARY) -db $(DB)

run-block-india: build
	./$(BINARY) -db $(DB) -block IN

tidy:
	go mod tidy

vet:
	go vet ./...

test:
	go test ./...
