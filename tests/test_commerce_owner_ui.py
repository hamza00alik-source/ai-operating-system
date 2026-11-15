"""Static checks for owner-controlled WooCommerce controls."""


def test_woocommerce_ui_is_read_only_and_does_not_persist_credentials_in_browser():
    from opencompany_app.woocommerce_ui import WOOCOMMERCE_HTML, WOOCOMMERCE_JS
    assert "read-only connection" in WOOCOMMERCE_HTML
    assert "consumer_secret" in WOOCOMMERCE_JS
    assert 'method:"PUT"' in WOOCOMMERCE_JS
    assert 'method:"POST"' in WOOCOMMERCE_JS
    assert "/products" in WOOCOMMERCE_JS
    assert "/orders" in WOOCOMMERCE_JS
    assert "innerHTML" not in WOOCOMMERCE_JS
    assert 'byId("woo-consumer-secret").value=""' in WOOCOMMERCE_JS
    assert "writes_enabled" in WOOCOMMERCE_HTML or "disabled" in WOOCOMMERCE_HTML


def test_product_rd_ui_displays_automation_status_without_control_actions():
    from opencompany_app.product_rd_ui import PRODUCT_RD_HTML, PRODUCT_RD_JS
    assert "prd-automation-status" in PRODUCT_RD_HTML
    assert "/product-rd/automation/status" in PRODUCT_RD_JS
    assert "external actions disabled" in PRODUCT_RD_JS
