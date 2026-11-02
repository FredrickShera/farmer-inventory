from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ..deps import CurrentUser, get_repo, require_roles
from ..errors import Forbidden, NotFound, Unprocessable
from ..repository import Repository
from ..schemas import FarmerOut, FarmerPatch, FarmerStatus, Page

router = APIRouter(prefix="/farmers", tags=["farmers"])


@router.get("/me", response_model=FarmerOut, summary="The caller's profile and plots")
def get_me(user: CurrentUser = Depends(require_roles("farmer")), repo: Repository = Depends(get_repo)):
    return repo.get_farmer_by_user(user.user_id)


@router.patch("/me", response_model=FarmerOut, summary="Update name, contact and plots (never status or role)")
def patch_me(body: FarmerPatch, user: CurrentUser = Depends(require_roles("farmer")), repo: Repository = Depends(get_repo)):
    fields = body.model_dump(exclude_unset=True, exclude={"plots"})
    if "full_name" in fields and fields["full_name"] is None:
        raise Unprocessable("full_name cannot be null", details=[{"field": "full_name", "message": "cannot be null"}])
    if "phone" in fields and fields["phone"] is None:
        raise Unprocessable("phone cannot be null", details=[{"field": "phone", "message": "cannot be null"}])
    plots = [p.model_dump() for p in body.plots] if body.plots is not None else None
    for p in plots or []:
        if not repo.ward_exists(p["ward_id"]):
            raise Unprocessable("Invalid ward", details=[{"field": "plots.ward_id", "message": "unknown ward"}])
    return repo.update_farmer(user.farmer_id, fields, plots)  # type: ignore[arg-type]


@router.get("", response_model=Page[FarmerOut], summary="Paginated farmers (officer: own wards only)")
def list_farmers(
    ward_id: int | None = Query(None, gt=0),
    status: FarmerStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_roles("officer", "admin")),
    repo: Repository = Depends(get_repo),
):
    scope: list[int] | None = None
    if user.role == "officer":
        if ward_id is not None and ward_id not in user.ward_ids:
            raise Forbidden("You are not assigned to that ward", code="WARD_NOT_ASSIGNED")
        scope = user.ward_ids  # an officer with no assignments sees nothing (empty list), never everything
    items, total = repo.list_farmers(ward_ids=scope, ward_id=ward_id, status=status.value if status else None,
                                     page=page, page_size=page_size)
    return Page(items=items, page=page, page_size=page_size, total=total, has_more=page * page_size < total)


@router.get("/{farmer_id}", response_model=FarmerOut, summary="One farmer (officer: own wards only)")
def get_farmer(farmer_id: UUID, user: CurrentUser = Depends(require_roles("officer", "admin")),
               repo: Repository = Depends(get_repo)):
    farmer = repo.get_farmer(farmer_id, user.ward_ids if user.role == "officer" else None)
    if farmer is None:
        # Identical response for "does not exist" and "not in your ward": existence is never leaked.
        raise NotFound("Farmer not found")
    return farmer
