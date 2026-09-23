package auth

import (
	"context"
	"errors"
	"log/slog"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	authv1 "stock-news/auth/proto/auth/v1"
)

// GRPCHandler is the only place proto types appear (project-structure.md) —
// translates proto <-> Service calls.
type GRPCHandler struct {
	authv1.UnimplementedAuthServiceServer
	svc    *Service
	logger *slog.Logger
}

func NewGRPCHandler(svc *Service, logger *slog.Logger) *GRPCHandler {
	return &GRPCHandler{svc: svc, logger: logger}
}

func (h *GRPCHandler) ExchangeIdentity(ctx context.Context, req *authv1.ExchangeIdentityRequest) (*authv1.ExchangeIdentityResponse, error) {
	resp, err := h.svc.ExchangeIdentity(ctx, req.GetGoogleSub(), req.GetEmail())
	if err != nil {
		if errors.Is(err, ErrInvalidGoogleSub) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}
		// Only the genuinely unexpected path is worth a log line — an
		// InvalidArgument is routine client-input rejection, already
		// surfaced to the caller via the gRPC status code itself.
		h.logger.Error("exchange identity failed", "error", err)
		return nil, status.Error(codes.Internal, "failed to exchange identity")
	}

	return &authv1.ExchangeIdentityResponse{
		Jwt:           resp.JWT,
		ExpiresAtUnix: resp.ExpiresAtUnix,
	}, nil
}
