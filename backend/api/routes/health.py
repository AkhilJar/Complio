from fastapi import APIRouter

router = APIRouter()


#returns status for uptime checks
@router.get("/health")
def health_check():
    return {"status": "ok"}