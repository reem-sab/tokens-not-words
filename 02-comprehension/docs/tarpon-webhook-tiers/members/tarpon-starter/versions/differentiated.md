# Tarpon Starter: webhook delivery

Tarpon Starter delivers events to your HTTPS endpoint. Settings marked "Starter
default" below are specific to this tier; other tiers set them differently.

- **Per-attempt timeout (Starter default):** 10 seconds.
- **Retries (Starter default):** off. When you enable them, Tarpon retries up to
  **3 times (Starter default)**, counting attempts after the first.
- **Backoff:** exponential, starting at 2 seconds.
- **Retry policy:** only 5xx responses and timeouts are retried. A 4xx response
  is final and is never retried.
- **Dead-letter queue (Starter):** not available on this tier. After the final
  attempt fails, the message is dropped.
- **Signature:** HMAC-SHA256, sent in the X-Tarpon-Signature header.
- **Maximum payload (Starter default):** 256 KB.
