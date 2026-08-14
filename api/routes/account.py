"""Authenticated customer account: profile, addresses, order history."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from src.models.user import AddressInput, CustomerPrincipal, UserProfileUpdate
from src.plugins.customer_deps import require_customer_auth
from src.services.order_service import OrderService
from src.services.user_service import ProfileConflictError, UserService

router = APIRouter()


def _serialize_user(user) -> dict:
    return {
        "id": user.id,
        "phone": user.phone,
        "name": user.name,
        "email": user.email,
        "addresses": [a.model_dump() for a in user.addresses],
    }


@router.get("/api/account/me")
async def get_me(principal: CustomerPrincipal = Depends(require_customer_auth)):
    user = await UserService().get_by_id(principal.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    return _serialize_user(user)


@router.patch("/api/account/me")
async def update_me(
    payload: UserProfileUpdate, principal: CustomerPrincipal = Depends(require_customer_auth)
):
    try:
        user = await UserService().update_profile(principal.user_id, payload)
    except ProfileConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    return _serialize_user(user)


@router.get("/api/account/addresses")
async def list_addresses(principal: CustomerPrincipal = Depends(require_customer_auth)):
    user = await UserService().get_by_id(principal.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    return [a.model_dump() for a in user.addresses]


@router.post("/api/account/addresses")
async def add_address(
    payload: AddressInput, principal: CustomerPrincipal = Depends(require_customer_auth)
):
    user = await UserService().add_address(principal.user_id, payload)
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    return [a.model_dump() for a in user.addresses]


@router.patch("/api/account/addresses/{address_id}")
async def update_address(
    address_id: str,
    payload: AddressInput,
    principal: CustomerPrincipal = Depends(require_customer_auth),
):
    user = await UserService().update_address(principal.user_id, address_id, payload)
    if not user:
        raise HTTPException(status_code=404, detail="Address not found")
    return [a.model_dump() for a in user.addresses]


@router.delete("/api/account/addresses/{address_id}")
async def delete_address(
    address_id: str, principal: CustomerPrincipal = Depends(require_customer_auth)
):
    user = await UserService().delete_address(principal.user_id, address_id)
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    return [a.model_dump() for a in user.addresses]


@router.get("/api/account/orders")
async def list_my_orders(principal: CustomerPrincipal = Depends(require_customer_auth)):
    """Merges user_id-, phone-, and email-matched orders. user_id is the
    strongest match (order placed while this exact session was verified at
    checkout); phone/email are the fallback for guest checkouts placed
    under either identifier before the owner ever logged in.
    """
    order_service = OrderService()
    by_user_id = await order_service.list_by_user_id(principal.user_id)
    by_phone = await order_service.list_by_phone(principal.phone) if principal.phone else []
    by_email = await order_service.list_by_email(principal.email) if principal.email else []

    seen: set[str] = set()
    merged = []
    for order in by_user_id + by_phone + by_email:
        if order.order_id in seen:
            continue
        seen.add(order.order_id)
        merged.append(order)
    merged.sort(key=lambda o: o.created_at, reverse=True)

    # exclude "id" (aliased "_id"): it's a raw bson ObjectId with no
    # pydantic-v2 serializer registered (only a validator — see
    # PyObjectId in src/models/shipping_address.py), so jsonable_encoder
    # can't serialize it and the whole response 500s. The frontend's
    # CustomerOrder type never reads it, so just drop it rather than fix
    # every model that reuses PyObjectId.
    return [order.model_dump(by_alias=True, exclude={"id"}) for order in merged]
