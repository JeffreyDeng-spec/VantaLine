# Authentication session policy

VantaLine currently enforces one active session per account, including administrator accounts. A successful login revokes that account's previous session, so the most recent device remains authenticated and earlier devices must sign in again.

This is the production behavior covered by `scripts/smoke_auth_rbac.py`. Changing to concurrent sessions is a product and security policy change; it requires an explicit decision, a session-management design, and updated regression tests rather than a test-only expectation change.
