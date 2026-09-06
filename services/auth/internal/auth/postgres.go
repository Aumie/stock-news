package auth

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type PostgresRepository struct {
	pool *pgxpool.Pool
}

func NewPostgresRepository(pool *pgxpool.Pool) *PostgresRepository {
	return &PostgresRepository{pool: pool}
}

func (r *PostgresRepository) FindByGoogleSub(ctx context.Context, googleSub string) (*User, error) {
	var u User
	err := r.pool.QueryRow(
		ctx,
		`SELECT id, google_sub, email, created_at FROM users WHERE google_sub = $1`,
		googleSub,
	).Scan(&u.ID, &u.GoogleSub, &u.Email, &u.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (r *PostgresRepository) Create(ctx context.Context, googleSub, email string) (*User, error) {
	var u User
	err := r.pool.QueryRow(
		ctx,
		`INSERT INTO users (google_sub, email) VALUES ($1, $2)
		 ON CONFLICT (google_sub) DO UPDATE SET google_sub = EXCLUDED.google_sub
		 RETURNING id, google_sub, email, created_at`,
		googleSub, email,
	).Scan(&u.ID, &u.GoogleSub, &u.Email, &u.CreatedAt)
	if err != nil {
		return nil, err
	}
	return &u, nil
}
