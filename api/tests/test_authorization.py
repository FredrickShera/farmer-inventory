"""Server-side authorisation: who may see/do what, and that nothing leaks."""
from uuid import uuid4

from tests.conftest import bearer, make_token


def test_farmer_cannot_read_another_farmers_profile(world):
    other = world.farmer2["id"]
    r = world.client.get(f"/farmers/{other}", headers=world.h(world.farmer1["user_id"]))
    assert r.status_code == 403  # farmers have no access to this endpoint at all


def test_farmer_cannot_list_farmers(world):
    assert world.client.get("/farmers", headers=world.h(world.farmer1["user_id"])).status_code == 403


def test_farmer_inventory_list_contains_only_own_items(world):
    r = world.client.get("/inventory", headers=world.h(world.farmer1["user_id"]))
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()["items"]}
    assert str(world.item1["id"]) in ids and str(world.item2["id"]) not in ids


def test_farmer_cannot_filter_inventory_by_another_farmer(world):
    r = world.client.get(f"/inventory?farmer_id={world.farmer2['id']}", headers=world.h(world.farmer1["user_id"]))
    assert r.status_code == 403


def test_farmer_cannot_read_update_or_delete_another_farmers_item(world):
    h = world.h(world.farmer1["user_id"])
    iid = world.item2["id"]
    missing = uuid4()
    for method, kwargs in (("get", {}), ("patch", {"json": {"grade": "B"}}), ("delete", {})):
        real = getattr(world.client, method)(f"/inventory/{iid}", headers=h, **kwargs)
        ghost = getattr(world.client, method)(f"/inventory/{missing}", headers=h, **kwargs)
        assert real.status_code == ghost.status_code == 404
        assert real.json()["error"]["message"] == ghost.json()["error"]["message"]  # no existence oracle
    assert world.repo.items[iid]["grade"] == "A" and world.repo.items[iid]["deleted_at"] is None


def test_farmer_cannot_create_item_on_another_farmers_plot(world):
    other_plot = next(p for p in world.repo.plots.values() if p["farmer_id"] == world.farmer2["id"])
    body = {"plot_id": str(other_plot["id"]), "produce_type_id": 1, "quantity": "5", "unit": "kg", "grade": "A",
            "expected_harvest_date": "2026-12-01", "asking_price_minor": 1000}
    r = world.client.post("/inventory", json=body, headers=world.h(world.farmer1["user_id"]))
    assert r.status_code == 404 and r.json()["error"]["code"] == "PLOT_NOT_FOUND"


def test_officer_outside_ward_cannot_filter_farmers_by_that_ward(world):
    r = world.client.get("/farmers?ward_id=2", headers=world.h(world.officer))
    assert r.status_code == 403 and r.json()["error"]["code"] == "WARD_NOT_ASSIGNED"


def test_officer_sees_only_farmers_in_own_ward(world):
    r = world.client.get("/farmers", headers=world.h(world.officer))
    names = {f["full_name"] for f in r.json()["items"]}
    assert names == {"Wanjiru Mwangi"}  # Peter (ward 2) and Grace (ward 3) are invisible
    assert r.json()["total"] == 1


def test_officer_cannot_fetch_farmer_outside_ward_and_response_matches_nonexistent(world):
    h = world.h(world.officer)
    outside = world.client.get(f"/farmers/{world.farmer2['id']}", headers=h)
    ghost = world.client.get(f"/farmers/{uuid4()}", headers=h)
    assert outside.status_code == ghost.status_code == 404
    assert outside.json()["error"]["message"] == ghost.json()["error"]["message"]
    assert world.client.get(f"/farmers/{world.farmer1['id']}", headers=h).status_code == 200


def test_officer_inventory_is_ward_scoped(world):
    r = world.client.get("/inventory", headers=world.h(world.officer))
    ids = {i["id"] for i in r.json()["items"]}
    assert str(world.item1["id"]) in ids and str(world.item2["id"]) not in ids
    assert world.client.get(f"/inventory/{world.item2['id']}", headers=world.h(world.officer)).status_code == 404
    assert world.client.get("/inventory?ward_id=2", headers=world.h(world.officer)).status_code == 403


