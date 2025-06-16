# Multi-stage build for Notion Document Store MCP Server
# Using Alpine Linux for minimal attack surface and better security

FROM python:3.13-alpine AS builder

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    cargo \
    rust

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first (for better caching)
COPY pyproject.toml uv.lock* README.md ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application source
COPY src/ ./src/

FROM python:3.13-alpine AS release

# Install runtime dependencies only
RUN apk add --no-cache \
    curl \
    ca-certificates \
    && rm -rf /var/cache/apk/*

# Create non-root user
RUN addgroup -g 1000 mcpuser && \
    adduser -D -u 1000 -G mcpuser -s /bin/sh mcpuser

# Set working directory
WORKDIR /app

# Copy built application and dependencies from builder
COPY --from=builder --chown=mcpuser:mcpuser /app/.venv /app/.venv
COPY --from=builder --chown=mcpuser:mcpuser /app/src /app/src
COPY --from=builder --chown=mcpuser:mcpuser /app/pyproject.toml /app/pyproject.toml

# Create logs directory with proper permissions
RUN mkdir -p /app/logs && chown mcpuser:mcpuser /app/logs

# Switch to non-root user
USER mcpuser

# Environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV NOTION_API_VERSION=2022-06-28
ENV PATH="/app/.venv/bin:$PATH"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose ports: 3000 for MCP SSE, 8080 for health checks
EXPOSE 3000 8080

# Default command with SSE transport for Docker deployment
CMD ["python", "-m", "notion_document_store.server", "--verbose", "--transport", "sse", "--host", "0.0.0.0", "--port", "3000"]