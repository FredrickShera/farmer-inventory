"""Data access. Every query is parameterised (psycopg binds values server-side). The few
dynamic pieces — WHERE clauses and UPDATE column lists — are assembled only from fixed
string fragments and a whitelist of column names via psycopg.sql.Identifier, never from
request text.

The API connects with the database owner/service credentials, which BYPASS RLS. That is
deliberate: authorisation is enforced here in the service layer (deps.py + routers) AND by
RLS for any client that talks to Supabase directly. The two are kept equivalent and the
DB integration test (tests/test_db_integration.py) checks they agree.
"""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

import psycopg
from psycopg import errors as pgerr
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .errors import Conflict, NotFound, Unprocessable

Row = dict[str, Any]


class ItemSold(Conflict):
    code = "ITEM_SOLD"

    def __init__(self) -> None:
        super().__init__("This inventory item is sold and can no longer be changed")


class Repository(Protocol):
    # identity / roles
    def get_role(self, user_id: UUID) -> str | None: ...
    def officer_ward_ids(self, user_id: UUID) -> list[int]: ...
    def get_farmer_by_user(self, user_id: UUID) -> Row | None: ...
    def auth_email_for_phone(self, phone: str) -> str | None: ...
    # lookups
    def list_locations(self) -> list[Row]: ...
    def ward_exists(self, ward_id: int) -> bool: ...
    def list_produce_types(self) -> list[Row]: ...
    def get_produce_type(self, produce_type_id: int) -> Row | None: ...
    # farmers
    def find_conflicts(self, national_id: str, phone: str) -> list[str]: ...
    def create_farmer(self, user_id: UUID, data: Row, plot_name: str) -> Row: ...
    def get_farmer(self, farmer_id: UUID, ward_ids: list[int] | None = None) -> Row | None: ...
    def update_farmer(self, farmer_id: UUID, fields: Row, plots: list[Row] | None) -> Row: ...
    def list_farmers(self, *, ward_ids: list[int] | None, ward_id: int | None, status: str | None,
                     page: int, page_size: int) -> tuple[list[Row], int]: ...
    # plots / inventory
    def get_plot(self, plot_id: UUID) -> Row | None: ...
    def create_inventory(self, farmer_id: UUID, data: Row) -> tuple[Row, bool]: ...
    def get_inventory(self, item_id: UUID) -> Row | None: ...
    def list_inventory(self, *, farmer_id: UUID | None, ward_ids: list[int] | None, filters: Row,
                       page: int, page_size: int) -> tuple[list[Row], int]: ...
    def update_inventory(self, item_id: UUID, fields: Row) -> Row: ...
    def soft_delete_inventory(self, item_id: UUID) -> None: ...


_FARMER_SQL = """
select f.id, f.user_id, f.full_name, f.national_id, f.phone, f.email, f.ward_id, f.status::text as status,
       f.created_at, f.updated_at, w.name as ward, sc.name as sub_county, c.name as county
from public.farmers f
join public.wards w on w.id = f.ward_id
join public.sub_counties sc on sc.id = w.sub_county_id
join public.counties c on c.id = sc.county_id
"""

_PLOT_SQL = """
select p.id, p.farmer_id, p.name, p.ward_id, p.size_acres, p.is_active,
       w.name as ward, sc.name as sub_county, c.name as county
from public.plots p
join public.wards w on w.id = p.ward_id
join public.sub_counties sc on sc.id = w.sub_county_id
join public.counties c on c.id = sc.county_id
"""

_INV_SQL = """
select i.id, i.farmer_id, f.full_name as farmer_name, i.plot_id, p.name as plot_name, p.ward_id, w.name as ward,
       i.produce_type_id, pt.name as produce_type, i.quantity, i.unit::text as unit, i.grade::text as grade,
       i.status::text as status, i.expected_harvest_date, i.asking_price_minor, i.currency, i.sold_at,
       i.created_at, i.updated_at
from public.inventory_items i
join public.farmers f on f.id = i.farmer_id
join public.plots p on p.id = i.plot_id
join public.wards w on w.id = p.ward_id
join public.produce_types pt on pt.id = i.produce_type_id
"""


