from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from fin import categories_store
from fin.database import get_db
from fin.models.user import MOCK_USER_ID
from fin.repositories.ledger_sqlite import LedgerSQLiteRepository
from fin.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate

router = APIRouter(prefix="/api")


@router.get("/categories", response_model=list[CategoryResponse])
def list_categories():
    """Return built-ins (from code) merged with user-added categories (from JSON)."""
    return categories_store.list_all()


@router.post("/categories", response_model=CategoryResponse, status_code=201)
def create_category(data: CategoryCreate):
    try:
        return categories_store.add(
            direction=data.direction,
            name=data.name.strip(),
            bg_color=data.bg_color,
            text_color=data.text_color,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.put("/categories/{id}", response_model=CategoryResponse)
def update_category(id: str, data: CategoryUpdate, db: Session = Depends(get_db)):
    """Update a custom category. If the name changes, the new name propagates to
    every ledger row that referenced the old name so historical entries stay
    grouped under the renamed category.
    """
    new_name = data.name.strip() if data.name else None
    old = categories_store.find(id) if new_name else None
    try:
        updated = categories_store.update(
            id,
            name=new_name,
            bg_color=data.bg_color,
            text_color=data.text_color,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail="category not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    if old and new_name and old["name"] != new_name:
        LedgerSQLiteRepository(db).rename_category(MOCK_USER_ID, old["name"], new_name)
    return updated


@router.delete("/categories/{id}", status_code=204)
def delete_category(id: str):
    try:
        categories_store.delete(id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail="category not found")
    return Response(status_code=204)
