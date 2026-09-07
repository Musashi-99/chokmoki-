package iputil

import (
	"net"
	"strings"
)

// RealIP extracts the true client IP.
// X-Forwarded-For may be "client, proxy1, proxy2" — always take the leftmost entry.
// Falls back to X-Real-IP, then RemoteAddr.
func RealIP(xff, xri, remoteAddr string) net.IP {
	if xff != "" {
		first := strings.SplitN(xff, ",", 2)[0]
		if ip := net.ParseIP(strings.TrimSpace(first)); ip != nil {
			return ip
		}
	}
	if xri != "" {
		if ip := net.ParseIP(strings.TrimSpace(xri)); ip != nil {
			return ip
		}
	}
	host, _, err := net.SplitHostPort(remoteAddr)
	if err != nil {
		return net.ParseIP(remoteAddr)
	}
	return net.ParseIP(host)
}
