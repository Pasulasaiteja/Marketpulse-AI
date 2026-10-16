"""FastAPI Decision API.

Endpoints: /profile/extract, /profile/confirm, /plan, /chain/plan, /ask, /opportunities.
Run:  uvicorn marketpulse.api.app:app --reload
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from marketpulse.audit import AuditLog
from marketpulse.contracts.models import CanonicalData, CatalogueItem, OptimizerConstraints
from marketpulse.csvloader import dump_csv, dump_stores_csv
from marketpulse.mocks.catalogue import sample_catalogue
from marketpulse.mocks.fixtures import make_canonical_data, make_demo_chain
from marketpulse.registry import Modules
from marketpulse.service import ApiError, DecisionService

UI_DIR = Path(__file__).resolve().parents[1] / "ui"


class _Req(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractRequest(_Req):
    description: str
    language_hint: str | None = None


class ConfirmRequest(_Req):
    profile_id: str
    edits: dict[str, Any] = Field(default_factory=dict)


class PlanRequest(_Req):
    profile_id: str
    budget: float
    horizon_days: int = 14
    language: str | None = None
    data: CanonicalData | None = None
    dataset_id: str | None = None
    products_csv: str | None = None
    sales_csv: str | None = None
    shop_id: str | None = None
    as_of: dt.date | None = None
    constraints: OptimizerConstraints | None = None


class StoresRequest(_Req):
    profile_id: str
    products_csv: str
    sales_csv: str
    as_of: dt.date | None = None


class ChainPlanRequest(_Req):
    """Chain-wide view: one plan per store (each with its own budget), then the totals."""

    profile_id: str
    budget: float = Field(description="Default budget applied to each store.")
    horizon_days: int = 14
    language: str | None = None
    dataset_ids: list[str] = Field(min_length=1, description="Store dataset_ids from /stores.")
    store_budgets: dict[str, float] | None = Field(
        default=None, description="Optional per-store budget overrides, keyed by dataset_id.")
    constraints: OptimizerConstraints | None = None


class OpportunityRequest(_Req):
    profile_id: str
    budget: float
    horizon_days: int = 14
    data: CanonicalData | None = None
    dataset_id: str | None = None
    products_csv: str | None = None
    sales_csv: str | None = None
    shop_id: str | None = None
    as_of: dt.date | None = None
    catalogue: list[CatalogueItem] | None = None
    catalogue_csv: str | None = None
    include_trial_orders: bool = True


class AskRequest(_Req):
    request_id: str
    question: str
    language: str | None = None


def create_app(modules: Modules | None = None, audit_path: str | None = "logs/audit.jsonl") -> FastAPI:
    service = DecisionService(modules, AuditLog(audit_path))
    app = FastAPI(title="MarketPulse Decision API", version="0.1.0")
    app.state.service = service

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def _bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"] if p != "body")
        return JSONResponse(status_code=422, content={
            "status": "error", "request_id": None,
            "error": {"code": "INVALID_REQUEST", "message": f"{loc}: {first['msg']}"}})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/profile/extract")
    def extract(req: ExtractRequest) -> dict[str, Any]:
        return service.extract_profile(req.description, req.language_hint)

    @app.post("/profile/confirm")
    def confirm(req: ConfirmRequest) -> dict[str, Any]:
        return service.confirm_profile(req.profile_id, req.edits)

    @app.post("/plan")
    def plan(req: PlanRequest) -> dict[str, Any]:
        return service.plan(req.model_dump(exclude_none=False) | {
            "data": req.data, "constraints": req.constraints})

    @app.post("/ask")
    def ask(req: AskRequest) -> dict[str, Any]:
        return service.ask(req.request_id, req.question, req.language)

    @app.get("/demo/files")
    def demo_files() -> dict[str, Any]:
        products_csv, sales_csv = dump_csv(make_canonical_data())
        return {"synthetic": True, "note": "Invented sample data, not a real shop.",
                "products_csv": products_csv, "sales_csv": sales_csv}

    @app.get("/demo/chain")
    def demo_chain() -> dict[str, Any]:
        products_csv, sales_csv = dump_stores_csv(make_demo_chain())
        return {"synthetic": True, "note": "Invented sample data, not real stores.",
                "products_csv": products_csv, "sales_csv": sales_csv}

    @app.post("/stores")
    def stores(req: StoresRequest) -> dict[str, Any]:
        """Register every store in multi-store CSVs; use each returned dataset_id with /plan."""
        return service.register_stores(req.model_dump(mode="json"))

    @app.post("/chain/plan")
    def chain_plan(req: ChainPlanRequest) -> dict[str, Any]:
        """Plan every store independently and return per-store plans plus chain-wide totals."""
        return service.chain_plan(req.model_dump(exclude_none=False) | {
            "constraints": req.constraints})

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/ui/")

    @app.post("/opportunities")
    def opportunities(req: OpportunityRequest) -> dict[str, Any]:
        return service.opportunities(req.model_dump(exclude_none=False) | {
            "data": req.data, "catalogue": req.catalogue})

    @app.get("/demo/catalogue")
    def demo_catalogue() -> dict[str, Any]:
        """Invented sample supplier catalogue, used when /opportunities gets no catalogue."""
        return {"synthetic": True, "note": "Invented sample catalogue, not real products.",
                "items": [c.model_dump(mode="json") for c in sample_catalogue()]}

    app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")
    return app


app = create_app()
