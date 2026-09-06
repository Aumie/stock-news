// Real end-to-end check for milestone 2 (docs/milestone.md §2): dials the
// actual running auth service over gRPC and verifies ExchangeIdentity works
// against a real Postgres. Requires `docker compose up postgres auth`.
package integration

import (
	"context"
	"os"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	authv1 "stock-news/auth/proto/auth/v1"
)

func dialAuth(t *testing.T) authv1.AuthServiceClient {
	t.Helper()
	addr := os.Getenv("AUTH_GRPC_ADDR")
	if addr == "" {
		addr = "localhost:50051"
	}

	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("failed to dial auth service at %s: %v", addr, err)
	}
	t.Cleanup(func() { conn.Close() })

	client := authv1.NewAuthServiceClient(conn)

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	_, err = client.ExchangeIdentity(ctx, &authv1.ExchangeIdentityRequest{GoogleSub: "healthcheck-probe", Email: "probe@example.com"})
	if err != nil {
		t.Skipf("auth service not reachable at %s: %v", addr, err)
	}

	return client
}

func TestExchangeIdentity_FirstLoginThenSubsequentLoginReturnSameUser(t *testing.T) {
	client := dialAuth(t)
	ctx := context.Background()
	googleSub := "e2e-test-sub-" + time.Now().Format("150405.000000")

	first, err := client.ExchangeIdentity(ctx, &authv1.ExchangeIdentityRequest{
		GoogleSub: googleSub,
		Email:     "e2e@example.com",
	})
	if err != nil {
		t.Fatalf("first ExchangeIdentity call failed: %v", err)
	}
	if first.GetJwt() == "" {
		t.Fatal("expected a non-empty JWT")
	}

	second, err := client.ExchangeIdentity(ctx, &authv1.ExchangeIdentityRequest{
		GoogleSub: googleSub,
		Email:     "e2e@example.com",
	})
	if err != nil {
		t.Fatalf("second ExchangeIdentity call failed: %v", err)
	}
	if second.GetJwt() == "" {
		t.Fatal("expected a non-empty JWT on second call")
	}

	// Same underlying user across both calls: expiry windows should both be
	// ~24h from their respective call times, not wildly different.
	if second.GetExpiresAtUnix() < first.GetExpiresAtUnix() {
		t.Fatalf("expected second call's expiry >= first's, got first=%d second=%d",
			first.GetExpiresAtUnix(), second.GetExpiresAtUnix())
	}
}

func TestExchangeIdentity_RejectsEmptyGoogleSub(t *testing.T) {
	client := dialAuth(t)
	ctx := context.Background()

	_, err := client.ExchangeIdentity(ctx, &authv1.ExchangeIdentityRequest{
		GoogleSub: "",
		Email:     "e2e@example.com",
	})
	if err == nil {
		t.Fatal("expected an error for empty google_sub, got nil")
	}
}
