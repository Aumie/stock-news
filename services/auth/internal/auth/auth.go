package auth

import (
	"errors"
	"time"

	"github.com/google/uuid"
)

// JWTExpiry is 24h, no refresh flow in v1 (decision_log.md, "Auth").
const JWTExpiry = 24 * time.Hour

var ErrInvalidGoogleSub = errors.New("google_sub must not be empty")

type User struct {
	ID        uuid.UUID
	GoogleSub string
	Email     string
	CreatedAt time.Time
}

// ValidateIdentity checks the inbound identity claim before any lookup/insert
// is attempted. api-spec.md: invalid/unverifiable google_sub -> INVALID_ARGUMENT.
func ValidateIdentity(googleSub, email string) error {
	if googleSub == "" {
		return ErrInvalidGoogleSub
	}
	if email == "" {
		return errors.New("email must not be empty")
	}
	return nil
}
