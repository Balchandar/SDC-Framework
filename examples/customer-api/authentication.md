# Authentication

OAuth2 bearer authentication is required.

Every request must present a valid bearer token in the `Authorization` header.
Tokens are JWTs signed by the identity provider. The token subject identifies
the principal and carries the principal's tenant and role claims.
