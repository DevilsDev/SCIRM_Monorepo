# Connecting SCIRM to SAP S/4HANA

Instead of exporting files, an administrator can connect SCIRM to the organization's
SAP S/4HANA system. SCIRM then reads the supplier master and the last 12 months of
purchase orders itself. The same rules apply as for the
[file imports](sap-import.md): you see a preview first, possible duplicates wait for
your decision, nothing is deleted, and currencies are never converted.

**S/4HANA only.** SAP ECC has no such APIs, so on ECC use the file imports.

**Read only.** SCIRM only sends `GET` requests. It never creates, changes or deletes
anything in SAP.

## What SCIRM reads

| Data | SAP API (OData V2) | S/4HANA Cloud communication scenario |
|---|---|---|
| Suppliers: names, address (country, city), posting and purchasing blocks, deletion flag, VAT number | `API_BUSINESS_PARTNER`: `A_BusinessPartner` with `to_Supplier` and `to_BusinessPartnerAddress` | `SAP_COM_0008` |
| Purchase orders dated in the last 365 days, with their items | `API_PURCHASEORDER_PROCESS_SRV`: `A_PurchaseOrder` with `to_PurchaseOrderItem` | `SAP_COM_0053` |

Suppliers are keyed by the **supplier number** (LIFNR, the `Supplier` field), not by
the business partner number, which can differ. That is the number the LFA1 file import
uses and the one purchase orders carry. A supplier imported from a file and later from
the connection is therefore the same record in SCIRM.

An item's value is its net order value (`NetAmount`) where the SAP release has it. On
older releases it is net price × quantity ÷ price unit, and the preview says so: in that
case conditions such as discounts on the item may be missing.

## 1. Set up access in SAP

**S/4HANA Cloud:**

1. Create a communication system for SCIRM.
2. Create a communication user with a strong password.
3. Create communication arrangements for `SAP_COM_0008` and `SAP_COM_0053`. Use
   inbound services only, with read access.

**S/4HANA on-premise or private cloud:**

1. Activate the two OData services in `/IWFND/MAINT_SERVICE`.
2. Create a technical user that holds only display authorizations for business partners,
   suppliers and purchase orders.

**Network.** SCIRM connects only to addresses on the public internet, over HTTPS with
a valid certificate. It refuses private, loopback, link-local and cloud-metadata
addresses, and does not follow redirects. A system reachable only inside your network
needs a public endpoint in front of it, for example SAP API Management, SAP BTP, or a
reverse proxy that exposes just these two services.

## 2. Connect

On **Import from SAP**, an administrator enters:

- the system's base address, for example `https://my-s4.example.com` (without
  `/sap/opu/odata/...`);
- the SAP client, if your system needs one (three digits, e.g. `100`);
- the communication user and its password.

**Save and test** checks both services. For each, it reads `$metadata`, confirms that
every field SCIRM reads exists, and reads one record to prove authorization. Problems
are reported per service, for example *HTTP 403: check that the communication user is
assigned to SAP_COM_0053*.

## 3. Import

- **Suppliers:** choose *From the SAP connection* and then *Preview from SAP*. The preview
  works as for a file. Applying reads SAP again and re-plans, so it can differ slightly
  from the preview if suppliers changed in between.
- **Spend:** *Preview the last 12 months from SAP*. The period always ends today, even if
  the latest order is older.

Analysts and admins can run imports. Auditors can see the connection's settings and
status, but not import or change anything.

An import reads everything before it plans anything. If any page fails, or SAP returns
fewer records than it counted, nothing is imported and the error says why. A partial
supplier list would otherwise look like suppliers removed from SAP. Imports stop rather
than truncate above 20,000 suppliers or 200,000 purchase orders; use the file imports
for larger volumes.

## Credentials and security

- The password is encrypted at rest with AES-256-GCM using `MFA_ENCRYPTION_KEY`, the
  same key that protects MFA seeds. It is bound to the organization and connection, so a
  copied value does not decrypt elsewhere. It is never returned by the API, written to
  the audit log, or included in error messages.
- Only administrators can create, change, test or remove the connection. Each of these
  actions is audited (the address and user name, never the password). Imports are
  audited with counts only.
- Each organization has its own connection, isolated by row-level security.
- Removing the connection deletes the stored password. Suppliers already imported stay.
- If `MFA_ENCRYPTION_KEY` is lost or replaced without `MFA_ENCRYPTION_KEY_PREVIOUS`,
  the stored password can no longer be read, and an administrator must enter it again.

## Not covered yet

- **Scheduled imports.** Imports run when someone starts them, because new possible
  duplicates need a person's decision.
- **OAuth 2.0 and X.509 client certificates.** Only user and password (basic
  authentication) are supported.
- **SAP ECC (RFC/BAPI).**

!!! note "How this was tested"
    The connector is tested against a simulated S/4HANA OData service built from SAP's
    published API model (`tests/erp/sap_fake.py`), not against a live SAP system. The
    first customer connection is the real test. Run *Test connection* first, and compare
    the first preview with a file export.
