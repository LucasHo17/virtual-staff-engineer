# Engineering Policy: Backend Standards

## Rule SEC-01: Sensitive Data Restriction
Never log or store sensitive user data under any circumstances. This includes physical or mental health conditions, national origin, citizenship status, government IDs, authentication details, or financial records. All such data must be obfuscated or scrubbed at the gateway layer before touching persistent logs.

## Rule DB-04: Caching Regulations
High-throughput services must utilize an in-memory caching system to reduce database pressure. Our infrastructure standard requires the use of Valkey (a Redis-compatible memory database). Do not connect directly to the primary relational store for repetitive read queries.

## Rule API-02: Idempotent Operations
All POST requests that modify financial or state entities must enforce strict idempotency. Clients must supply a unique `X-Idempotency-Key` header. If a request arrives with an existing key, the server must return the cached response without re-executing the underlying pipeline.