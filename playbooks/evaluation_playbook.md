# Engineering Governance Evaluation Playbook

## Rule GOV-01: Risk Tiers and Applicability
**Applicability:** All systems and engineering changes.

Rules use four risk tiers. **Tier 0** covers regulated, financial, identity, security-critical, safety-critical, or irreversible operations. **Tier 1** covers customer-facing production systems and services processing real customer data. **Tier 2** covers internal production systems with controlled access and limited blast radius. **Tier 3** covers local tools, short-lived experiments, and prototypes with no production traffic or real customer data. When multiple tiers could apply, use the highest-risk tier. A prototype using production credentials, real customer data, or shared production infrastructure is not Tier 3. Rule-specific applicability overrides general recommendations, but it never creates an exception to legal, privacy, or security obligations.

## Rule SEC-01: Sensitive Data in Logs
**Applicability:** All tiers whenever real personal, confidential, authentication, or financial data is processed. Tier 3 systems must use synthetic data or follow the same restriction.

Applications must not write passwords, access tokens, session identifiers, government identifiers, payment details, health information, or other sensitive personal data to logs. Log fields containing email addresses, IP addresses, or customer identifiers must be masked or tokenized when they are not essential for operations. Redaction must happen before the event reaches the logging sink; deleting sensitive log entries afterward is not an acceptable control. Diagnostic logging may record that a credential was present, but never its value.

## Rule SEC-02: Secret Management
**Applicability:** All tiers that use non-public credentials or cryptographic material.

API keys, private keys, database passwords, signing secrets, and webhook secrets must be obtained from the approved secret manager at runtime. Secrets must not be committed to source control, embedded in container images, stored in plaintext configuration files, or passed through command-line arguments that may appear in process listings. Environment variables are permitted only when injected by the deployment platform from the secret manager. Suspected exposure requires immediate rotation; removing the secret from the latest Git commit is insufficient because history may retain it.

## Rule SEC-03: Untrusted Input Validation
**Applicability:** Required for Tier 0–2 boundaries receiving user, network, file, webhook, or message input. Required for Tier 3 when it is shared, externally accessible, or uses real data.

Every externally controlled value must be validated at the system boundary before it reaches business logic, a query builder, a template engine, or a shell. Prefer allowlists, typed schemas, length limits, and canonicalization over denylist-based filtering. Database operations must use parameterized queries; process execution must use argument arrays rather than concatenated shell commands. Escaping output does not replace input validation, and client-side validation must never be treated as a server-side security control.

## Rule SEC-04: Encryption and Transport Security
**Applicability:** Required for Tier 0–2 systems transmitting or storing confidential data. Required for Tier 3 whenever real credentials, customer data, or non-local network traffic is involved.

Confidential data must use authenticated encryption at rest and TLS 1.2 or newer in transit. Services must verify certificate chains and hostnames and must not disable TLS verification to work around local configuration problems. Encryption keys must be managed separately from encrypted data and rotated through the approved key-management service. Custom cryptographic algorithms, static initialization vectors, and hard-coded encryption keys are prohibited. Hashing alone is not encryption and must not be used when the original value must later be recovered.

## Rule SEC-05: Dependency and Supply-Chain Security
**Applicability:** Required for Tier 0–2 deployable artifacts. Recommended for Tier 3 and required when a prototype is distributed, shared, or built from third-party packages with installation scripts.

Production dependencies must be pinned through a lockfile or immutable digest and scanned for known vulnerabilities in continuous integration. A dependency with a critical exploitable vulnerability must block release unless a time-bounded, documented exception is approved. Package installation must use trusted registries, and build pipelines must verify provenance where supported. Teams must remove unused dependencies and must not execute unreviewed installation scripts from arbitrary repositories. Automated updates still require tests and review before merging.

## Rule AUTH-01: Authentication Token Validation
**Applicability:** Required for Tier 0–2 services accepting bearer tokens. Required for Tier 3 when reachable by anyone other than the developer running it locally.

