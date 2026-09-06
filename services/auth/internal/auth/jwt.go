package auth

import (
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

// JWTSigner implements TokenSigner using HS256 with a shared secret.
// Query API verifies the same token locally with the same secret
// (api-spec.md, §6: "no call-back to Auth") — the secret is the one
// shared Secret Manager entry both services read (decision_log.md, §8).
type JWTSigner struct {
	secret []byte
}

func NewJWTSigner(secret string) *JWTSigner {
	return &JWTSigner{secret: []byte(secret)}
}

func (s *JWTSigner) Sign(userID uuid.UUID, expiresAt time.Time) (string, error) {
	claims := jwt.RegisteredClaims{
		Subject:   userID.String(),
		ExpiresAt: jwt.NewNumericDate(expiresAt),
		IssuedAt:  jwt.NewNumericDate(time.Now()),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(s.secret)
}

func (s *JWTSigner) Parse(tokenString string) (*jwt.RegisteredClaims, error) {
	claims := &jwt.RegisteredClaims{}
	_, err := jwt.ParseWithClaims(tokenString, claims, func(t *jwt.Token) (interface{}, error) {
		return s.secret, nil
	}, jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Name}))
	if err != nil {
		return nil, err
	}
	return claims, nil
}
