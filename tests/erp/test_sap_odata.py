"""Direct SAP S/4HANA connection (libs/integrations/sap_odata.py), against a fake OData
server built from SAP's published API model (tests/erp/sap_fake.py)."""

import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from libs.integrations import sap_odata, sap_spend  # noqa: E402
from libs.integrations.sap_odata import SapError  # noqa: E402
import sap_fake  # noqa: E402
from sap_fake import FakeSap, order, partner  # noqa: E402

CONN = {"base_url": "https://s4.example.com", "sap_client": "100", "username": "SCIRM_COMM", "password": "s3cret!"}
TODAY = date(2026, 10, 21)


@pytest.fixture
def sap(monkeypatch):
    """Install a fake SAP system; strict mode off unless a test turns it on."""
    def install(fake):
        monkeypatch.setattr(sap_odata, "transport_factory", lambda: fake)
        return fake
    monkeypatch.setattr(sap_odata, "STRICT", False)
    return install


def run(coro):
    return asyncio.run(coro)


class TestBaseUrl:
    @pytest.mark.parametrize("url, expected", [
        ("https://S4.Example.com/", "https://s4.example.com"),
        ("https://api.example.com:8443/s4", "https://api.example.com:8443/s4"),
    ])
    def test_canonical(self, url, expected):
        assert sap_odata.validate_base_url(url, strict=True) == expected

    @pytest.mark.parametrize("url, words", [
        ("http://s4.example.com", "https"),
        ("https://user:pw@s4.example.com", "own fields"),
        ("https://s4.example.com/?sap-client=100", "query"),
        ("https://s4.example.com/#x", "fragment"),
        ("https://s4.example.com/sap/opu/odata/sap/API_BUSINESS_PARTNER", "base address"),
        ("ftp://s4.example.com", "https"),
        ("s4.example.com", "https"),
    ])
    def test_rejected(self, url, words):
        with pytest.raises(SapError, match=words):
            sap_odata.validate_base_url(url, strict=True)

    def test_http_allowed_only_in_development(self):
        assert sap_odata.validate_base_url("http://localhost:4004", strict=False) == "http://localhost:4004"

    @pytest.mark.parametrize("value", ["1", "1000", "abc"])
    def test_client(self, value):
        with pytest.raises(SapError):
            sap_odata.validate_client(value)
        assert sap_odata.validate_client(" 100 ") == "100" and sap_odata.validate_client("") is None


class TestOutboundGuard:
    @pytest.mark.parametrize("ips", [["10.0.0.5"], ["127.0.0.1"], ["169.254.169.254"], ["192.168.1.1"],
                                     ["100.64.0.1"], ["::1"], ["fd00::1"], ["::ffff:10.0.0.1"],
                                     ["93.184.216.34", "10.0.0.5"]])  # every address is checked
    def test_private_and_reserved_addresses_are_refused(self, sap, monkeypatch, ips):
        fake = sap(FakeSap())
        monkeypatch.setattr(sap_odata, "resolve", lambda host, port: ips)
        result = run(sap_odata.check_connection(CONN, strict=True))
        assert not result["ok"] and "private or reserved" in result["checks"][0]["detail"]
        assert fake.requests == []

    def test_ip_literals_are_checked_too(self, sap):
        sap(FakeSap())
        with pytest.raises(SapError, match="private"):
            run(sap_odata.fetch_suppliers({**CONN, "base_url": "https://10.1.2.3"}, strict=True))

    def test_requests_go_to_the_checked_address_with_the_host_name_kept_for_tls(self, sap, monkeypatch):
        fake = sap(FakeSap([partner("1", "1", "Acme GmbH")]))
        monkeypatch.setattr(sap_odata, "resolve", lambda host, port: ["93.184.216.34"])
        run(sap_odata.fetch_suppliers(CONN, today=TODAY, strict=True))
        first = fake.requests[0]
        assert first.url.host == "93.184.216.34" and first.url.port in (None, 443)
        assert first.headers["host"] == "s4.example.com"
        assert first.extensions.get("sni_hostname") == "s4.example.com"
        assert first.headers["sap-client"] == "100" and first.headers["authorization"].startswith("Basic ")

    def test_unknown_host(self, sap, monkeypatch):
        sap(FakeSap())

        def fail(host, port):
            raise OSError("nodename nor servname provided")
        monkeypatch.setattr(sap_odata, "resolve", fail)
        with pytest.raises(SapError, match="could not be found"):
            run(sap_odata.fetch_suppliers(CONN, strict=True))

    def test_redirects_are_not_followed(self, sap):
        fake = sap(FakeSap(redirect=True))
        with pytest.raises(SapError, match="redirected"):
            run(sap_odata.fetch_suppliers(CONN))
        assert len(fake.requests) == 1

    def test_responses_are_capped(self, sap, monkeypatch):
        monkeypatch.setattr(sap_odata, "MAX_RESPONSE_BYTES", 1000)
        sap(FakeSap(body_bytes=5000))
        with pytest.raises(SapError, match="larger response"):
            run(sap_odata.fetch_suppliers(CONN))

    def test_errors_never_carry_sap_bodies_or_the_password(self, sap):
        sap(FakeSap(status={sap_fake.BP: 401}))
        with pytest.raises(SapError) as err:
            run(sap_odata.fetch_suppliers(CONN))
        message = str(err.value)
        assert "HTTP 401" in message and "SAP_COM_0008" in message
        assert "logon page" not in message and CONN["password"] not in message


