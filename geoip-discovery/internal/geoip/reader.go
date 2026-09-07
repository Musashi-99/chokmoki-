package geoip

import (
	"fmt"
	"net"

	"github.com/oschwald/maxminddb-golang"
	"github.com/b33lz3bubTH/geoip-discovery/internal/cache"
)

// Reader wraps a MaxMind DB with a byte-bounded in-memory LRU cache.
// One Reader should be opened at startup and reused across all requests.
type Reader struct {
	db    *maxminddb.Reader
	cache *cache.LRU[string, *Record]
}

// Open opens the .mmdb file at path and initialises a cache capped at cacheBytes.
func Open(path string, cacheBytes int64) (*Reader, error) {
	db, err := maxminddb.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open mmdb %q: %w", path, err)
	}

	c, err := cache.New[string, *Record](cacheBytes, func(ip string, r *Record) int64 {
		const keyOverhead = 64 // string header + LRU map entry overhead
		return int64(keyOverhead+len(ip)) + r.estimateSize()
	})
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("init cache: %w", err)
	}

	return &Reader{db: db, cache: c}, nil
}

// Close releases the underlying file handle.
func (r *Reader) Close() error {
	return r.db.Close()
}

// Lookup returns GeoIP data for ip. Results are served from cache when available.
func (r *Reader) Lookup(ip net.IP) (*Record, error) {
	key := ip.String()

	if rec, ok := r.cache.Get(key); ok {
		return rec, nil
	}

	var rec Record
	if err := r.db.Lookup(ip, &rec); err != nil {
		return nil, fmt.Errorf("db lookup %s: %w", key, err)
	}

	r.cache.Add(key, &rec)
	return &rec, nil
}

// CacheStats returns the current entry count and estimated byte usage.
func (r *Reader) CacheStats() (entries int, bytes int64) {
	return r.cache.Len(), r.cache.BytesUsed()
}
