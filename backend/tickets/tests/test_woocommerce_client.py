from datetime import datetime, timezone
from unittest.mock import Mock, patch

from tickets.woocommerce_client import WooCommerceClient


def _fake_response(json_body, status_code=200):
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status = Mock()
    return resp


@patch("tickets.woocommerce_client.requests.get")
def test_list_paid_orders_uses_basic_auth_from_settings(mock_get, settings):
    settings.WOOCOMMERCE_API_URL = "https://romeral.test/wp-json/wc/v3"
    settings.WOOCOMMERCE_API_KEY = "ck_test"
    settings.WOOCOMMERCE_API_SECRET = "cs_test"
    mock_get.return_value = _fake_response([])

    client = WooCommerceClient()
    client.list_paid_orders(datetime(2026, 11, 1, tzinfo=timezone.utc))

    mock_get.assert_called_once()
    _, kwargs = mock_get.call_args
    assert kwargs["auth"] == ("ck_test", "cs_test")
    assert kwargs["params"]["status"] == "processing,completed"


@patch("tickets.woocommerce_client.requests.get")
def test_list_paid_orders_returns_the_order_dicts_unchanged(mock_get, settings):
    """The REST API's order resource is the same shape
    create_ticket_from_order reads, so no remapping should happen here."""
    settings.WOOCOMMERCE_API_URL = "https://romeral.test/wp-json/wc/v3"
    settings.WOOCOMMERCE_API_KEY = "ck_test"
    settings.WOOCOMMERCE_API_SECRET = "cs_test"
    order = {"id": 777, "number": "777", "status": "processing", "billing": {}}
    mock_get.return_value = _fake_response([order])

    client = WooCommerceClient()
    orders = client.list_paid_orders(datetime(2026, 11, 1, tzinfo=timezone.utc))

    assert orders == [order]


@patch("tickets.woocommerce_client.requests.get")
def test_list_paid_orders_pages_until_a_short_page_is_returned(mock_get):
    full_page = [{"id": i} for i in range(100)]
    last_page = [{"id": 999}]
    mock_get.side_effect = [_fake_response(full_page), _fake_response(last_page)]

    client = WooCommerceClient(
        base_url="https://romeral.test/wp-json/wc/v3",
        api_key="ck",
        api_secret="cs",
    )
    orders = client.list_paid_orders(datetime(2026, 11, 1, tzinfo=timezone.utc))

    assert len(orders) == 101
    assert mock_get.call_count == 2


@patch("tickets.woocommerce_client.requests.get")
def test_list_paid_orders_never_calls_a_non_get_method(mock_get):
    """Defensive: this client is read-only by construction (it only ever
    calls requests.get), never requests.post/put/delete."""
    mock_get.return_value = _fake_response([])

    client = WooCommerceClient(
        base_url="https://romeral.test/wp-json/wc/v3",
        api_key="ck",
        api_secret="cs",
    )
    client.list_paid_orders(datetime(2026, 11, 1, tzinfo=timezone.utc))

    assert mock_get.called
