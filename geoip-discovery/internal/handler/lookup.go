package handler

import (
	"encoding/json"
	"net"
	"net/http"

	"github.com/b33lz3bubTH/geoip-discovery/internal/geoip"
	"github.com/b33lz3bubTH/geoip-discovery/pkg/iputil"
)

type lookupResponse struct {
	IP  string       `json:"ip"`
	Geo *geoip.Record `json:"geo"`
}

// Lookup handles GET /lookup?ip=<addr>.
// When the ip query param is absent, the caller's own IP is resolved.
func Lookup(reader *geoip.Reader) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var ip net.IP

		if raw := r.URL.Query().Get("ip"); raw != "" {
			ip = net.ParseIP(raw)
			if ip == nil {
				http.Error(w, "invalid ip parameter", http.StatusBadRequest)
				return
			}
		} else {
			ip = iputil.RealIP(
				r.Header.Get("X-Forwarded-For"),
				r.Header.Get("X-Real-IP"),
				r.RemoteAddr,
			)
			if ip == nil {
				http.Error(w, "cannot determine client IP", http.StatusBadRequest)
				return
			}
		}

		rec, err := reader.Lookup(ip)
		if err != nil {
			http.Error(w, "lookup failed", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(lookupResponse{IP: ip.String(), Geo: rec})
	}
}

// Health handles GET /health — reports server liveness and cache stats.
func Health(reader *geoip.Reader) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		entries, bytes := reader.CacheStats()
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"status":        "ok",
			"cache_entries": entries,
			"cache_bytes":   bytes,
		})
	}
}
