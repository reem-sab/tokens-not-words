# Tarpon Team: webhook delivery

Tarpon Team delivers events to your HTTPS endpoint.

Each delivery attempt waits up to 15 seconds for a response before Tarpon gives
up on that attempt.

Retries are on by default. Tarpon retries up to 5 times, counting attempts after
the first, using exponential backoff that starts at 2 seconds. Only 5xx responses
and timeouts are retried. A 4xx response is treated as final and is never retried.

Team includes a dead-letter queue, but it is disabled by default. Unless you
enable it, a message that fails every attempt is dropped.

Every webhook is signed with HMAC-SHA256. The signature is sent in the
X-Tarpon-Signature header.

The maximum webhook payload size is 1 MB.
