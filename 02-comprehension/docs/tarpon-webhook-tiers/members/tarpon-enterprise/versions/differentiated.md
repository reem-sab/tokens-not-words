# Tarpon Enterprise: webhook delivery

Tarpon Enterprise delivers events to your HTTPS endpoint. Settings marked
"Enterprise default" below are specific to this tier; other tiers set them
differently.

- **Per-attempt timeout (Enterprise default):** 30 seconds.
- **Retries (Enterprise default):** on. Tarpon retries up to **10 times
  (Enterprise default)**, counting attempts after the first.
- **Backoff:** exponential, starting at 2 seconds.
- **Retry policy:** only 5xx responses and timeouts are retried. A 4xx response
  is final and is never retried.
- **Dead-letter queue (Enterprise default):** on. A message that fails every
  attempt is sent to the dead-letter queue.
- **Signature (Enterprise):** HMAC-SHA256, sent in the X-Tarpon-Signature-V2
  header.
- **Maximum payload (Enterprise default):** 10 MB.
