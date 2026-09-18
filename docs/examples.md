# Examples

## customer-api

`examples/customer-api` is the reference MVP. It specifies a multi-tenant
customer service and builds to a standalone HTTP API.

```bash
cd examples/customer-api
sdc build      # -> dist/customer-api, .build/*.json
sdc run        # SDC_JWT_SECRET=... PORT=8080
```

Endpoints: `GET /customers/{id}`, `GET /customers`, plus `/healthz`, `/readyz`,
`/metrics`.

Try the drift loop:

```bash
sdc build
echo "\nA manager may access customers in their assigned departments." >> authorization.md
sdc build      # detects the change, shows a semantic diff, re-verifies, rebuilds
```

Mint a token to call it (HS256 with your SDC_JWT_SECRET), claims:
`{"sub": "...", "tenant_id": "t1", "role": "user" | "tenant_admin"}`.
Seeded ids: `c1`, `c2` in tenant `t1`; `c3` in tenant `t2`.