Every service receiving a bearer token must validate its signature, issuer, audience, expiration time, and not-before time before trusting any claim. The accepted signing algorithm must be configured explicitly; a token-provided algorithm must not choose the verification method. Tokens intended for one service or environment must not be accepted by another. Failed validation returns an unauthenticated response without revealing whether a user, key, or token identifier exists. Authentication establishes identity but does not grant permission to a requested resource.

## Rule AUTH-02: Authorization and Resource Ownership
**Applicability:** Required for all Tier 0–2 protected resources and all multi-user or multi-tenant systems. Tier 3 is exempt only when it is strictly local, single-user, and contains no real data.

Authorization must be enforced on the server for every protected operation after authentication. A handler must verify the caller's role, tenant, and ownership of the specific resource being accessed; hiding a button or route in the user interface is not authorization. Database queries should include tenant or owner scope so unauthorized records are never loaded when practical. Administrative bypasses require explicit policy checks and audit events. Sequential identifiers and hard-to-guess URLs do not prevent insecure direct object reference attacks.

## Rule AUTH-03: Session Lifecycle and Cookies
**Applicability:** Required for Tier 0–2 browser applications using cookie sessions. Required for shared or remotely accessible Tier 3 demonstrations; optional for strictly local synthetic prototypes.

Browser sessions must use cookies marked `Secure`, `HttpOnly`, and an appropriate `SameSite` policy. Session identifiers must be regenerated after login or privilege changes and invalidated after logout, password reset, or account suspension. Idle and absolute expiration limits must be enforced on the server. State-changing browser requests require CSRF protection when cookie authentication is used. Session data must not be placed in browser-readable storage solely for convenience, and long-lived sessions require documented product and security approval.

## Rule AUTH-04: Password Storage and Login Protection
**Applicability:** Required in every tier that accepts or stores passwords. Tier 3 systems should use synthetic accounts or an external identity provider rather than weaken password controls.

Passwords must be stored using an approved adaptive password-hashing algorithm such as Argon2id with reviewed cost parameters and a unique salt. Passwords must never be encrypted for later recovery or hashed with general-purpose algorithms such as SHA-256 alone. Login endpoints must apply rate limits and progressive delay without permanently locking accounts through unauthenticated traffic. Password comparison must use the hashing library's verification function. Reset tokens must be single-use, short-lived, random, and invalidated after a successful reset.

## Rule API-01: API Versioning and Compatibility
**Applicability:** Required for Tier 0–1 public APIs and Tier 2 APIs with independently deployed consumers. Tier 3 and single-owner internal APIs may coordinate breaking changes when every consumer migrates atomically.

Public APIs must use an explicit versioning strategy and preserve documented behavior within a supported version. Removing fields, changing field meaning, narrowing accepted values, or changing error semantics is a breaking change even when the endpoint path stays the same. New response fields should be optional for clients, and consumers must receive a migration window before deprecation. Compatibility tests must cover representative existing clients. Internal APIs may use coordinated breaking changes only when all consumers are identified and migrated atomically.

## Rule API-02: Idempotent State-Changing Requests
**Applicability:** Required for Tier 0 operations and Tier 1 non-repeatable state changes. Required for Tier 2 when client retries could create harmful duplicates; recommended for Tier 3 simulations of those workflows.

POST operations that create financial records, submit orders, or trigger other non-repeatable state changes must support an idempotency key. The server must bind the key to the caller and a hash of the request, store the terminal response, and return that response when the same request is retried. Reusing a key with a different payload must fail. The idempotency record must be committed consistently with the state change so a timeout cannot create an untracked duplicate. This rule concerns request replay, not database query caching.

## Rule API-03: Rate Limiting and Abuse Control
**Applicability:** Required for Tier 0–1 externally reachable APIs and authentication endpoints. Required for Tier 2 shared services when abuse or expensive requests can affect other users; optional for local Tier 3 tools.