def test_officer_with_no_assignments_sees_nothing_rather_than_everything(world):
    lonely = uuid4()
    world.repo.roles[lonely] = "officer"
    assert world.client.get("/farmers", headers=world.h(lonely)).json()["total"] == 0
    assert world.client.get("/inventory", headers=world.h(lonely)).json()["total"] == 0


def test_officer_is_read_only(world):
    h = world.h(world.officer)
    body = {"plot_id": str(uuid4()), "produce_type_id": 1, "quantity": "5", "unit": "kg", "grade": "A",
            "expected_harvest_date": "2026-12-01", "asking_price_minor": 1000}
    assert world.client.post("/inventory", json=body, headers=h).status_code == 403
    assert world.client.patch(f"/inventory/{world.item1['id']}", json={"grade": "C"}, headers=h).status_code == 403
    assert world.client.delete(f"/inventory/{world.item1['id']}", headers=h).status_code == 403
    assert world.repo.items[world.item1["id"]]["grade"] == "A"


def test_admin_sees_everything_and_can_edit_any_item(world):
    h = world.h(world.admin)
    assert world.client.get("/farmers", headers=h).json()["total"] == 3
    assert world.client.get("/inventory", headers=h).json()["total"] == 3
    assert world.client.patch(f"/inventory/{world.item2['id']}", json={"grade": "B"}, headers=h).status_code == 200


def test_admin_cannot_call_farmer_only_endpoints(world):
    assert world.client.get("/farmers/me", headers=world.h(world.admin)).status_code == 403


def test_suspended_farmer_is_403(world):
    world.farmer1["status"] = "suspended"
    r = world.client.get("/farmers/me", headers=world.h(world.farmer1["user_id"]))
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_INACTIVE"


def test_farmer_cannot_change_status_or_role_via_patch_me(world):
    h = world.h(world.farmer1["user_id"])
    for field, value in (("status", "inactive"), ("role", "admin"), ("national_id", "99999999"), ("user_id", str(uuid4()))):
        r = world.client.patch("/farmers/me", json={field: value}, headers=h)
        assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN_FIELD", field
    assert world.repo.farmers[world.farmer1["id"]]["status"] == "active"
    assert world.repo.roles[world.farmer1["user_id"]] == "farmer"


def test_patch_me_updates_allowed_fields_and_plots(world):
    h = world.h(world.farmer1["user_id"])
    body = {"full_name": "Wanjiru W. Mwangi", "email": "W@Example.com",
            "plots": [{"name": "River plot", "ward_id": 3, "size_acres": "2.5"}]}
    r = world.client.patch("/farmers/me", json=body, headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["full_name"] == "Wanjiru W. Mwangi" and data["email"] == "w@example.com"
    assert {p["name"] for p in data["plots"]} == {"Home plot", "River plot"}


def test_patch_me_cannot_edit_someone_elses_plot(world):
    foreign = next(p for p in world.repo.plots.values() if p["farmer_id"] == world.farmer2["id"])
    r = world.client.patch("/farmers/me", headers=world.h(world.farmer1["user_id"]),
                           json={"plots": [{"id": str(foreign["id"]), "name": "Mine now", "ward_id": 1}]})
    assert r.status_code == 404
    assert foreign["name"] == "Home plot"


def test_patch_me_unknown_field_is_422(world):
    r = world.client.patch("/farmers/me", json={"favourite_colour": "green"}, headers=world.h(world.farmer1["user_id"]))
    assert r.status_code == 422


def test_farmers_list_pagination_and_filters(world):
    h = world.h(world.admin)
    page1 = world.client.get("/farmers?page=1&page_size=2", headers=h).json()
    assert len(page1["items"]) == 2 and page1["total"] == 3 and page1["has_more"] is True
    page2 = world.client.get("/farmers?page=2&page_size=2", headers=h).json()
    assert len(page2["items"]) == 1 and page2["has_more"] is False
    assert world.client.get("/farmers?ward_id=2", headers=h).json()["total"] == 1
    world.farmer3["status"] = "suspended"
    assert world.client.get("/farmers?status=suspended", headers=h).json()["total"] == 1
    assert world.client.get("/farmers?page_size=1000", headers=h).status_code == 422
