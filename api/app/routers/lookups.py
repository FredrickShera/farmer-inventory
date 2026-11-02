from fastapi import APIRouter, Depends

from ..deps import CurrentUser, get_current_user, get_repo
from ..repository import Repository
from ..schemas import LocationOut, ProduceTypeOut

router = APIRouter(tags=["lookups"])


@router.get("/locations", response_model=list[LocationOut], summary="County / sub-county / ward lookup (public)")
def locations(repo: Repository = Depends(get_repo)):
    # Public on purpose: the Register screen needs it before the user has an account.
    return repo.list_locations()


@router.get("/produce-types", response_model=list[ProduceTypeOut], summary="Active produce catalogue")
def produce_types(_: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repo)):
    return repo.list_produce_types()
