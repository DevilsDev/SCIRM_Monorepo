# Importing suppliers from SAP

SCIRM reads your supplier master from a file you export from SAP. It does not connect
to your SAP system, and it stores no SAP credentials.

## 1. Export table LFA1

In SAP ECC or S/4HANA, export the vendor master table **LFA1**, for example with
transaction **SE16N**, as a text or spreadsheet file (tab-, semicolon- or comma-separated).
Include these fields:

| Field | Meaning | Needed |
|---|---|---|
| LIFNR | Supplier number | required |
| NAME1 | Name | required |
| NAME2, NAME3, NAME4 | Further name lines | recommended |
| LAND1 | Country key | recommended (disaster exposure needs it) |
| ORT01 | City | optional |
| SPERR, SPERM | Posting block, purchasing block | recommended |
| LOEVM | Deletion flag | recommended |
| STCEG | VAT registration number | optional |

If your export has column labels instead of field names, choose which column holds
each field on the import page. UTF-8, UTF-16 and Windows-1252 files are all read correctly.

## 2. Preview, then import

**Suppliers → Import from SAP** shows what the import will do before anything is saved.
Only admins and analysts can import.

- **Matching on re-import.** Suppliers are recognised by their SAP number. Leading zeros don't matter: `0000100123` and `100123` are the same supplier.
- **New suppliers** get the code `SAP-<number>`.
- **Same name as a supplier added by hand.** Nothing happens until you choose. You can link the SAP number to the existing supplier, which keeps it and its history, or create a new supplier.
- **Blocked or deleted in SAP.**
  - A supplier blocked in SAP (SPERR or SPERM) is imported as inactive. It becomes active again when the block is lifted.
  - A supplier marked for deletion (LOEVM) is not imported. If it was imported before, it is deactivated.
- **Nothing is deleted.**
  - Suppliers missing from the file are listed. They are deactivated only if you ask, and not when the file has fewer than half the suppliers of the earlier imports, because that usually means the export was incomplete.
  - A supplier you deactivated by hand stays inactive.
- **Aliases** are only added, never removed, so names you entered yourself are kept.
  - A second name line becomes an alias only when it reads as a company name (it contains a legal form such as GmbH, Ltd or Inc).
  - When NAME1 is full (35 characters), NAME2 is treated as the rest of the name.

The audit log records who imported, when, and the counts. It does not record the file contents.

## 3. Rank suppliers by purchase-order spend

Once the supplier master is imported, upload purchase-order items to rank suppliers by
what you bought from them in the last 12 months. The upload is on the same page, under
**Purchase-order spend**.

Export purchase-order items with their header fields: table EKPO joined with EKKO, or a
purchase-order list (for example ME2N or ME2L) exported to a file. Include:

| Field | Meaning | Needed |
|---|---|---|
| LIFNR | Supplier number | required |
| BEDAT | Purchasing document date | required |
| NETWR | Net order value of the item | required |
| WAERS | Currency | required |
| EBELN | Purchase order number (counts orders) | optional |
| WERKS | Plant | optional |
| LOEKZ | Deletion flag (deleted items are excluded) | optional |

- **Period:** the 12 months up to the latest order date in the file.
- **Currencies are never converted or added together.** Ranking and the share
  percentage use the currency with the most spend in the file; other currencies are
  shown alongside.
- **Formats:** dates in any SAP user format and amounts written like `1.234,56` or
  `1,234.56` are read, including a trailing minus for credits. An amount such as
  `1,234` could mean two things; choose the decimal separator your export uses and
  preview again.
- **Each upload replaces earlier spend.** Suppliers with no orders in the period get
  zero. Spend on supplier numbers that are not imported is listed, not stored; import
  the supplier master to include them.
- The audit log records the period and totals, never individual orders or amounts.

The Suppliers page then shows **Spend (12 mo)** with each supplier's share, and can
sort by largest spend.

## Not covered yet

- **A direct API connection** (OData `API_BUSINESS_PARTNER`). This would need per-tenant credentials stored encrypted. Until then, the file export keeps your SAP credentials inside your own network.
