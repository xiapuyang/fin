from fastapi import APIRouter, HTTPException, Response

from fin import categories_store
from fin.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate

router = APIRouter(prefix="/api")


@router.get("/categories", response_model=list[CategoryResponse])
def list_categories():
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
def update_category(id: str, data: CategoryUpdate):
    """Rename / recolor a custom category. Ledger rows need no update since
    they reference categories by ID.
    """
    try:
        return categories_store.update(
            id,
            name=data.name.strip() if data.name else None,
            bg_color=data.bg_color,
            text_color=data.text_color,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail="category not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.delete("/categories/{id}", status_code=204)
def delete_category(id: str):
    try:
        categories_store.delete(id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail="category not found")
    return Response(status_code=204)
