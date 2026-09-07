package geoip

// Record holds the GeoIP fields extracted from the MaxMind DB.
// Country-level data is reliable; city-level is best-effort on the lite DB.
type Record struct {
	Country struct {
		ISOCode string            `maxminddb:"iso_code" json:"iso_code"`
		Names   map[string]string `maxminddb:"names"    json:"names,omitempty"`
	} `maxminddb:"country" json:"country"`

	Continent struct {
		Code  string            `maxminddb:"code"  json:"code,omitempty"`
		Names map[string]string `maxminddb:"names" json:"names,omitempty"`
	} `maxminddb:"continent" json:"continent,omitempty"`

	City struct {
		Names map[string]string `maxminddb:"names" json:"names,omitempty"`
	} `maxminddb:"city" json:"city,omitempty"`

	Location struct {
		Latitude  float64 `maxminddb:"latitude"  json:"latitude,omitempty"`
		Longitude float64 `maxminddb:"longitude" json:"longitude,omitempty"`
		TimeZone  string  `maxminddb:"time_zone" json:"time_zone,omitempty"`
	} `maxminddb:"location" json:"location,omitempty"`

	Subdivisions []struct {
		ISOCode string            `maxminddb:"iso_code" json:"iso_code,omitempty"`
		Names   map[string]string `maxminddb:"names"    json:"names,omitempty"`
	} `maxminddb:"subdivisions" json:"subdivisions,omitempty"`
}

// estimateSize returns a conservative byte estimate for cache accounting.
func (r *Record) estimateSize() int64 {
	const base = 256 // struct headers, map metadata, pointer words
	n := int64(base)
	n += int64(len(r.Country.ISOCode))
	for k, v := range r.Country.Names {
		n += int64(len(k) + len(v) + 32)
	}
	n += int64(len(r.Continent.Code))
	for k, v := range r.Continent.Names {
		n += int64(len(k) + len(v) + 32)
	}
	for k, v := range r.City.Names {
		n += int64(len(k) + len(v) + 32)
	}
	n += int64(len(r.Location.TimeZone) + 16) // two float64s
	for _, sub := range r.Subdivisions {
		n += int64(len(sub.ISOCode) + 64)
		for k, v := range sub.Names {
			n += int64(len(k) + len(v) + 32)
		}
	}
	return n
}
