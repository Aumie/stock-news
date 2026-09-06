FROM golang:1.25-alpine AS build

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -o /auth ./cmd/server

FROM alpine:3.20

COPY --from=build /auth /auth

USER nobody

EXPOSE 50051

CMD ["/auth"]
