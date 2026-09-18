# API

The service exposes read access to customer records. All endpoints require
authentication and enforce tenant isolation.

### GET /customers/{id}

Returns a single customer belonging to the authenticated user's tenant.

### GET /customers

Returns the list of customers visible to the authenticated principal within
their own tenant.
