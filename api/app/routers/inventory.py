from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from ..deps import CurrentUser, get_repo, require_roles
from ..errors import Forbidden, NotFound, Unprocessable
from ..repository import ItemSold, Repository
from ..schemas import Grade, InventoryCreate, InventoryOut, InventoryPatch, InventoryStatus, Page

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _load_writable(item_id: UUID, user: CurrentUser, repo: Repository) -> dict:
    """Owner or admin only. Missing and not-yours both -> 404 (no existence leak)."""
    item = repo.get_inventory(item_id)
    if item is None or (user.role == "farmer" and item["farmer_id"] != user.farmer_id):
        raise NotFound("Inventory item not found")
    if item["status"] == "sold":
        raise ItemSold()  # the DB trigger enforces this too; checking early gives a clean 409
    return item


def _check_plot(plot_id: UUID, owner_farmer_id: UUID, repo: Repository) -> None:
    plot = repo.get_plot(plot_id)
    if plot is None or plot["farmer_id"] != owner_farmer_id:
        raise NotFound("Plot not found", code="PLOT_NOT_FOUND")
    if not plot["is_active"]:
        raise Unprocessable("That plot is inactive", details=[{"field": "plot_id", "message": "plot is inactive"}])


def _check_produce(produce_type_id: int, repo: Repository) -> None:
    if repo.get_produce_type(produce_type_id) is None:
        raise Unprocessable("Unknown produce type", details=[{"field": "produce_type_id", "message": "unknown produce type"}])


@router.post("", response_model=InventoryOut, status_code=status.HTTP_201_CREATED,
             summary="Create an item on one of the caller's plots (idempotent via client_request_id)")
def create_item(body: InventoryCreate, response: Response, user: CurrentUser = Depends(require_roles("farmer")),
                repo: Repository = Depends(get_repo)):
    _check_plot(body.plot_id, user.farmer_id, repo)  # type: ignore[arg-type]
    _check_produce(body.produce_type_id, repo)
    item, created = repo.create_inventory(user.farmer_id, body.model_dump())  # type: ignore[arg-type]
    if not created:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replay"] = "true"
    return item


@router.get("", response_model=Page[InventoryOut], summary="List items scoped by role, with filters")
def list_items(
    produce_type_id: int | None = Query(None, gt=0),
    grade: Grade | None = None,
    status: InventoryStatus | None = None,
    ward_id: int | None = Query(None, gt=0, description="officer/admin"),
    farmer_id: UUID | None = Query(None, description="officer/admin"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_roles("farmer", "officer", "admin")),
    repo: Repository = Depends(get_repo),
):
    scope_farmer: UUID | None = None
    scope_wards: list[int] | None = None
    if user.role == "farmer":
        scope_farmer = user.farmer_id
        if farmer_id is not None and farmer_id != user.farmer_id:
            raise Forbidden("You can only list your own inventory", code="FORBIDDEN_FILTER")
    elif user.role == "officer":
        if ward_id is not None and ward_id not in user.ward_ids:
            raise Forbidden("You are not assigned to that ward", code="WARD_NOT_ASSIGNED")
        scope_wards = user.ward_ids
    filters = {"produce_type_id": produce_type_id, "grade": grade.value if grade else None,
               "status": status.value if status else None, "ward_id": ward_id,
               "filter_farmer_id": farmer_id if user.role != "farmer" else None}
    items, total = repo.list_inventory(farmer_id=scope_farmer, ward_ids=scope_wards, filters=filters,
                                       page=page, page_size=page_size)
    return Page(items=items, page=page, page_size=page_size, total=total, has_more=page * page_size < total)


@router.get("/{item_id}", response_model=InventoryOut, summary="One item (scoped by role)")
def get_item(item_id: UUID, user: CurrentUser = Depends(require_roles("farmer", "officer", "admin")),
             repo: Repository = Depends(get_repo)):
    item = repo.get_inventory(item_id)
    visible = item is not None and (
        user.role == "admin"
        or (user.role == "farmer" and item["farmer_id"] == user.farmer_id)
        or (user.role == "officer" and item["ward_id"] in user.ward_ids))
    if not visible:
        raise NotFound("Inventory item not found")
    return item


@router.patch("/{item_id}", response_model=InventoryOut, summary="Update an item (owner/admin; blocked once sold)")
def patch_item(item_id: UUID, body: InventoryPatch, user: CurrentUser = Depends(require_roles("farmer", "admin")),
               repo: Repository = Depends(get_repo)):
    item = _load_writable(item_id, user, repo)
    fields = body.model_dump(exclude_unset=True)
    if "plot_id" in fields:
        _check_plot(fields["plot_id"], item["farmer_id"], repo)
    if "produce_type_id" in fields:
        _check_produce(fields["produce_type_id"], repo)
    return repo.update_inventory(item_id, fields)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Soft-delete (owner/admin; blocked once sold)")
def delete_item(item_id: UUID, user: CurrentUser = Depends(require_roles("farmer", "admin")),
                repo: Repository = Depends(get_repo)):
    _load_writable(item_id, user, repo)
    repo.soft_delete_inventory(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
