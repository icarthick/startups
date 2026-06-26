"""Tests for extract_heroku_billing tool."""

import json
from pathlib import Path

import pytest

from engine.tools.heroku.discover.billing import extract_heroku_billing


@pytest.fixture
def enterprise_csv(tmp_path):
    (tmp_path / "heroku-billing-2026-02.csv").write_text(
        "app,dyno_units,addon_total,platform_total,period\n"
        "my-web-app,100.00,200.00,50.00,2026-02\n"
        "my-api-app,75.00,25.00,0.00,2026-02\n"
    )
    return tmp_path


@pytest.fixture
def invoice_csv(tmp_path):
    (tmp_path / "invoice-march.csv").write_text(
        "description,amount,period_start,period_end\n"
        "Dyno usage for my-web-app,100.00,2026-03-01,2026-03-31\n"
        "Add-on: heroku-postgresql for my-web-app,200.00,2026-03-01,2026-03-31\n"
        "Platform SSL,15.00,2026-03-01,2026-03-31\n"
    )
    return tmp_path


@pytest.fixture
def invoice_json(tmp_path):
    data = {
        "total": 350.00,
        "period_start": "2026-04-01",
        "period_end": "2026-04-30",
        "charges": [
            {"description": "Dyno usage for api-app", "amount": 150.00},
            {"description": "Add-on: heroku-redis for api-app", "amount": 50.00},
            {"description": "Platform", "amount": 10.00},
        ]
    }
    (tmp_path / "billing-april.json").write_text(json.dumps(data))
    return tmp_path


class TestNoFiles:
    def test_empty_dir(self, tmp_path):
        result = extract_heroku_billing(str(tmp_path))
        assert result["status"] == "skipped"

    def test_unrecognized_csv(self, tmp_path):
        (tmp_path / "billing.csv").write_text("foo,bar,baz\n1,2,3\n")
        result = extract_heroku_billing(str(tmp_path))
        assert result["status"] == "skipped"


class TestEnterpriseCsv:
    def test_parses_enterprise(self, enterprise_csv):
        result = extract_heroku_billing(str(enterprise_csv))
        assert result["status"] == "ok"
        assert result["total_monthly_cost"] == 450.00
        assert result["source_format"] == "enterprise_csv"

    def test_writes_output(self, enterprise_csv):
        mdir = enterprise_csv / ".migration" / "test"
        mdir.mkdir(parents=True)
        extract_heroku_billing(str(enterprise_csv), str(mdir))
        data = json.loads((mdir / "_billing-discovery.json").read_text())
        assert data["billing_profile"]["available"] is True
        assert data["billing_profile"]["total_monthly_cost"] == 450.00
        assert len(data["billing_profile"]["line_items"]) == 5


class TestInvoiceCsv:
    def test_parses_invoice(self, invoice_csv):
        result = extract_heroku_billing(str(invoice_csv))
        assert result["status"] == "ok"
        assert result["total_monthly_cost"] == 315.00
        assert result["source_format"] == "invoice_csv"

    def test_description_parsing(self, invoice_csv):
        mdir = invoice_csv / ".migration" / "test"
        mdir.mkdir(parents=True)
        extract_heroku_billing(str(invoice_csv), str(mdir))
        data = json.loads((mdir / "_billing-discovery.json").read_text())
        items = data["billing_profile"]["line_items"]
        dyno = next(i for i in items if i["category"] == "dyno")
        assert dyno["resource_name"] == "my-web-app"
        platform = next(i for i in items if i["category"] == "platform")
        assert platform["resource_name"] == "platform"


class TestInvoiceJson:
    def test_parses_json(self, invoice_json):
        result = extract_heroku_billing(str(invoice_json))
        assert result["status"] == "ok"
        assert result["source_format"] == "invoice_json"
        assert result["line_item_count"] == 3

    def test_billing_period(self, invoice_json):
        mdir = invoice_json / ".migration" / "test"
        mdir.mkdir(parents=True)
        extract_heroku_billing(str(invoice_json), str(mdir))
        data = json.loads((mdir / "_billing-discovery.json").read_text())
        assert data["billing_profile"]["billing_period"] == "2026-04"
