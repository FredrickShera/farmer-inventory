"""In-memory stand-ins so the API test-suite needs no Supabase and no Postgres.

The fakes hold DATA only. All authorisation decisions live in app/deps.py and the routers,
which is exactly what these tests exercise. (The real SQL is exercised by
tests/test_db_integration.py when TEST_DATABASE_URL is set.)"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

from app.auth_gateway import Session
from app.errors import Conflict, NotFound, Unauthorized
from app.repository import ItemSold

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)

WARDS = {
    1: ("Kitisuru", "Westlands", "Nairobi"),
    2: ("Njoro", "Njoro", "Nakuru"),
    3: ("Township", "Thika Town", "Kiambu"),
}
PRODUCE = {1: "Maize", 2: "Tomatoes"}


class FakeRepo:
    def __init__(self) -> None:
        self.roles: dict[UUID, str] = {}
        self.officer_wards: dict[UUID, list[int]] = {}
        self.farmers: dict[UUID, dict[str, Any]] = {}
        self.plots: dict[UUID, dict[str, Any]] = {}
        self.items: dict[UUID, dict[str, Any]] = {}
        self.auth_emails: dict[str, str] = {}
        self.fail_create_farmer = False

    # ---- builders used by the fixtures
    def add_farmer(self, user_id: UUID, name: str, ward_id: int, *, national_id: str, phone: str, status: str = "active") -> dict:
        fid = uuid4()
        self.roles[user_id] = "farmer"
        self.farmers[fid] = dict(id=fid, user_id=user_id, full_name=name, national_id=national_id, phone=phone, email=None,
                                 ward_id=ward_id, status=status, created_at=NOW, updated_at=NOW)
        self.add_plot(fid, "Home plot", ward_id)
        return self.farmers[fid]

    def add_plot(self, farmer_id: UUID, name: str, ward_id: int) -> dict:
        pid = uuid4()
        self.plots[pid] = dict(id=pid, farmer_id=farmer_id, name=name, ward_id=ward_id, size_acres=None, is_active=True)
        return self.plots[pid]

    def add_item(self, farmer_id: UUID, plot_id: UUID, *, status: str = "available", quantity: str = "10.00",
                 client_request_id: UUID | None = None, produce_type_id: int = 1) -> dict:
        iid = uuid4()
        self.items[iid] = dict(id=iid, farmer_id=farmer_id, plot_id=plot_id, produce_type_id=produce_type_id,
                               quantity=__import__("decimal").Decimal(quantity), unit="kg", grade="A", status=status,
                               expected_harvest_date=NOW.date(), asking_price_minor=5000, currency="KES",
                               sold_at=NOW if status == "sold" else None, created_at=NOW, updated_at=NOW,
                               client_request_id=client_request_id, deleted_at=None)
        return self.items[iid]

    # ---- views
    def _plot_out(self, p: dict) -> dict:
        w, sc, c = WARDS[p["ward_id"]]
        return {**p, "ward": w, "sub_county": sc, "county": c}

    def _farmer_out(self, f: dict) -> dict:
        w, sc, c = WARDS[f["ward_id"]]
        plots = [self._plot_out(p) for p in self.plots.values() if p["farmer_id"] == f["id"]]
        return {**f, "ward": w, "sub_county": sc, "county": c, "plots": plots}

    def _item_out(self, i: dict) -> dict:
        p, f = self.plots[i["plot_id"]], self.farmers[i["farmer_id"]]
        return {**i, "farmer_name": f["full_name"], "plot_name": p["name"], "ward_id": p["ward_id"], "ward": WARDS[p["ward_id"]][0],
                "produce_type": PRODUCE[i["produce_type_id"]]}

    def _farmer_in(self, f: dict, wards: list[int]) -> bool:
        return f["ward_id"] in wards or any(p["ward_id"] in wards for p in self.plots.values() if p["farmer_id"] == f["id"])

    # ---- Repository
    def get_role(self, user_id): return self.roles.get(user_id)
    def officer_ward_ids(self, user_id): return list(self.officer_wards.get(user_id, []))

    def get_farmer_by_user(self, user_id):
        f = next((f for f in self.farmers.values() if f["user_id"] == user_id), None)
        return self._farmer_out(f) if f else None

    def auth_email_for_phone(self, phone): return self.auth_emails.get(phone)
    def list_locations(self): return [dict(ward_id=k, ward=v[0], sub_county_id=k, sub_county=v[1], county_id=k, county=v[2]) for k, v in WARDS.items()]
    def ward_exists(self, ward_id): return ward_id in WARDS
    def list_produce_types(self): return [dict(id=k, name=v, category="other") for k, v in PRODUCE.items()]
    def get_produce_type(self, pid): return dict(id=pid, name=PRODUCE[pid], category="other") if pid in PRODUCE else None

    def find_conflicts(self, national_id, phone):
        out = []
        if any(f["national_id"] == national_id for f in self.farmers.values()): out.append("national_id")
        if any(f["phone"] == phone for f in self.farmers.values()): out.append("phone")
        return out

    def create_farmer(self, user_id, data, plot_name):
        if self.fail_create_farmer:
            raise RuntimeError("simulated database failure")
        f = self.add_farmer(user_id, data["full_name"], data["ward_id"], national_id=data["national_id"], phone=data["phone"])
        f["email"] = data["email"]
        next(p for p in self.plots.values() if p["farmer_id"] == f["id"])["name"] = plot_name
        return self._farmer_out(f)

    def get_farmer(self, farmer_id, ward_ids=None):
        f = self.farmers.get(farmer_id)
        if f is None or (ward_ids is not None and not self._farmer_in(f, ward_ids)):
            return None
        return self._farmer_out(f)

    def update_farmer(self, farmer_id, fields, plots):
        self.farmers[farmer_id].update(fields)
        for p in plots or []:
            if p.get("id"):
                existing = self.plots.get(p["id"])
                if not existing or existing["farmer_id"] != farmer_id:
                    raise NotFound("Plot not found", code="PLOT_NOT_FOUND")
                existing.update({k: p[k] for k in ("name", "ward_id", "size_acres", "is_active")})
            else:
                self.add_plot(farmer_id, p["name"], p["ward_id"])
        return self._farmer_out(self.farmers[farmer_id])

    def list_farmers(self, *, ward_ids, ward_id, status, page, page_size):
        rows = [f for f in self.farmers.values()
                if (ward_ids is None or self._farmer_in(f, ward_ids))
                and (ward_id is None or self._farmer_in(f, [ward_id]))
                and (status is None or f["status"] == status)]
        rows.sort(key=lambda f: (f["full_name"], str(f["id"])))
        return [self._farmer_out(f) for f in rows[(page - 1) * page_size: page * page_size]], len(rows)

    def get_plot(self, plot_id):
        p = self.plots.get(plot_id)
        return self._plot_out(p) if p else None

    def create_inventory(self, farmer_id, data):
        crid = data.get("client_request_id")
        if crid:
            prior = next((i for i in self.items.values() if i["farmer_id"] == farmer_id and i["client_request_id"] == crid), None)
            if prior:
                return self._item_out(prior), False
        item = self.add_item(farmer_id, data["plot_id"], quantity=str(data["quantity"]), client_request_id=crid,
                             produce_type_id=data["produce_type_id"])
        item.update({k: data[k] for k in ("unit", "grade", "expected_harvest_date", "asking_price_minor")})
        return self._item_out(item), True

    def get_inventory(self, item_id):
        i = self.items.get(item_id)
        return self._item_out(i) if i and i["deleted_at"] is None else None

    def list_inventory(self, *, farmer_id, ward_ids, filters, page, page_size):
        out = []
        for i in self.items.values():
            if i["deleted_at"] is not None: continue
            o = self._item_out(i)
            if farmer_id is not None and i["farmer_id"] != farmer_id: continue
            if ward_ids is not None and o["ward_id"] not in ward_ids: continue
            if filters.get("produce_type_id") and i["produce_type_id"] != filters["produce_type_id"]: continue
            if filters.get("grade") and i["grade"] != filters["grade"]: continue
            if filters.get("status") and i["status"] != filters["status"]: continue
            if filters.get("ward_id") and o["ward_id"] != filters["ward_id"]: continue
            if filters.get("filter_farmer_id") and i["farmer_id"] != filters["filter_farmer_id"]: continue
            out.append(o)
        out.sort(key=lambda r: str(r["id"]))
        return out[(page - 1) * page_size: page * page_size], len(out)

    def update_inventory(self, item_id, fields):
        item = self.items[item_id]
        # NOTE: deliberately does NOT mimic the DB sold-trigger, so these tests prove the API layer blocks on its own.
        item.update(fields)
        return self._item_out(item)

    def soft_delete_inventory(self, item_id):
        self.items[item_id]["deleted_at"] = NOW


class FakeGateway:
    """Records calls; mints tokens with the same helper the tests use."""

    def __init__(self, mint: Callable[[UUID], str]) -> None:
        self._mint = mint
        self.users: dict[str, tuple[UUID, str]] = {}   # email -> (id, password)
        self.deleted: list[UUID] = []
        self.signed_out: list[str] = []
        self.refresh_tokens: dict[str, UUID] = {}

    def _session(self, uid: UUID) -> Session:
        rt = f"refresh-{uuid4().hex}"
        self.refresh_tokens[rt] = uid
        return Session(self._mint(uid), rt, 3600, int(NOW.timestamp()) + 3600, uid)

    def create_user(self, *, email, password, full_name):
        if email in self.users: raise Conflict("exists", code="ACCOUNT_EXISTS")
        uid = uuid4(); self.users[email] = (uid, password); return uid

    def delete_user(self, user_id):
        self.deleted.append(user_id)
        self.users = {e: v for e, v in self.users.items() if v[0] != user_id}

    def sign_in(self, *, email, password):
        rec = self.users.get(email)
        if not rec or rec[1] != password: raise Unauthorized("Invalid credentials", code="INVALID_CREDENTIALS")
        return self._session(rec[0])

    def refresh(self, refresh_token):
        uid = self.refresh_tokens.pop(refresh_token, None)
        if uid is None: raise Unauthorized("Session expired", code="REFRESH_FAILED")
        return self._session(uid)

    def sign_out(self, access_token): self.signed_out.append(access_token)
