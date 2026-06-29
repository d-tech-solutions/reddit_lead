from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import logging
import time

from app.config import settings
from app.logging_config import setup_logging
from app.routers import auth, onboarding, leads, admin, system

# Initialize global logging setup
setup_logging()
logger = logging.getLogger("app")

app = FastAPI(
    title="LeadRadar AI Backend",
    description="AI-powered Lead Intelligence Platform API dashboard",
    version="1.0.0"
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(
        f"Request: {request.method} {request.url.path} | "
        f"Status: {response.status_code} | "
        f"Latency: {process_time:.4f}s | "
        f"Client: {request.client.host if request.client else 'unknown'}"
    )
    return response


# Enable CORS for frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, config should target settings.FRONTEND_URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount logical sub-routers
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(leads.router)
app.include_router(admin.router)
app.include_router(system.router)

# Redirect root path to Swagger documentation
@app.get('/', include_in_schema=False)
def root_redirect():
    return RedirectResponse(url='/docs')