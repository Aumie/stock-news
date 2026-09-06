package auth

import (
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestJWTSigner_SignAndParseRoundTrip(t *testing.T) {
	signer := NewJWTSigner("test-secret")
	userID := uuid.New()
	expiresAt := time.Now().Add(JWTExpiry)

	token, err := signer.Sign(userID, expiresAt)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	claims, err := signer.Parse(token)
	if err != nil {
		t.Fatalf("unexpected error parsing token: %v", err)
	}
	if claims.Subject != userID.String() {
		t.Fatalf("expected subject %s, got %s", userID, claims.Subject)
	}
}

func TestJWTSigner_ParseRejectsExpiredToken(t *testing.T) {
	signer := NewJWTSigner("test-secret")
	userID := uuid.New()
	alreadyExpired := time.Now().Add(-1 * time.Hour)

	token, err := signer.Sign(userID, alreadyExpired)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	_, err = signer.Parse(token)
	if err == nil {
		t.Fatal("expected an error parsing an expired token, got nil")
	}
}

func TestJWTSigner_ParseRejectsWrongSecret(t *testing.T) {
	signer := NewJWTSigner("test-secret")
	other := NewJWTSigner("different-secret")
	userID := uuid.New()

	token, err := signer.Sign(userID, time.Now().Add(JWTExpiry))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	_, err = other.Parse(token)
	if err == nil {
		t.Fatal("expected an error parsing a token signed with a different secret, got nil")
	}
}

func TestJWTSigner_ParseRejectsMalformedToken(t *testing.T) {
	signer := NewJWTSigner("test-secret")

	_, err := signer.Parse("not-a-jwt")
	if err == nil {
		t.Fatal("expected an error parsing a malformed token, got nil")
	}
}
