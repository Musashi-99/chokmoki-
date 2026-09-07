package cache

import (
	"sync"

	lru "github.com/hashicorp/golang-lru/v2"
)

// LRU is a thread-safe, byte-bounded least-recently-used cache.
// The sizer function estimates each entry's memory footprint; entries are
// evicted oldest-first whenever the total would exceed maxBytes.
type LRU[K comparable, V any] struct {
	mu       sync.Mutex
	inner    *lru.Cache[K, V]
	sizes    map[K]int64
	curBytes int64
	maxBytes int64
	sizer    func(K, V) int64
}

// New creates a new size-bounded LRU.
// maxBytes is the soft upper bound on total estimated entry size.
func New[K comparable, V any](maxBytes int64, sizer func(K, V) int64) (*LRU[K, V], error) {
	// Count cap is intentionally huge; byte-based eviction fires first.
	inner, err := lru.New[K, V](1 << 30)
	if err != nil {
		return nil, err
	}
	return &LRU[K, V]{
		inner:    inner,
		sizes:    make(map[K]int64),
		maxBytes: maxBytes,
		sizer:    sizer,
	}, nil
}

// Get returns the cached value for key and whether it was found.
func (c *LRU[K, V]) Get(key K) (V, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.inner.Get(key)
}

// Add inserts or updates key → value, evicting oldest entries as needed.
func (c *LRU[K, V]) Add(key K, val V) {
	c.mu.Lock()
	defer c.mu.Unlock()

	newSize := c.sizer(key, val)

	// If updating an existing key, remove its old size contribution first.
	if old, ok := c.sizes[key]; ok {
		c.curBytes -= old
	}

	// Evict oldest entries until the new entry fits.
	for c.curBytes+newSize > c.maxBytes {
		oldest, _, ok := c.inner.GetOldest()
		if !ok {
			break
		}
		c.curBytes -= c.sizes[oldest]
		delete(c.sizes, oldest)
		c.inner.Remove(oldest)
	}

	c.inner.Add(key, val)
	c.sizes[key] = newSize
	c.curBytes += newSize
}

// Len returns the number of entries in the cache.
func (c *LRU[K, V]) Len() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.inner.Len()
}

// BytesUsed returns the current estimated byte usage.
func (c *LRU[K, V]) BytesUsed() int64 {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.curBytes
}
