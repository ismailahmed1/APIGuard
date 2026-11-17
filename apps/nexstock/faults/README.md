# NexStock seeded faults

Each patch adds one fault to the pinned NexStock commit. The original application is never
changed: a fault is applied only when the image is built with `NEXSTOCK_FAULT` set.

| ID | Category | Change | Expected symptom |
|---|---|---|---|
| F01 | Unauthorized access | `GET /api/products` no longer requires a token | Anonymous request returns 200 instead of 401 |
| F02 | Wrong status code | `POST /api/categories` returns 200 instead of 201 | Successful create returns an undocumented status |
| F03 | Input validation removed | `unit_price` no longer has to be positive | A product with a negative price is created |

Start NexStock with one fault (from the repository root):

```sh
NEXSTOCK_FAULT=F01-products-list-without-auth docker compose -f apps/nexstock/compose.yaml up --detach --wait --build api
```

Start it without `NEXSTOCK_FAULT` (and with `--build`) to return to the original application.
