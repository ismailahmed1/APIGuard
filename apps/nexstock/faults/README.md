# NexStock seeded faults

Each patch adds one fault to the pinned NexStock commit. The original application is never
changed: a fault is applied only when the image is built with `NEXSTOCK_FAULT` set.

| ID | Category | Change | Expected symptom |
|---|---|---|---|
| F01 | Unauthorized access | `GET /api/products` no longer requires a token | Anonymous request returns 200 instead of 401 |
| F02 | Wrong status code | `POST /api/categories` returns 200 instead of 201 | Successful create returns an undocumented status |
| F03 | Input validation removed | `unit_price` no longer has to be positive | A product with a negative price is created |
| F04 | Broken authorization | `DELETE /api/categories/{category_id}` permits Managers | A Manager deletes a category instead of receiving 403 |
| F05 | Business-logic and semantic testing | `GET /api/products` ignores `category_id` | A filtered request returns products from other categories |
| F06 | Stateful workflow testing | Product deletion reports success, but the product remains available | `DELETE /api/products/{product_id}` returns success; subsequent detail and list requests still return the product |

Start NexStock with one fault (from the repository root):

```sh
NEXSTOCK_FAULT=F01-products-list-without-auth docker compose -f apps/nexstock/compose.yaml up --detach --wait --build api
```

Start it without `NEXSTOCK_FAULT` (and with `--build`) to return to the original application.
