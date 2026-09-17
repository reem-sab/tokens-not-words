# Tarpon Starter: webhook delivery

Tarpon Starter delivers events to your HTTPS endpoint.

Each delivery attempt waits up to 10 seconds for a response before Tarpon gives
up on that attempt.

Retries are turned off by default. When you enable them, Tarpon retries up to 3
times, counting attempts after the first, using exponential backoff that starts
at 2 seconds. Only 5xx responses and timeouts are retried. A 4xx response is
treated as final and is never retried.

Starter does not include a dead-letter queue. Once delivery attempts are
exhausted, the message is dropped.

Every webhook is signed with HMAC-SHA256. The signature is sent in the
X-Tarpon-Signature header.

The maximum webhook payload size is 256 KB.
