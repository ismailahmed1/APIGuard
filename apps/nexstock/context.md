NexStock is a warehouse and inventory management API. Every test starts from this seed data:

- Users: role `admin` (Admin) and role `manager` (Manager). In request bodies, write their
  credentials only as the placeholders {{admin.email}}, {{admin.password}}, {{manager.email}} and
  {{manager.password}}; APIGuard fills them in at run time.
- Categories 1-10: 1 Electronics, 2 Raw Materials, 3 Packaging, 4 Office Supplies,
  5 Safety Equipment, 6 Tools & Hardware, 7 Cleaning Supplies, 8 Furniture, 9 Spare Parts,
  10 Consumables. Category names are unique.
- Products 1-30, three per category, all active. Product 1 is SKU ELEC-001 "Electronics Item 1" in
  category 1. SKUs follow PREFIX-NNN (ELEC, RAW, PACK, OFF, SAFE, TOOL, CLEAN, FURN, SPAR, CONS) and
  are unique. Product 1 has 168 units in stock (minimum 23, maximum 594).
- Every product has an inventory record; products 6, 18, 26 and 27 are at or below their minimum.
- There are 150 stock movements of type IN and OUT.
- IDs above 30 do not exist for products or above 10 for categories.
