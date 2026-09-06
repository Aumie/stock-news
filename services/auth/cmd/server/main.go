package main

import (
	"context"
	"log"
	"net"
	"os"

	"github.com/jackc/pgx/v5/pgxpool"
	"google.golang.org/grpc"

	authpkg "stock-news/auth/internal/auth"
	authv1 "stock-news/auth/proto/auth/v1"
)

func main() {
	ctx := context.Background()

	// Shared literal with query-api's DEFAULT_JWT_SIGNING_SECRET — if this is
	// still in effect at startup, HS256 is symmetric and total auth bypass is
	// possible for anyone who has read this public source (decision_log_claude.md).
	const defaultJWTSigningSecret = "dev-secret-change-me"

	databaseURL := envOrDefault("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/stock-news")
	jwtSecret := envOrDefault("JWT_SIGNING_SECRET", defaultJWTSigningSecret)
	port := envOrDefault("PORT", "50051")

	if jwtSecret == defaultJWTSigningSecret {
		log.Println("WARNING: JWT_SIGNING_SECRET is unset — using the well-known dev default. " +
			"This allows anyone who has read this source to forge a valid JWT for any user.")
	}

	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		log.Fatalf("failed to connect to postgres: %v", err)
	}
	defer pool.Close()

	repo := authpkg.NewPostgresRepository(pool)
	signer := authpkg.NewJWTSigner(jwtSecret)
	svc := authpkg.NewService(repo, signer)
	handler := authpkg.NewGRPCHandler(svc)

	lis, err := net.Listen("tcp", ":"+port)
	if err != nil {
		log.Fatalf("failed to listen on port %s: %v", port, err)
	}

	grpcServer := grpc.NewServer()
	authv1.RegisterAuthServiceServer(grpcServer, handler)

	log.Printf("auth service listening on :%s", port)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
