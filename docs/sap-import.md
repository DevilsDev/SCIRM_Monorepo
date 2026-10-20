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

## Not covered yet

- **Purchase-order spend,** used to rank suppliers by what you buy from them.
- **A direct API connection** (OData `API_BUSINESS_PARTNER`). This would need per-tenant credentials stored encrypted. Until then, the file export keeps your SAP credentials inside your own network.