Externally reachable APIs must enforce rate limits using an identity appropriate to the threat, such as account, API key, tenant, or source network. Limits must define both a sustained rate and a burst allowance and must return a consistent throttling response with retry guidance. Authentication, password reset, and expensive search endpoints require stricter policies. Distributed services must share limit state or use a gateway capable of enforcing a global policy. Rate limiting protects capacity and abuse boundaries; it is not a substitute for authorization.

## Rule API-04: Error Response Contract
**Applicability:** Required for Tier 0–2 network APIs. Recommended for Tier 3 APIs that will become shared or production-facing.

API errors must use a stable structured schema containing a machine-readable code, a safe human-readable message, and a correlation identifier. Responses must not expose stack traces, SQL fragments, internal hostnames, secrets, or raw downstream exceptions. Status codes must distinguish invalid input, unauthenticated callers, forbidden operations, missing resources, conflicts, throttling, and server failures. Detailed diagnostic context belongs in protected logs linked by the correlation identifier. Retrying clients must be able to determine whether an error is transient.

## Rule API-05: Deadlines and Cancellation
**Applicability:** Required for Tier 0–2 services making remote calls or expensive operations. Recommended for Tier 3 shared services; optional for bounded local scripts without remote dependencies.

Every outbound network request must have an explicit timeout derived from the caller's remaining deadline. Services must propagate cancellation and stop unnecessary database, network, and compute work when the client request is abandoned. A timeout must cover connection establishment and response processing rather than relying only on a library's connect timeout. Long-running work should move to an asynchronous job when it cannot reliably finish within the request budget. Retrying without a deadline can multiply load and is prohibited.

## Rule DB-01: Transaction Boundaries
**Applicability:** Required in every tier when durable writes form one business operation. Tier 3 is exempt only for disposable synthetic state where partial completion has no consequence.

Operations that must succeed or fail as one business action must execute within a database transaction. The transaction must include all required relational writes, uniqueness checks, and state transitions, and must roll back on any failure. Transactions should be short and must not remain open during remote API calls or user interaction. Isolation level and locking must be chosen deliberately for concurrent updates. A database transaction cannot atomically cover an external message broker or HTTP service; use an outbox or another consistency pattern when crossing that boundary.

## Rule DB-02: Query Efficiency and Indexing
**Applicability:** Required for Tier 0–1 production paths. Required for Tier 2 when data volume, latency objectives, or database load is material; recommended for Tier 3 before promotion.

Queries on production paths must be reviewed with representative data and an execution plan before scale-sensitive release. Filters, joins, and ordering on large tables require appropriate indexes, but every new index must justify its write and storage cost. Avoid unbounded result sets, `SELECT *`, per-row queries, and functions on indexed columns that prevent index use. Pagination must have a deterministic order; high-offset pagination should use a cursor or keyset approach. Optimization claims require before-and-after latency or plan evidence.

## Rule DB-03: Connection Pool Management
**Applicability:** Required for Tier 0–2 services connecting to a shared database. Required for Tier 3 when it uses shared or production-like database infrastructure; optional for isolated local databases.

Applications must use a bounded database connection pool sized against the database's total connection budget and the number of service replicas. Acquisition must have a timeout, and connections must always be returned to the pool after success or failure. Pools must validate or recycle stale connections and expose utilization, wait time, and timeout metrics. Increasing pool size is not a default latency fix because excessive connections can reduce database throughput. Serverless concurrency must use a proxy or pooling strategy approved for burst behavior.

## Rule DB-04: Cache Correctness
**Applicability:** Required in every tier that introduces caching for user-specific or durable source data. Stampede protection is required for Tier 0–1 expensive shared keys and when Tier 2 load measurements justify it.

Caching is permitted only when the key, ownership scope, expiration policy, invalidation behavior, and source of truth are documented. Cache keys must include tenant and authorization context when responses differ between callers. Entries require a finite TTL unless immutability is guaranteed. Writes must invalidate or update affected entries, and cache failure must not silently return another user's data. Stampede protection is required for expensive popular keys. A cache improves repeated-read performance but must not become the authoritative store for durable business state.

