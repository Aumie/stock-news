package auth

import (
	"context"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	authv1 "stock-news/auth/proto/auth/v1"
)

func TestGRPCHandler_ExchangeIdentity_ReturnsInvalidArgumentForEmptyGoogleSub(t *testing.T) {
	repo := newFakeRepo()
	signer := &fakeSigner{}
	svc := NewService(repo, signer)
	handler := NewGRPCHandler(svc)

	_, err := handler.ExchangeIdentity(context.Background(), &authv1.ExchangeIdentityRequest{
		GoogleSub: "",
		Email:     "a@example.com",
	})

	if err == nil {
		t.Fatal("expected an error, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected a gRPC status error, got %T", err)
	}
	if st.Code() != codes.InvalidArgument {
		t.Fatalf("expected codes.InvalidArgument, got %v", st.Code())
	}
}

func TestGRPCHandler_ExchangeIdentity_ReturnsJWTOnSuccess(t *testing.T) {
	repo := newFakeRepo()
	signer := &fakeSigner{}
	svc := NewService(repo, signer)
	handler := NewGRPCHandler(svc)

	resp, err := handler.ExchangeIdentity(context.Background(), &authv1.ExchangeIdentityRequest{
		GoogleSub: "google-sub-1",
		Email:     "a@example.com",
	})

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.GetJwt() == "" {
		t.Fatal("expected a non-empty JWT")
	}
}
