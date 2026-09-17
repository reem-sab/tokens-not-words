# Tarpon Enterprise: webhook delivery

Tarpon Enterprise delivers events to your HTTPS endpoint.

Each delivery attempt waits up to 30 seconds for a response before Tarpon gives
up on that attempt.

Retries are on by default. Tarpon retries up to 10 times, counting attempts after
the first, using exponential backoff that starts at 2 seconds. Only 5xx responses
and timeouts are retried. A 4xx response is treated as final and is never retried.

Enterprise includes a dead-letter queue, and it is enabled by default. A message
that fails every attempt is sent to the dead-letter queue.

Every webhook is signed with HMAC-SHA256. The signature is sent in the
X-Tarpon-Signature-V2 header.

The maximum webhook payload size is 10 MB.
