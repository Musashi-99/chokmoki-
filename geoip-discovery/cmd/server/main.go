package main

import (
	"context"
	"flag"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/b33lz3bubTH/geoip-discovery/internal/geoip"
	"github.com/b33lz3bubTH/geoip-discovery/internal/handler"
	"github.com/b33lz3bubTH/geoip-discovery/internal/middleware"
)

func main() {
	addr      := flag.String("addr", ":8080", "listen address")
	mmdb      := flag.String("db", "dip.mmdb", "path to MaxMind .mmdb database")
	blockList := flag.String("block", "", "comma-separated ISO country codes to block (e.g. IN,CN)")
	cacheMB   := flag.Int64("cache-mb", 200, "in-memory LRU cache size in MiB")
	flag.Parse()

	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	reader, err := geoip.Open(*mmdb, *cacheMB*1024*1024)
	if err != nil {
		log.Error("failed to open database", "err", err)
		os.Exit(1)
	}
	defer reader.Close()

	log.Info("database loaded", "path", *mmdb, "cache_mb", *cacheMB)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /lookup", handler.Lookup(reader))
	mux.HandleFunc("GET /health", handler.Health(reader))

	var h http.Handler = mux

	if *blockList != "" {
		codes := strings.Split(*blockList, ",")
		h = middleware.GeoBlock(reader, codes...)(mux)
		log.Info("geo-blocking enabled", "countries", codes)
	}

	srv := &http.Server{
		Addr:         *addr,
		Handler:      h,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		log.Info("server starting", "addr", *addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Error("server error", "err", err)
			os.Exit(1)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Info("shutting down")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Error("shutdown error", "err", err)
	}
	log.Info("server stopped")
}
