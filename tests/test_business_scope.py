import pytest

from ai_os.business_scope import validate_business_task_scope, validate_workflow_scope


def test_physical_agency_rejects_digital_order_fulfillment():
    with pytest.raises(ValueError, match="cannot fulfil an order"):
        validate_business_task_scope(
            "physical-agency",
            "Fulfil customer order with downloadable game assets",
        )


def test_physical_brand_rejects_software_substitution():
    with pytest.raises(ValueError, match="cannot fulfil an order"):
        validate_business_task_scope(
            "physical-brand",
            "Provide software license as replacement for product order",
        )


def test_digital_business_rejects_physical_shipping_commitment():
    with pytest.raises(ValueError, match="cannot promise or fulfil physical goods"):
        validate_business_task_scope(
            "digital-products",
            "Ship physical inventory to customer and manage delivery",
        )


def test_digital_business_allows_digital_deliverable():
    validate_business_task_scope(
        "digital-products",
        "Prepare a downloadable 3D model package for a digital storefront",
    )


def test_physical_business_allows_marketing_mentions_of_digital_channels():
    validate_business_task_scope(
        "physical-agency",
        "Create digital marketing assets and research physical product buyers",
    )


def test_unknown_business_fails_closed():
    with pytest.raises(ValueError, match="Unknown business environment"):
        validate_business_task_scope("other", "General research")


def test_digital_launch_workflow_is_scoped():
    with pytest.raises(ValueError, match="only run inside"):
        validate_workflow_scope("digital-product-launch", "physical-agency")
    validate_workflow_scope("digital-product-launch", "digital-products")
