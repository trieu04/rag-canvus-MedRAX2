from __future__ import annotations

from time import monotonic
from typing import Any, Type

import httpx
from langchain_core.callbacks import AsyncCallbackManagerForToolRun, CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, model_validator


class CanvusRAGLookupInput(BaseModel):
    question: str = Field(..., description="Question to ask against the Canvus/apps-api knowledge base")
    canvas_id: int | None = Field(default=None, description="Internal canvas ID if already known")
    remote_canvas_id: str | None = Field(default=None, description="Remote Canvus canvas ID when internal canvas_id is unknown")
    mode: str = Field(default="hybrid", description="Retrieval mode to pass to apps/api")
    top_k: int = Field(default=10, ge=1, description="Maximum number of context nodes to return")
    request_id: str | None = Field(default=None, description="Optional correlation ID propagated across services")

    @model_validator(mode="after")
    def validate_canvas_identity(self) -> "CanvusRAGLookupInput":
        if self.canvas_id is None and not self.remote_canvas_id:
            raise ValueError("Either canvas_id or remote_canvas_id is required")
        return self


class CanvusRAGLookupTool(BaseTool):
    name: str = "canvus_rag_lookup"
    description: str = (
        "Looks up canvas-scoped knowledge from the apps/api RAG service. "
        "Use this when you need grounded supporting knowledge tied to a specific Canvus canvas. "
        "Requires either canvas_id or remote_canvas_id. Returns answer, multimodal content blocks, citations, graph context, and metadata."
    )
    args_schema: Type[BaseModel] = CanvusRAGLookupInput

    base_url: str = "http://localhost:7200"
    timeout_seconds: int = 30

    def __init__(self, base_url: str = "http://localhost:7200", timeout_seconds: int = 30):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(self, payload: CanvusRAGLookupInput) -> tuple[dict[str, Any], dict[str, Any]]:
        started_at = monotonic()
        route_path = "/query"
        params: dict[str, Any] = {"canvas_id": payload.canvas_id} if payload.canvas_id is not None else {"remote_canvas_id": payload.remote_canvas_id}

        if payload.canvas_id is None:
            route_path = "/sync/query"

        body = {
            "question": payload.question,
            "mode": payload.mode,
            "top_k": payload.top_k,
            "request_id": payload.request_id,
        }

        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = client.post(route_path, params=params, json=body)
                response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("apps/api returned an unexpected payload shape")

            latency_ms = int((monotonic() - started_at) * 1000)
            metadata = {
                "analysis_status": str(result.get("metadata", {}).get("analysis_status") or "completed"),
                "query_mode": str(result.get("metadata", {}).get("query_mode") or ("query" if payload.canvas_id is not None else "sync_query")),
                "canvas_id": result.get("canvas_id", payload.canvas_id),
                "remote_canvas_id": result.get("remote_canvas_id", payload.remote_canvas_id),
                "latency_ms": result.get("metadata", {}).get("latency_ms", latency_ms),
                "top_k": result.get("metadata", {}).get("top_k", payload.top_k),
                "request_id": payload.request_id,
                "upstream_status": response.status_code,
            }

            output = {
                "answer": result.get("answer", ""),
                "content_blocks": result.get("content_blocks", []),
                "sources": result.get("sources", []),
                "context": result.get("context", []),
                "edges": result.get("edges", []),
                "canvas_id": result.get("canvas_id", payload.canvas_id),
                "remote_canvas_id": result.get("remote_canvas_id", payload.remote_canvas_id),
                "confidence": result.get("confidence"),
            }
            return output, metadata
        except Exception as exc:
            latency_ms = int((monotonic() - started_at) * 1000)
            return (
                {"error": str(exc)},
                {
                    "analysis_status": "failed",
                    "query_mode": "query" if payload.canvas_id is not None else "sync_query",
                    "canvas_id": payload.canvas_id,
                    "remote_canvas_id": payload.remote_canvas_id,
                    "latency_ms": latency_ms,
                    "top_k": payload.top_k,
                    "request_id": payload.request_id,
                    "error_details": str(exc),
                },
            )

    def _run(
        self,
        question: str,
        canvas_id: int | None = None,
        remote_canvas_id: str | None = None,
        mode: str = "hybrid",
        top_k: int = 10,
        request_id: str | None = None,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = CanvusRAGLookupInput(
            question=question,
            canvas_id=canvas_id,
            remote_canvas_id=remote_canvas_id,
            mode=mode,
            top_k=top_k,
            request_id=request_id,
        )
        return self._request(payload)

    async def _arun(
        self,
        question: str,
        canvas_id: int | None = None,
        remote_canvas_id: str | None = None,
        mode: str = "hybrid",
        top_k: int = 10,
        request_id: str | None = None,
        run_manager: AsyncCallbackManagerForToolRun | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return self._run(
            question=question,
            canvas_id=canvas_id,
            remote_canvas_id=remote_canvas_id,
            mode=mode,
            top_k=top_k,
            request_id=request_id,
        )
