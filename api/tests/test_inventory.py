"""Inventory business rules."""
from uuid import uuid4

import pytest


def _body(world, **over):
    plot = next(p for p in world.repo.plots.values() if p["farmer_id"] == world.farmer1["id"])
    base = {"plot_id": str(plot["id"]), "produce_type_id": 1, "quantity": "25.5", "unit": "bag", "grade": "B",
            "expected_harvest_date": "2026-12-15", "asking_price_minor": 350000}
    return {**base, **over}


def test_create_item_success(world):
    r = world.client.post("/inventory", json=_body(world), headers=world.h(world.farmer1["user_id"]))
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "available" and data["unit"] == "bag" and data["asking_price_minor"] == 350000
    assert data["currency"] == "KES" and data["farmer_id"] == str(world.farmer1["id"])


@pytest.mark.parametrize("qty", ["-1", "-0.01", "0", "0.00"])
def test_negative_or_zero_quantity_is_422(world, qty):
    before = len(world.repo.items)
    r = world.client.post("/inventory", json=_body(world, quantity=qty), headers=world.h(world.farmer1["user_id"]))
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["field"] == "quantity"
    assert len(world.repo.items) == before


def test_negative_quantity_rejected_on_update_too(world):
    r = world.client.patch(f"/inventory/{world.item1['id']}", json={"quantity": "-5"}, headers=world.h(world.farmer1["user_id"]))
    assert r.status_code == 422
    assert str(world.repo.items[world.item1["id"]]["quantity"]) == "10.00"


@pytest.mark.parametrize("field,value", [("grade", "D"), ("unit", "tonne"), ("asking_price_minor", -1),
                                          ("asking_price_minor", 12.5), ("expected_harvest_date", "next week"),
                                          ("quantity", "1.234"), ("produce_type_id", 0)])
def test_invalid_fields_are_422(world, field, value):
    r = world.client.post("/inventory", json=_body(world, **{field: value}), headers=world.h(world.farmer1["user_id"]))
    assert r.status_code == 422


def test_unknown_produce_type_is_422(world):
    r = world.client.post("/inventory", json=_body(world, produce_type_id=999), headers=world.h(world.farmer1["user_id"]))
    assert r.status_code == 422


def test_double_submit_with_same_client_request_id_creates_one_record(world):
    rid = str(uuid4())
    h = world.h(world.farmer1["user_id"])
    first = world.client.post("/inventory", json=_body(world, client_request_id=rid), headers=h)
    second = world.client.post("/inventory", json=_body(world, client_request_id=rid), headers=h)
    assert first.status_code == 201 and second.status_code == 200
    assert second.headers["idempotent-replay"] == "true"
    assert first.json()["id"] == second.json()["id"]
    assert sum(1 for i in world.repo.items.values() if i["client_request_id"] and str(i["client_request_id"]) == rid) == 1


def test_sold_item_cannot_be_updated_or_deleted(world):
    h = world.h(world.farmer1["user_id"])
    for resp in (world.client.patch(f"/inventory/{world.sold1['id']}", json={"quantity": "1"}, headers=h),
                 world.client.delete(f"/inventory/{world.sold1['id']}", headers=h)):
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "ITEM_SOLD"
    assert world.repo.items[world.sold1["id"]]["deleted_at"] is None


def test_even_admin_cannot_edit_sold_item(world):
    r = world.client.patch(f"/inventory/{world.sold1['id']}", json={"quantity": "1"}, headers=world.h(world.admin))
    assert r.status_code == 409


def test_marking_sold_then_editing_is_blocked(world):
    h = world.h(world.farmer1["user_id"])
    assert world.client.patch(f"/inventory/{world.item1['id']}", json={"status": "sold"}, headers=h).status_code == 200
    assert world.client.patch(f"/inventory/{world.item1['id']}", json={"grade": "C"}, headers=h).status_code == 409


def test_soft_delete_hides_item(world):
    h = world.h(world.farmer1["user_id"])
    assert world.client.delete(f"/inventory/{world.item1['id']}", headers=h).status_code == 204
    assert world.client.get(f"/inventory/{world.item1['id']}", headers=h).status_code == 404
    assert str(world.item1["id"]) not in {i["id"] for i in world.client.get("/inventory", headers=h).json()["items"]}
    assert world.item1["id"] in world.repo.items  # row kept (soft delete)


def test_empty_patch_is_422(world):
    assert world.client.patch(f"/inventory/{world.item1['id']}", json={}, headers=world.h(world.farmer1["user_id"])).status_code == 422


def test_inventory_filters_and_pagination(world):
    h = world.h(world.farmer1["user_id"])
    for _ in range(3):
        world.client.post("/inventory", json=_body(world, produce_type_id=2, grade="C"), headers=h)
    assert world.client.get("/inventory?produce_type_id=2", headers=h).json()["total"] == 3
    assert world.client.get("/inventory?grade=C", headers=h).json()["total"] == 3
    assert world.client.get("/inventory?status=sold", headers=h).json()["total"] == 1
    p = world.client.get("/inventory?page=1&page_size=2", headers=h).json()
    assert len(p["items"]) == 2 and p["total"] == 5 and p["has_more"]
    assert world.client.get("/inventory?grade=Z", headers=h).status_code == 422