## Rule DB-05: Safe Schema Migrations
**Applicability:** Required for Tier 0–2 shared durable databases. Required for Tier 3 when a schema is shared, contains real data, or must survive deployment; optional for disposable local schemas.

Production schema changes must be backward compatible with the currently deployed application during rolling releases. Destructive operations such as dropping or renaming a column require an expand-migrate-contract sequence: introduce the new shape, deploy compatible code, backfill in bounded batches, verify, and remove the old shape later. Large table rewrites and long locks must be assessed before deployment. Every migration must be observable, restartable where practical, and paired with a rollback or forward-fix plan. Applied migration files are immutable.

## Rule REL-01: Retries and Exponential Backoff
**Applicability:** Required for Tier 0–2 retrying remote calls or asynchronous work. Recommended for Tier 3 integrations; irrelevant when no retry is performed.

Retries are allowed only for failures that are transient and operations that are idempotent or protected by an idempotency mechanism. Retry policies must set a maximum attempt count, exponential backoff, random jitter, and an overall deadline. Validation failures, authorization failures, and deterministic business conflicts must not be retried. Services must honor downstream retry guidance such as `Retry-After`. Nested retries across multiple service layers must be avoided because they amplify traffic during an outage. Retry attempts and eventual recovery must be measured.

## Rule REL-02: Circuit Breakers and Dependency Isolation
**Applicability:** Required for Tier 0–1 dependencies when repeated failure can exhaust capacity or amplify an outage. Required for Tier 2 only when failure measurements justify it; optional for Tier 3.

Calls to unstable or capacity-limited dependencies must use circuit breaking when repeated failures would otherwise consume request threads or worsen the outage. The breaker must define failure thresholds, an open interval, limited half-open probes, and recovery behavior. Separate dependencies or traffic classes should not share one breaker when their failure domains differ. Fallbacks must be safe and must not return fabricated authoritative data. Circuit state, rejected calls, probe outcomes, and fallback usage must be observable.

## Rule REL-03: Health and Readiness Checks
**Applicability:** Required for Tier 0–2 long-running services managed by an orchestrator or load balancer. Tier 3 requires readiness only when deployed into shared infrastructure; local processes are exempt.

Services must expose separate liveness and readiness signals. Liveness reports whether the process can make progress and must not fail solely because an optional downstream dependency is unavailable. Readiness reports whether the instance can safely receive traffic and may include critical dependency or initialization state. Health endpoints must be fast, unauthenticated only within trusted infrastructure, and free of sensitive diagnostic data. A deep diagnostic check must not be used as a high-frequency orchestrator probe because it can overload dependencies.

## Rule REL-04: Graceful Shutdown
**Applicability:** Required for Tier 0–2 long-running services, workers, and message consumers. Required for Tier 3 when interruption could lose durable work; optional for disposable local processes.

On termination, a service must stop accepting new work, advertise that it is not ready, and allow in-flight work to finish within a bounded grace period. Consumers must stop fetching new messages before completing or safely releasing current messages. Network servers, database pools, telemetry exporters, and background tasks must close in a defined order. Work that cannot complete must remain recoverable after restart. Immediate process exit is allowed only after the grace deadline or for failures where continued execution would corrupt data.

## Rule REL-05: Asynchronous Job Delivery
**Applicability:** Required for Tier 0–2 queued jobs with durable effects. Required for Tier 3 when using a real at-least-once queue or non-disposable state; optional for purely synthetic jobs.

Background jobs must have a stable job identifier and an idempotent processing strategy because queues may deliver a message more than once. Workers must acknowledge a job only after its durable effects succeed. Transient failures should use bounded delayed retries; exhausted or non-retryable jobs must move to a dead-letter state with enough context for investigation and replay. Job payloads should carry identifiers rather than large mutable records. Queue visibility timeout must exceed normal processing time or be extended through a heartbeat.

