# Data

Customer records are stored in PostgreSQL. All reads and writes occur within a
transaction. Every customer belongs to exactly one tenant.

### Customer

| Field       | Type   | Sensitive |
|-------------|--------|-----------|
| id          | string | no        |
| tenant_id   | string | no        |
| name        | string | no        |
| email       | string | no        |
| password    | string | yes       |
| auth_token  | string | yes       |

The `id` field is the primary key. The `tenant_id` field scopes every record
to a tenant. The `password` and `auth_token` fields are sensitive and must
never be returned by the API or written to logs.
