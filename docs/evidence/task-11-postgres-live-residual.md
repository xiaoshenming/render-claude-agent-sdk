# Task 11 PostgreSQL Verification Boundary

Task 11 provides a psycopg v3 service-delivery adapter and fake-connection
contract tests for parameterized SQL, transaction grouping, tenant ownership,
idempotent intake, `FOR UPDATE SKIP LOCKED`, lease fencing, durable HOLD and
callback outboxes, and persistent callback replay claims.

No live PostgreSQL result is claimed in Task 11. Task 14 must run migration
`0003_service_delivery.sql` against the supported PostgreSQL version and verify:

- concurrent idempotent submissions and global `job_id` conflicts;
- `SKIP LOCKED` behavior with multiple worker processes;
- stale lease fencing across real transactions and connection loss;
- atomic dead-letter, HOLD, and callback outbox rollback under failure injection;
- callback replay uniqueness across processes;
- lock timeout, deadlock, restart, and network interruption recovery;
- query plans and quota behavior at production-scale row counts.

Until that live suite passes, the PostgreSQL adapter is contract-complete but
not production-certified.