def _farmer_in_wards(param: str) -> str:
    # an officer covers a farmer whose home ward OR any plot ward is assigned (mirrors officer_can_see_farmer())
    return (f"(f.ward_id = any(%({param})s::int[]) or exists (select 1 from public.plots sp "
            f"where sp.farmer_id = f.id and sp.ward_id = any(%({param})s::int[])))")


_UNIQUE_FIELD = {"farmers_national_id_key": "national_id", "farmers_phone_key": "phone",
                 "plots_farmer_name_key": "plot name", "farmers_user_id_key": "account"}


def _translate(exc: psycopg.Error) -> Exception:
    """Map database errors onto API errors."""
    if isinstance(exc, pgerr.ObjectNotInPrerequisiteState):  # SQLSTATE 55000 from the sold-item trigger
        return ItemSold()
    if isinstance(exc, pgerr.UniqueViolation):
        field = _UNIQUE_FIELD.get(exc.diag.constraint_name or "", "value")
        return Conflict(f"That {field} is already in use", code="DUPLICATE", details=[{"field": field, "message": "already in use"}])
    if isinstance(exc, pgerr.ForeignKeyViolation):
        return Unprocessable("A referenced record does not exist or is not allowed")
    if isinstance(exc, pgerr.CheckViolation):
        return Unprocessable("A value violates a data rule", details=[{"field": exc.diag.constraint_name or "value", "message": "violates a data rule"}])
    return exc


