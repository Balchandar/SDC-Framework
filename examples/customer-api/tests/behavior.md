# Testing

These behavioral test cases are derived from the specification and are executed
against the running generated service by the verification engine. The verifier
also auto-generates additional negative authorization tests.

| name                       | endpoint                | authenticated | role         | tenant | expect |
|----------------------------|-------------------------|---------------|--------------|--------|--------|
| unauthenticated-denied     | GET /customers/c1       | no            |              |        | 401    |
| same-tenant-user-allowed   | GET /customers/c1       | yes           | user         | t1     | 200    |
| cross-tenant-user-denied   | GET /customers/c1       | yes           | user         | t2     | 403    |
| admin-same-tenant-allowed  | GET /customers/c1       | yes           | tenant_admin | t1     | 200    |
| missing-customer-not-found | GET /customers/missing  | yes           | user         | t1     | 404    |
