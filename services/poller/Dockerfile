FROM golang:1.25-alpine AS build

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -o /poller ./cmd/server

FROM alpine:3.20

COPY --from=build /poller /poller

USER nobody

EXPOSE 8080

CMD ["/poller"]