class PostgresRepository:
    def __init__(self, dsn: str, max_size: int = 10):
        # prepare_threshold=None: Supabase's transaction pooler (port 6543) does not support prepared statements.
        self.pool = ConnectionPool(dsn, min_size=1, max_size=max_size, open=False,
                                   kwargs={"row_factory": dict_row, "prepare_threshold": None})

    def open(self) -> None:
        self.pool.open(wait=True, timeout=15)

    def close(self) -> None:
        self.pool.close()

    # ------------------------------------------------------------ helpers
    def _one(self, query: str | sql.Composable, params: Any = None) -> Row | None:
        with self.pool.connection() as conn:
            return conn.execute(query, params).fetchone()

    def _all(self, query: str | sql.Composable, params: Any = None) -> list[Row]:
        with self.pool.connection() as conn:
            return conn.execute(query, params).fetchall()

    def _attach_plots(self, farmers: list[Row]) -> list[Row]:
        if not farmers:
            return farmers
        plots = self._all(_PLOT_SQL + " where p.farmer_id = any(%s::uuid[]) order by p.created_at, p.id",
                          ([f["id"] for f in farmers],))
        by_farmer: dict[UUID, list[Row]] = {}
        for p in plots:
            by_farmer.setdefault(p["farmer_id"], []).append(p)
        for f in farmers:
            f["plots"] = by_farmer.get(f["id"], [])
        return farmers

    # ------------------------------------------------------------ identity
    def get_role(self, user_id: UUID) -> str | None:
        row = self._one("select role::text as role from public.user_roles where user_id = %s", (user_id,))
        return row["role"] if row else None

    def officer_ward_ids(self, user_id: UUID) -> list[int]:
        rows = self._all("select ward_id from public.officer_assignments where officer_id = %s order by ward_id", (user_id,))
        return [r["ward_id"] for r in rows]

    def get_farmer_by_user(self, user_id: UUID) -> Row | None:
        row = self._one(_FARMER_SQL + " where f.user_id = %s", (user_id,))
        return self._attach_plots([row])[0] if row else None

    def auth_email_for_phone(self, phone: str) -> str | None:
        row = self._one("select u.email from public.farmers f join auth.users u on u.id = f.user_id where f.phone = %s", (phone,))
        return row["email"] if row else None

    # ------------------------------------------------------------ lookups
    def list_locations(self) -> list[Row]:
        return self._all("select ward_id, ward, sub_county_id, sub_county, county_id, county "
                         "from public.locations order by county, sub_county, ward")

    def ward_exists(self, ward_id: int) -> bool:
        return self._one("select 1 as ok from public.wards where id = %s", (ward_id,)) is not None

    def list_produce_types(self) -> list[Row]:
        return self._all("select id, name, category from public.produce_types where is_active order by name")

    def get_produce_type(self, produce_type_id: int) -> Row | None:
        return self._one("select id, name, category from public.produce_types where id = %s and is_active", (produce_type_id,))

    # ------------------------------------------------------------ farmers
    def find_conflicts(self, national_id: str, phone: str) -> list[str]:
        row = self._one("select bool_or(national_id = %s) as nid, bool_or(phone = %s) as ph "
                        "from public.farmers where national_id = %s or phone = %s", (national_id, phone, national_id, phone))
        out = []
        if row and row["nid"]:
            out.append("national_id")
        if row and row["ph"]:
            out.append("phone")
        return out

    def create_farmer(self, user_id: UUID, data: Row, plot_name: str) -> Row:
        # One transaction: role + farmer + first plot succeed or fail together.
        with self.pool.connection() as conn:
            try:
                conn.execute("insert into public.user_roles (user_id, role) values (%s, 'farmer')", (user_id,))
                farmer = conn.execute(
                    "insert into public.farmers (user_id, full_name, national_id, phone, email, ward_id) "
                    "values (%(user_id)s, %(full_name)s, %(national_id)s, %(phone)s, %(email)s, %(ward_id)s) returning id",
                    {**data, "user_id": user_id}).fetchone()
                conn.execute("insert into public.plots (farmer_id, name, ward_id) values (%s, %s, %s)",
                             (farmer["id"], plot_name, data["ward_id"]))
            except psycopg.Error as exc:
                raise _translate(exc) from exc
        return self.get_farmer(farmer["id"])  # type: ignore[return-value]

    def get_farmer(self, farmer_id: UUID, ward_ids: list[int] | None = None) -> Row | None:
        query, params = _FARMER_SQL + " where f.id = %(id)s", {"id": farmer_id}
        if ward_ids is not None:
            query += " and " + _farmer_in_wards("wards")
            params["wards"] = ward_ids
        row = self._one(query, params)
        return self._attach_plots([row])[0] if row else None

    _FARMER_COLUMNS = ("full_name", "phone", "email")
    _PLOT_COLUMNS = ("name", "ward_id", "size_acres", "is_active")

    def update_farmer(self, farmer_id: UUID, fields: Row, plots: list[Row] | None) -> Row:
        with self.pool.connection() as conn:
            try:
                cols = [c for c in self._FARMER_COLUMNS if c in fields]
                if cols:
                    assignments = sql.SQL(", ").join(sql.SQL("{} = {}").format(sql.Identifier(c), sql.Placeholder(c)) for c in cols)
                    conn.execute(sql.SQL("update public.farmers set {} where id = {}").format(assignments, sql.Placeholder("_id")),
                                 {**{c: fields[c] for c in cols}, "_id": farmer_id})
                for plot in plots or []:
                    vals = {c: plot.get(c) for c in self._PLOT_COLUMNS}
                    if plot.get("id"):
                        updated = conn.execute(
                            "update public.plots set name = %(name)s, ward_id = %(ward_id)s, size_acres = %(size_acres)s, "
                            "is_active = %(is_active)s where id = %(id)s and farmer_id = %(farmer_id)s returning id",
                            {**vals, "id": plot["id"], "farmer_id": farmer_id}).fetchone()
                        if not updated:  # not yours or not existing: same answer, no leak
                            raise NotFound("Plot not found", code="PLOT_NOT_FOUND")
                    else:
                        conn.execute("insert into public.plots (farmer_id, name, ward_id, size_acres, is_active) "
                                     "values (%(farmer_id)s, %(name)s, %(ward_id)s, %(size_acres)s, %(is_active)s)",
                                     {**vals, "farmer_id": farmer_id})
            except psycopg.Error as exc:
                raise _translate(exc) from exc
        return self.get_farmer(farmer_id)  # type: ignore[return-value]

    def list_farmers(self, *, ward_ids, ward_id, status, page, page_size):
        where, params = ["true"], {}
        if ward_ids is not None:
            where.append(_farmer_in_wards("scope_wards"))
            params["scope_wards"] = ward_ids
        if ward_id is not None:
            where.append(_farmer_in_wards("filter_wards"))
            params["filter_wards"] = [ward_id]
        if status is not None:
            where.append("f.status = %(status)s::public.farmer_status")
            params["status"] = status
        clause = " where " + " and ".join(where)
        total = self._one("select count(*) as n from public.farmers f" + clause, params)["n"]  # type: ignore[index]
        rows = self._all(_FARMER_SQL + clause + " order by f.full_name, f.id limit %(limit)s offset %(offset)s",
                         {**params, "limit": page_size, "offset": (page - 1) * page_size})
        return self._attach_plots(rows), total

    # ------------------------------------------------------------ plots / inventory
    def get_plot(self, plot_id: UUID) -> Row | None:
        return self._one(_PLOT_SQL + " where p.id = %s", (plot_id,))

    def create_inventory(self, farmer_id: UUID, data: Row) -> tuple[Row, bool]:
        with self.pool.connection() as conn:
            try:
                row = conn.execute(
                    "insert into public.inventory_items (farmer_id, plot_id, produce_type_id, quantity, unit, grade, "
                    "expected_harvest_date, asking_price_minor, client_request_id) "
                    "values (%(farmer_id)s, %(plot_id)s, %(produce_type_id)s, %(quantity)s, %(unit)s, %(grade)s, "
                    "%(expected_harvest_date)s, %(asking_price_minor)s, %(client_request_id)s) "
                    "on conflict (farmer_id, client_request_id) where client_request_id is not null do nothing returning id",
                    {**data, "farmer_id": farmer_id}).fetchone()
                created = row is not None
                if row is None:  # replay of an earlier request: return the original record
                    row = conn.execute("select id from public.inventory_items where farmer_id = %s and client_request_id = %s",
                                       (farmer_id, data["client_request_id"])).fetchone()
            except psycopg.Error as exc:
                raise _translate(exc) from exc
        return self.get_inventory(row["id"]), created  # type: ignore[return-value]

    def get_inventory(self, item_id: UUID) -> Row | None:
        return self._one(_INV_SQL + " where i.id = %s and i.deleted_at is null", (item_id,))

    def list_inventory(self, *, farmer_id, ward_ids, filters, page, page_size):
        where, params = ["i.deleted_at is null"], {}
        if farmer_id is not None:
            where.append("i.farmer_id = %(farmer_id)s")
            params["farmer_id"] = farmer_id
        if ward_ids is not None:
            where.append("p.ward_id = any(%(scope_wards)s::int[])")
            params["scope_wards"] = ward_ids
        fixed = {"produce_type_id": "i.produce_type_id = %(produce_type_id)s",
                 "grade": "i.grade = %(grade)s::public.quality_grade",
                 "status": "i.status = %(status)s::public.inventory_status",
                 "ward_id": "p.ward_id = %(ward_id)s",
                 "filter_farmer_id": "i.farmer_id = %(filter_farmer_id)s"}
        for key, fragment in fixed.items():
            if filters.get(key) is not None:
                where.append(fragment)
                params[key] = filters[key]
        clause = " where " + " and ".join(where)
        count_sql = ("select count(*) as n from public.inventory_items i join public.plots p on p.id = i.plot_id" + clause)
        total = self._one(count_sql, params)["n"]  # type: ignore[index]
        rows = self._all(_INV_SQL + clause + " order by i.created_at desc, i.id limit %(limit)s offset %(offset)s",
                         {**params, "limit": page_size, "offset": (page - 1) * page_size})
        return rows, total

    _INV_COLUMNS = ("plot_id", "produce_type_id", "quantity", "unit", "grade", "status",
                    "expected_harvest_date", "asking_price_minor")

    def update_inventory(self, item_id: UUID, fields: Row) -> Row:
        cols = [c for c in self._INV_COLUMNS if c in fields]
        assignments = sql.SQL(", ").join(sql.SQL("{} = {}").format(sql.Identifier(c), sql.Placeholder(c)) for c in cols)
        query = sql.SQL("update public.inventory_items set {} where id = {} and deleted_at is null returning id").format(
            assignments, sql.Placeholder("_id"))
        with self.pool.connection() as conn:
            try:
                row = conn.execute(query, {**{c: fields[c] for c in cols}, "_id": item_id}).fetchone()
            except psycopg.Error as exc:
                raise _translate(exc) from exc
        if row is None:
            raise NotFound("Inventory item not found")
        return self.get_inventory(item_id)  # type: ignore[return-value]

    def soft_delete_inventory(self, item_id: UUID) -> None:
        with self.pool.connection() as conn:
            try:
                row = conn.execute("update public.inventory_items set deleted_at = now() "
                                   "where id = %s and deleted_at is null returning id", (item_id,)).fetchone()
            except psycopg.Error as exc:
                raise _translate(exc) from exc
        if row is None:
            raise NotFound("Inventory item not found")
