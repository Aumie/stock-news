package auth

import (
	"context"
	"errors"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	authv1 "stock-news/auth/proto/auth/v1"
)

// GRPCHandler is the only place proto types appear (project-structure.md) —
// translates proto <-> Service calls.
type GRPCHandler struct {
	authv1.UnimplementedAuthServiceServer
	svc *Service
}

func NewGRPCHandler(svc *Service) *GRPCHandler {
	return &GRPCHandler{svc: svc}
}

func (h *GRPCHandler) ExchangeIdentity(ctx context.Context, req *authv1.ExchangeIdentityRequest) (*authv1.ExchangeIdentityResponse, error) {
	resp, err := h.svc.ExchangeIdentity(ctx, req.GetGoogleSub(), req.GetEmail())
	if err != nil {
		if errors.Is(err, ErrInvalidGoogleSub) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}
		return nil, status.Error(codes.Internal, "failed to exchange identity")
	}

	return &authv1.ExchangeIdentityResponse{
		Jwt:           resp.JWT,
		ExpiresAtUnix: resp.ExpiresAtUnix,
	}, nil
}
