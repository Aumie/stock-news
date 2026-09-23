package main

import (
	"context"
	"net"
	"os"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
	"google.golang.org/grpc"

	authpkg "stock-news/auth/internal/auth"
	authv1 "stock-news/auth/proto/auth/v1"
)

func main() {
	ctx := context.Background()
	logger := authpkg.NewLogger(envOrDefault("LOG_ENV", "dev"))

	// Shared literal with query-api's DEFAULT_JWT_SIGNING_SECRET — if this is
	// still in effect at startup, HS256 is symmetric and total auth bypass is
	// possible for anyone who has read this public source (decision_log_claude.md).
	const defaultJWTSigningSecret = "dev-secret-change-me"

	// The shared database-url secret (used by every service in this project)
	// carries a "+psycopg" driver suffix for the Python/SQLAlchemy services —
	// pgx has no notion of driver suffixes and fails to parse the URL with
	// one present, so strip it here rather than changing the shared secret
	// value and breaking the Python services again. Same fix as poller's pgx
	// driver (services/poller/cmd/server/main.go).
	databaseURL := strings.Replace(
		envOrDefault("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/stock-news"),
		"postgresql+psycopg://", "postgresql://", 1,
	)
	jwtSecret := envOrDefault("JWT_SIGNING_SECRET", defaultJWTSigningSecret)
	port := envOrDefault("PORT", "50051")

	if jwtSecret == defaultJWTSigningSecret {
		logger.Warn("JWT_SIGNING_SECRET is unset — using the well-known dev default. " +
			"This allows anyone who has read this source to forge a valid JWT for any user.")
	}

	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		logger.Error("failed to connect to postgres", "error", err)
		os.Exit(1)
	}
	defer pool.Close()

	repo := authpkg.NewPostgresRepository(pool)
	signer := authpkg.NewJWTSigner(jwtSecret)
	svc := authpkg.NewService(repo, signer)
	handler := authpkg.NewGRPCHandler(svc, logger)

	lis, err := net.Listen("tcp", ":"+port)
	if err != nil {
		logger.Error("failed to listen", "port", port, "error", err)
		os.Exit(1)
	}

	grpcServer := grpc.NewServer()
	authv1.RegisterAuthServiceServer(grpcServer, handler)

	logger.Info("auth service listening", "port", port)
	if err := grpcServer.Serve(lis); err != nil {
		logger.Error("failed to serve", "error", err)
		os.Exit(1)
	}
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
