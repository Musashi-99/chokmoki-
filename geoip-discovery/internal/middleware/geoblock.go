package middleware

import (
	"net/http"
	"strings"

	"github.com/b33lz3bubTH/geoip-discovery/internal/geoip"
	"github.com/b33lz3bubTH/geoip-discovery/pkg/iputil"
)

// GeoBlock returns middleware that blocks requests from any country whose
// ISO 3166-1 alpha-2 code is in blockedCodes. Blocked requests get 403.
// Pass codes in any case — they are normalised to upper-case internally.
func GeoBlock(reader *geoip.Reader, blockedCodes ...string) func(http.Handler) http.Handler {
	blocked := make(map[string]struct{}, len(blockedCodes))
	for _, code := range blockedCodes {
		blocked[strings.ToUpper(strings.TrimSpace(code))] = struct{}{}
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ip := iputil.RealIP(
				r.Header.Get("X-Forwarded-For"),
				r.Header.Get("X-Real-IP"),
				r.RemoteAddr,
			)

			if ip != nil {
				if rec, err := reader.Lookup(ip); err == nil {
					code := strings.ToUpper(rec.Country.ISOCode)
					if _, deny := blocked[code]; deny {
						http.Error(w, "Access denied", http.StatusForbidden)
						return
					}
				}
			}

			next.ServeHTTP(w, r)
		})
	}
}