## Rule OBS-01: Structured Application Logging
**Applicability:** Required for Tier 0–2 deployed services. Required for Tier 3 when deployed to a shared environment or used by multiple people; optional for short-lived local experiments.

Production services must emit structured logs with a timestamp, severity, service name, environment, event name, and correlation or trace identifier. Field names and event names must be stable enough for automated queries and alerts. Avoid multiline free-form messages when structured fields can represent the same information. Logging must follow the sensitive-data restrictions in `SEC-01`; observability does not justify recording credentials or private payloads. High-volume debug logging must be sampled or disabled in production and must not obscure actionable events.

## Rule OBS-02: Metrics and Cardinality
**Applicability:** Required for Tier 0–1 services. Tier 2 must expose core health and workload metrics; detailed domain metrics depend on operational risk. Optional for local Tier 3 experiments.

Services must publish metrics for request volume, error rate, latency, and resource saturation, plus domain-specific success indicators. Histograms must use reviewed buckets appropriate to service objectives. Metric labels must come from bounded sets; user IDs, request IDs, raw URLs, exception messages, and other unbounded values are prohibited because they create cardinality explosions. Dashboards should separate client errors from service failures. Alerts must identify an actionable symptom and should be tied to user impact or an explicit service-level objective.

## Rule OBS-03: Distributed Trace Propagation
**Applicability:** Required for Tier 0–1 distributed request paths. Required for Tier 2 when requests cross multiple independently operated services; optional for Tier 3 and single-process systems.

Services participating in a request must propagate the approved trace context across HTTP, messaging, and asynchronous boundaries. Spans must identify the operation, service, outcome, and relevant low-cardinality attributes. Errors should be recorded without attaching secrets or entire request bodies. Sampling must preserve enough error and high-latency traces for investigation while respecting cost limits. Creating a new trace at every internal hop breaks causal analysis and is prohibited unless the incoming context is invalid or intentionally crosses a trust boundary.

## Rule OBS-04: Security Audit Events
**Applicability:** Required in every tier performing security-sensitive actions against real identities, permissions, secrets, or customer data. Synthetic Tier 3 demonstrations are exempt from durable retention but should preserve the event contract.

Security-sensitive actions must create append-only audit events, including login changes, permission changes, administrative access, secret rotation, data export, and destructive operations. Each event must identify the actor, action, target, timestamp, outcome, source, and correlation identifier. Audit records must be protected from modification by ordinary application roles and retained according to the compliance schedule. They must not contain passwords, complete tokens, or unnecessary sensitive payloads. Audit events serve accountability and investigation; they are distinct from general diagnostic logs.

## Rule DEP-01: Progressive Delivery and Rollback
**Applicability:** Required for Tier 0–1 high-risk production changes. Required for Tier 2 when blast radius or rollback complexity is material; optional for Tier 3 and low-risk isolated internal changes.

High-risk production changes must use progressive delivery such as a canary, staged rollout, or feature flag with explicit success and rollback criteria. Deployment automation must monitor health signals during each stage and stop promotion when thresholds are violated. Rollback procedures must account for schema compatibility and irreversible external effects; redeploying an older binary is not always safe. Feature flags require an owner and removal date. A successful build and unit-test run alone are insufficient evidence for immediate full-traffic deployment.

## Rule DATA-01: Data Retention and Deletion
**Applicability:** Required in every tier storing real customer, employee, regulated, or operational data. Tier 3 is exempt only when it uses synthetic disposable data and no legally relevant audit evidence.

Stored customer and operational data must have a documented purpose, owner, retention period, and deletion mechanism. Services must not retain raw data indefinitely merely because storage is inexpensive. Deletion workflows must cover primary records, derived stores, search indexes, caches, and scheduled backups according to policy, while preserving legally required audit evidence. Soft deletion is not completion when policy requires erasure. Retention jobs must be idempotent, observable, and tested against data relationships so they do not leave inaccessible orphaned records.
