package auth

import (
	"context"
	"time"

	"github.com/google/uuid"
)

// Repository is defined here, next to the use case that consumes it, per
// this project's Go-idiomatic (not Clean Architecture) package structure
// (decision_log.md, "DDD + TDD everywhere...").
type Repository interface {
	FindByGoogleSub(ctx context.Context, googleSub string) (*User, error)
	Create(ctx context.Context, googleSub, email string) (*User, error)
}

type TokenSigner interface {
	Sign(userID uuid.UUID, expiresAt time.Time) (string, error)
}

type ExchangeIdentityResponse struct {
	JWT           string
	ExpiresAtUnix int64
}

type Service struct {
	repo   Repository
	signer TokenSigner
}

func NewService(repo Repository, signer TokenSigner) *Service {
	return &Service{repo: repo, signer: signer}
}

func (s *Service) ExchangeIdentity(ctx context.Context, googleSub, email string) (*ExchangeIdentityResponse, error) {
	if err := ValidateIdentity(googleSub, email); err != nil {
		return nil, err
	}

	user, err := s.repo.FindByGoogleSub(ctx, googleSub)
	if err != nil {
		return nil, err
	}
	if user == nil {
		user, err = s.repo.Create(ctx, googleSub, email)
		if err != nil {
			return nil, err
		}
	}

	expiresAt := time.Now().Add(JWTExpiry)
	token, err := s.signer.Sign(user.ID, expiresAt)
	if err != nil {
		return nil, err
	}

	return &ExchangeIdentityResponse{JWT: token, ExpiresAtUnix: expiresAt.Unix()}, nil
}