class TestMetadata:
    def test_missing_field_stops_before_reading_data(self, sap):
        fake = sap(FakeSap([partner("1", "1", "Acme GmbH")], drop={"A_Supplier": "PurchasingIsBlocked"}))
        with pytest.raises(SapError, match="A_Supplier has no PurchasingIsBlocked"):
            run(sap_odata.fetch_suppliers(CONN))
        assert fake.queries("A_BusinessPartner") == []

    def test_dtd_is_refused(self):
        with pytest.raises(SapError, match="DTD"):
            sap_odata.properties_from_metadata(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x/>')

    def test_check_connection_reports_each_service(self, sap):
        sap(FakeSap(status={sap_fake.PO: 403}))
        result = run(sap_odata.check_connection(CONN))
        by = {c["service"]: c for c in result["checks"]}
        assert not result["ok"] and by["API_BUSINESS_PARTNER"]["ok"]
        assert not by["API_PURCHASEORDER_PROCESS_SRV"]["ok"] and "SAP_COM_0053" in by["API_PURCHASEORDER_PROCESS_SRV"]["detail"]


class TestSuppliers:
    def test_mapping_to_supplier_rows(self, sap):
        fake = sap(FakeSap([
            # The business partner number differs from the supplier number (LIFNR): the key is LIFNR.
            partner("1000042", "0000100123", "Müller Präzisionsteile GmbH", "DE", "Köln", vat="DE123456789"),
            partner("1000043", "100124", "Blocked Corp", "US", "Boston", purchasing_block=True),
            partner("1000044", "100125", "Gone Ltd", "GB", "Leeds", deleted=True),
        ]))
        rows, warnings = run(sap_odata.fetch_suppliers(CONN, today=TODAY))
        by = {r["number"]: r for r in rows}
        assert set(by) == {"100123", "100124", "100125"} and warnings == []
        assert by["100123"]["name"] == "Müller Präzisionsteile GmbH" and by["100123"]["country_code"] == "DE"
        assert by["100123"]["city"] == "Köln" and by["100123"]["vat_number"] == "DE123456789"
        assert by["100123"]["blocked"] is False and by["100124"]["blocked"] is True
        assert by["100125"]["deletion_flag"] is True
        query = fake.queries("A_BusinessPartner")[0]
        assert query["$filter"] == "Supplier ne ''"
        assert set(query["$expand"].split(",")) == {"to_Supplier", "to_BusinessPartnerAddress"}
        assert "to_Supplier/PostingIsBlocked" in query["$select"] and "to_BusinessPartnerAddress/Country" in query["$select"]

    def test_long_names_continue_and_second_lines_become_aliases(self, sap):
        sap(FakeSap([partner("1", "1", "International Semiconductor Mfg Co.", name2="Ltd"),
                     partner("2", "2", "Acme Holding", name2="Acme Components GmbH")]))
        rows, _ = run(sap_odata.fetch_suppliers(CONN, today=TODAY))
        by = {r["number"]: r for r in rows}
        assert by["1"]["name"] == "International Semiconductor Mfg Co. Ltd"
        assert by["2"]["aliases"] == ["Acme Components GmbH"]

    def test_the_address_valid_today_is_used(self, sap):
        old = {"AddressID": "1", "Country": "FR", "CityName": "Lyon", "ValidityStartDate": "/Date(946684800000)/",
               "ValidityEndDate": sap_fake.date_ms("2020-01-01")}
        current = {"AddressID": "2", "Country": "DE", "CityName": "Berlin", "ValidityStartDate": sap_fake.date_ms("2020-01-02"),
                   "ValidityEndDate": "/Date(253402214400000)/"}
        sap(FakeSap([partner("1", "1", "Moved GmbH", addresses=[old, current])]))
        rows, _ = run(sap_odata.fetch_suppliers(CONN, today=TODAY))
        assert rows[0]["country_code"] == "DE" and rows[0]["city"] == "Berlin"

    def test_all_pages_are_read(self, sap, monkeypatch):
        monkeypatch.setattr(sap_odata, "SUPPLIER_PAGE", 2)
        fake = sap(FakeSap([partner(str(i), str(i), f"Supplier {i} GmbH") for i in range(1, 6)]))
        rows, _ = run(sap_odata.fetch_suppliers(CONN, today=TODAY))
        assert len(rows) == 5 and [q["$skip"] for q in fake.queries("A_BusinessPartner")] == ["0", "2", "4"]

    def test_a_failed_page_fails_the_whole_read(self, sap, monkeypatch):
        monkeypatch.setattr(sap_odata, "SUPPLIER_PAGE", 2)
        sap(FakeSap([partner(str(i), str(i), f"Supplier {i} GmbH") for i in range(1, 6)], fail_after_pages=1))
        with pytest.raises(SapError, match="HTTP 500"):
            run(sap_odata.fetch_suppliers(CONN, today=TODAY))

    def test_fewer_records_than_counted_fails(self, sap):
        sap(FakeSap([partner("1", "1", "Acme GmbH")], short_by=3))
        with pytest.raises(SapError, match="counted 4 .* returned 1"):
            run(sap_odata.fetch_suppliers(CONN, today=TODAY))

    def test_too_many_suppliers_fails_rather_than_truncating(self, sap, monkeypatch):
        monkeypatch.setattr(sap_odata.sap_import, "MAX_ROWS", 2)
        sap(FakeSap([partner(str(i), str(i), f"S{i} GmbH") for i in range(1, 4)]))
        with pytest.raises(SapError, match="more than the 2"):
            run(sap_odata.fetch_suppliers(CONN, today=TODAY))


class TestOrders:
    def orders(self):
        return [
            order("4500000001", "0000100123", "2026-09-15", [{"NetAmount": "7500.00", "NetPriceAmount": "75.00",
                                                              "OrderQuantity": "100"}]),
            order("4500000002", "100124", "2026-03-01", [{"NetAmount": "2500.00", "NetPriceAmount": "25.00",
                                                          "OrderQuantity": "100"},
                                                         {"NetAmount": "999.00", "NetPriceAmount": "9.99", "OrderQuantity": "100",
                                                          "PurchasingDocumentDeletionCode": "L"}]),
            order("4500000003", "100124", "2026-05-01", [{"NetAmount": "10.00", "NetPriceAmount": "10", "OrderQuantity": "1"}],
                  deletion="L"),
            order("4500000004", "100125", "2026-06-01", [{"NetAmount": "5000", "NetPriceAmount": "5000",
                                                          "OrderQuantity": "1"}], currency="JPY"),
        ]

    def test_lines_and_summary(self, sap):
        fake = sap(FakeSap(orders=self.orders()))
        lines, warnings, end = run(sap_odata.fetch_orders(CONN, today=TODAY))
        assert end == TODAY and warnings == []
        summary = sap_spend.summarize(lines, end=end)
        assert summary["period"] == {"from": "2025-10-22", "to": "2026-10-21"}
        assert summary["suppliers"]["100123"]["spend"] == {"EUR": "7500.00"}
        assert summary["suppliers"]["100124"]["spend"] == {"EUR": "2500.00"}  # deleted item and order excluded
        assert summary["suppliers"]["100125"]["spend"] == {"JPY": "5000.00"} and summary["main_currency"] == "EUR"
        query = fake.queries("A_PurchaseOrder")[0]
        assert query["$filter"] == "PurchaseOrderDate ge datetime'2025-10-22T00:00:00'"
        assert "to_PurchaseOrderItem/NetAmount" in query["$select"] and query["$expand"] == "to_PurchaseOrderItem"

    def test_without_net_amount_value_is_price_times_quantity(self, sap):
        fake = sap(FakeSap(orders=[order("1", "7", "2026-09-01", [
            {"NetPriceAmount": "12.50", "OrderQuantity": "40", "NetPriceQuantity": "10"},  # price per 10 pieces
            {"NetPriceAmount": "3.00", "OrderQuantity": "2", "NetPriceQuantity": "0"},     # 0 price unit counts as 1
        ])], net_amount=False))
        lines, warnings, _ = run(sap_odata.fetch_orders(CONN, today=TODAY))
        assert [l["amount"] for l in lines] == [Decimal("50"), Decimal("6")]
        assert any("NetAmount" in w for w in warnings)
        assert "NetAmount" not in fake.queries("A_PurchaseOrder")[0]["$select"]

    def test_period_ends_today_even_when_the_latest_order_is_old(self, sap):
        sap(FakeSap(orders=[order("1", "7", "2026-01-10", [{"NetAmount": "100", "NetPriceAmount": "100",
                                                            "OrderQuantity": "1"}])]))
        lines, _, end = run(sap_odata.fetch_orders(CONN, today=TODAY))
        assert sap_spend.summarize(lines, end=end)["period"]["to"] == "2026-10-21"

    def test_unreadable_items_are_counted(self, sap):
        sap(FakeSap(orders=[order("1", "", "2026-09-01", [{"NetAmount": "1", "NetPriceAmount": "1", "OrderQuantity": "1"}]),
                            order("2", "7", "2026-09-01", [{"NetAmount": "1", "NetPriceAmount": "1", "OrderQuantity": "1"}],
                                  currency="")]))
        lines, warnings, _ = run(sap_odata.fetch_orders(CONN, today=TODAY))
        assert lines == [] and any("2 order item(s) skipped" in w for w in warnings)


@pytest.mark.parametrize("value, expected", [
    ("/Date(1729468800000)/", date(2024, 10, 21)),
    ("/Date(1729468800000+0000)/", date(2024, 10, 21)),
    ("2026-09-15T00:00:00", date(2026, 9, 15)),
    ("", None), (None, None), ("garbage", None),
])
def test_dates(value, expected):
    assert sap_odata.parse_date(value) == expected
