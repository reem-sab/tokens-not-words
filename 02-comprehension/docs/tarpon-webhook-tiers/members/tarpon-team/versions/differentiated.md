# Tarpon Team: webhook delivery

Tarpon Team delivers events to your HTTPS endpoint. Settings marked "Team default"
below are specific to this tier; other tiers set them differently.

- **Per-attempt timeout (Team default):** 15 seconds.
- **Retries (Team default):** on. Tarpon retries up to **5 times (Team default)**,
  counting attempts after the first.
- **Backoff:** exponential, starting at 2 seconds.
- **Retry policy:** only 5xx responses and timeouts are retried. A 4xx response
  is final and is never retried.
- **Dead-letter queue (Team default):** available but off. Unless you enable it,
  a message that fails every attempt is dropped.
- **Signature:** HMAC-SHA256, sent in the X-Tarpon-Signature header.
- **Maximum payload (Team default):** 1 MB.
