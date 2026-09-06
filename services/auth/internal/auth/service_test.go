package auth

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
)

type fakeRepo struct {
	byGoogleSub map[string]User
	inserted    []User
}

func newFakeRepo() *fakeRepo {
	return &fakeRepo{byGoogleSub: map[string]User{}}
}

func (r *fakeRepo) FindByGoogleSub(ctx context.Context, googleSub string) (*User, error) {
	if u, ok := r.byGoogleSub[googleSub]; ok {
		return &u, nil
	}
	return nil, nil
}

func (r *fakeRepo) Create(ctx context.Context, googleSub, email string) (*User, error) {
	u := User{ID: uuid.New(), GoogleSub: googleSub, Email: email, CreatedAt: time.Now()}
	r.byGoogleSub[googleSub] = u
	r.inserted = append(r.inserted, u)
	return &u, nil
}

type fakeSigner struct {
	signed []uuid.UUID
}

func (s *fakeSigner) Sign(userID uuid.UUID, expiresAt time.Time) (string, error) {
	s.signed = append(s.signed, userID)
	return "fake-jwt-" + userID.String(), nil
}

func TestExchangeIdentity_CreatesUserOnFirstLogin(t *testing.T) {
	repo := newFakeRepo()
	signer := &fakeSigner{}
	svc := NewService(repo, signer)

	resp, err := svc.ExchangeIdentity(context.Background(), "google-sub-1", "a@example.com")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(repo.inserted) != 1 {
		t.Fatalf("expected 1 user created, got %d", len(repo.inserted))
	}
	if resp.JWT == "" {
		t.Fatal("expected a non-empty JWT")
	}
}

func TestExchangeIdentity_LooksUpExistingUserOnSubsequentLogin(t *testing.T) {
	repo := newFakeRepo()
	signer := &fakeSigner{}
	svc := NewService(repo, signer)

	first, err := svc.ExchangeIdentity(context.Background(), "google-sub-1", "a@example.com")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	second, err := svc.ExchangeIdentity(context.Background(), "google-sub-1", "a@example.com")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(repo.inserted) != 1 {
		t.Fatalf("expected exactly 1 user ever created, got %d", len(repo.inserted))
	}
	_ = first
	_ = second
}

func TestExchangeIdentity_RejectsEmptyGoogleSub(t *testing.T) {
	repo := newFakeRepo()
	signer := &fakeSigner{}
	svc := NewService(repo, signer)

	_, err := svc.ExchangeIdentity(context.Background(), "", "a@example.com")
	if err != ErrInvalidGoogleSub {
		t.Fatalf("expected ErrInvalidGoogleSub, got %v", err)
	}
}

func TestExchangeIdentity_JWTExpiresIn24Hours(t *testing.T) {
	repo := newFakeRepo()
	signer := &fakeSigner{}
	svc := NewService(repo, signer)

	before := time.Now()
	resp, err := svc.ExchangeIdentity(context.Background(), "google-sub-1", "a@example.com")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	after := time.Now()

	expiresAt := time.Unix(resp.ExpiresAtUnix, 0)
	const tolerance = 2 * time.Second // Unix-second truncation, not a real timing bug
	if expiresAt.Before(before.Add(JWTExpiry-tolerance)) || expiresAt.After(after.Add(JWTExpiry+tolerance)) {
		t.Fatalf("expected expiry ~24h from now, got %v (now range %v..%v)", expiresAt, before, after)
	}
}
