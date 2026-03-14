from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "service": "ready"}
