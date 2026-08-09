from fastapi import APIRouter

# APIRouter lets each file own its routes; main.py just collects them.
router = APIRouter()

@router.get("/health")
def health():
    # Liveness only — is the process up? No DB call on purpose.
    # A slow database shouldn't make a deploy platform think we're dead.
    return {"status": "ok"}