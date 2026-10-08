"""Frozen HTTP constructor from 4491be2; no routes or lifespan are started."""
app = FastAPI(title="VantaLine Local Inspection Service", docs_url=None, redoc_url=None, openapi_url=None)
from .storage.artifacts.admission import UploadAdmission
if os.environ.get("VANTALINE_FILE_STORE", "local") != "local":
    app.add_middleware(UploadAdmission)
app.add_middleware(GZipMiddleware, minimum_size=1024)

LOCAL_CORS_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$"
LAN_CORS_ORIGIN_REGEX = (
    r"^https?://("
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|"
    r"[^/:]+\.local"
    r")(?::\d+)?$"
)
CORS_ORIGIN_REGEX = os.environ.get(
    "INSPECTION_CORS_ORIGIN_REGEX",
    LAN_CORS_ORIGIN_REGEX if os.environ.get("INSPECTION_ENABLE_LAN_CORS") == "1" else LOCAL_CORS_ORIGIN_REGEX,
)
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("INSPECTION_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
