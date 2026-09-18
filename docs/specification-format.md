# Specification Format

SDC specifications are plain Markdown. A project is a directory of `.md` files;
each file may focus on one category or combine several. The loader merges all
files, so how you split them does not affect the resulting IR.

## Categories

`Application`, `API`, `Authentication`, `Authorization`, `Data`, `Behavior`,
`Security`, `Performance`, `Reliability`, `Observability`, `Deployment`,
`Testing`, `Dependencies`.

Not every project needs every category.

## Conventions the normalizer understands

- **Application**: `Name:`, `Version:`, `Description:` key/value lines.
- **API**: `### METHOD /path/{param}` subheadings; the following paragraph is a
  summary. Path parameters and the primary entity are inferred.
- **Authentication**: prose mentioning `OAuth2` / `bearer` / `JWT`, and
  `required`.
- **Authorization**: prose rules like
  *"A normal user may access customers belonging to their own tenant"*,
  *"A tenant administrator may access all customers belonging to their tenant"*,
  *"Cross-tenant access is forbidden"*, *"decisions must be auditable"*.
- **Data**: an entity heading (`### Customer`) followed by a
  `| Field | Type | Sensitive |` table. Fields named `password`, `token`,
  `secret`, … are treated as sensitive automatically; `tenant_id` becomes the
  tenant scope.
- **Behavior**: condition → status prose (unauthenticated → 401, unauthorized →
  403, not found → 404, success → 200).
- **Security**: bullet requirements, mapped to machine check ids where possible.
- **Performance**: `p99 latency ... below 50ms`, `... 10,000 requests per second`.
- **Testing**: a table of `name | endpoint | authenticated | role | tenant |
  expect` rows.

See [`../examples/customer-api`](../examples/customer-api) for a full example.
