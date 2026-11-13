"""Adaptadores de segurança de borda: Turnstile e Rate Limit."""

from app.infra.seguranca.rate_limiter_mem import InMemoryRateLimiter
from app.infra.seguranca.rate_limiter_redis import RedisRateLimiter
from app.infra.seguranca.turnstile_adapter import (
    CloudflareTurnstileAdapter,
    StubCaptchaAdapter,
)

__all__ = [
    "CloudflareTurnstileAdapter",
    "InMemoryRateLimiter",
    "RedisRateLimiter",
    "StubCaptchaAdapter",
]
