"""
System API Routes

Routes for system-level operations like API secret validation and prompt retrieval.
"""

import ast
import base64
import re
import uuid
from pathlib import Path
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Any

from ..services.tool_manager import tool_manager, ToolStatus
from ..utils.file_utils import (
    filesystem_path_from_display_url,
    sanitize_dict_paths,
    sanitize_fs_paths,
    to_display_path,
)
from ..config import settings
from ..utils.logging_config import logger

_SYSTEM_PROMPTS_PATH = Path(__file__).resolve().parents[4] / "medrax" / "docs" / "system_prompts.txt"


def _load_prompt_section(section: str) -> str | None:
    """Read a named section from system_prompts.txt, returning None if not found."""
    try:
        content = _SYSTEM_PROMPTS_PATH.read_text(encoding="utf-8")
        match = re.search(
            rf"\[{re.escape(section)}\]\s*(.*?)(?=\n\[[^\]]+\]|$)",
            content,
            re.DOTALL,
        )
        if match:
            return match.group(1).strip()
    except Exception as e:
        logger.warning(f"failed_to_load_prompt section={section} error={e}")
    return None

router = APIRouter()


class ValidateSecretResponse(BaseModel):
    """Response for API secret validation."""

    valid: bool
    message: str


@router.post("/system/validate-secret", response_model=ValidateSecretResponse)
async def validate_api_secret(x_api_secret: str = Header(None, alias="X-API-Secret")):
    """
    Validate API secret key.

    This endpoint allows the frontend to validate the API secret
    before storing it locally.
    """
    if not settings.REQUIRE_API_SECRET:
        return ValidateSecretResponse(valid=True, message="API secret validation is disabled")

    if not x_api_secret:
        logger.warning("API secret validation failed - no secret provided")
        return ValidateSecretResponse(valid=False, message="API secret is required")

    if x_api_secret != settings.API_SECRET_KEY:
        logger.warning("API secret validation failed - invalid secret provided")
        return ValidateSecretResponse(valid=False, message="Invalid API secret")

    logger.info("API secret validated successfully")
    return ValidateSecretResponse(valid=True, message="API secret is valid")


class AutoAnalysisPromptResponse(BaseModel):
    """The standard prompt used for automatic image analysis on first upload."""

    prompt: str


@router.get("/system/auto-analysis-prompt", response_model=AutoAnalysisPromptResponse)
async def get_auto_analysis_prompt():
    """
    Return the standard prompt that is automatically submitted when a doctor
    uploads their first scan in a chat.  Sourced from system_prompts.txt so it
    can be updated without a frontend deploy.
    """
    prompt = _load_prompt_section("AUTO_ANALYSIS")
    if not prompt:
        # Safe fallback so the frontend never breaks even if the file is missing
        prompt = (
            "Please perform a comprehensive analysis of this medical image using all available tools. "
            "Provide a complete structured report with key findings, quantitative metrics, "
            "clinical impression, and recommendations."
        )
    return AutoAnalysisPromptResponse(prompt=prompt)


class SystemOrchestrateQueryRequest(BaseModel):
    query: str
    canvas_id: int | None = None
    remote_canvas_id: str | None = None
    mode: str = "hybrid"
    top_k: int = 10
    request_id: str | None = None
    attachments: list[str] = []


class SystemOrchestrateQueryResponse(BaseModel):
    request_id: str
    answer: str
    content_blocks: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    context: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    canvas_id: int | None = None
    remote_canvas_id: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = {}


def _validate_service_token(x_service_token: str | None) -> None:
    expected_token = settings.MEDRAX_SERVICE_TOKEN
    if not expected_token:
        raise HTTPException(status_code=503, detail="MEDRAX_SERVICE_TOKEN is not configured")
    if x_service_token != expected_token:
        raise HTTPException(status_code=403, detail="Invalid service token")


def _ensure_tool_loaded(tool_id: str) -> None:
    tool = tool_manager.get_tool(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")
    if tool.status == ToolStatus.LOADED:
        return
    load_result = tool_manager.load_tool(tool_id)
    if not load_result.get("success"):
        raise HTTPException(status_code=503, detail=load_result.get("error", f"Failed to load tool '{tool_id}'"))
    tool_manager.load_tool_in_background(tool_id)
    refreshed_tool = tool_manager.get_tool(tool_id)
    if refreshed_tool is None or refreshed_tool.status != ToolStatus.LOADED:
        raise HTTPException(status_code=503, detail=f"Tool '{tool_id}' failed to load")


def _infer_mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".png":
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".gif":
        return "image/gif"
    return "application/octet-stream"


def _resolve_attachment_paths(attachments: list[str]) -> tuple[list[str], list[str]]:
    resolved_paths: list[str] = []
    warnings: list[str] = []
    for attachment in attachments:
        if not attachment:
            continue
        mapped_path = filesystem_path_from_display_url(attachment)
        if mapped_path.exists():
            resolved_paths.append(str(mapped_path))
        else:
            warnings.append(f"Skipped unsupported attachment ref: {attachment}")
    return resolved_paths, warnings


def _extract_text_content(content: Any) -> str:
    if isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                text_parts.append(block)
        return sanitize_fs_paths("".join(text_parts))
    if content is None:
        return ""
    return sanitize_fs_paths(str(content))


def _parse_tool_message_content(raw_content: Any) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    result_data: dict[str, Any] | None = None
    metadata: dict[str, Any] = {}
    if raw_content:
        try:
            parsed = ast.literal_eval(str(raw_content))
            if isinstance(parsed, (tuple, list)) and len(parsed) >= 2:
                result_data = parsed[0] if isinstance(parsed[0], dict) else {"raw": str(parsed[0])}
                metadata = parsed[1] if isinstance(parsed[1], dict) else {}
            elif isinstance(parsed, dict):
                result_data = parsed
            else:
                result_data = {"raw": str(parsed)}
        except (ValueError, SyntaxError, TypeError):
            result_data = {"raw": str(raw_content)}
    return sanitize_dict_paths(result_data), sanitize_dict_paths(metadata)


def _build_grounding_block(result_data: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any] | None:
    predictions = result_data.get("predictions") or []
    visualization_path = result_data.get("visualization_path")
    source_image_path = metadata.get("image_path")
    if not predictions or not visualization_path or not source_image_path:
        return None

    original_size = metadata.get("original_size") or []
    image_width = None
    image_height = None
    if isinstance(original_size, (list, tuple)) and len(original_size) >= 2:
        image_width = float(original_size[0])
        image_height = float(original_size[1])

    boxes: list[dict[str, Any]] = []
    for prediction in predictions:
        for bbox in prediction.get("bounding_boxes", {}).get("image_coordinates", []):
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = bbox
            boxes.append(
                {
                    "label": str(prediction.get("phrase", "finding")),
                    "x": float(x1),
                    "y": float(y1),
                    "width": float(x2) - float(x1),
                    "height": float(y2) - float(y1),
                    "score": None,
                }
            )

    if not boxes:
        return None

    return {
        "type": "bbox_overlay",
        "image_ref": to_display_path(str(source_image_path)),
        "source_image_ref": to_display_path(str(source_image_path)),
        "rendered_image_ref": to_display_path(str(visualization_path)),
        "boxes": boxes,
        "source_tool": "xray_phrase_grounding",
        "coordinate_space": "image_pixels",
        "image_width": image_width,
        "image_height": image_height,
    }


def _build_image_block(
    *,
    image_path: Any,
    tool_name: str,
    caption: str | None = None,
) -> dict[str, Any] | None:
    if not image_path:
        return None
    return {
        "type": "image",
        "image_ref": to_display_path(str(image_path)),
        "caption": caption or tool_name,
        "source_tool": tool_name,
    }


_VISUAL_IMAGE_TOOL_IDS = {
    "image_visualizer",
    "xray_phrase_grounding",
    "chest_xray_segmentation",
    "medsam2",
}


@router.post("/system/orchestrate-query", response_model=SystemOrchestrateQueryResponse)
async def orchestrate_query(
    payload: SystemOrchestrateQueryRequest,
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
):
    _validate_service_token(x_service_token)

    if payload.canvas_id is None and not payload.remote_canvas_id:
        raise HTTPException(status_code=400, detail="Either canvas_id or remote_canvas_id is required")

    request_id = payload.request_id or str(uuid.uuid4())
    _ensure_tool_loaded("canvus_rag_lookup")

    agent = tool_manager.create_agent(
        request_id=request_id,
        system_prompt=(
            "You are a Canvus system orchestration worker. Always use canvus_rag_lookup for canvas-scoped supporting knowledge. "
            "If image attachments are available and relevant visual tools are already loaded, you may use them. "
            "Never invent bounding boxes or visual findings; only rely on grounded tool outputs. "
            "Return a concise final answer suitable for an end user."
        ),
    )
    if agent is None:
        raise HTTPException(status_code=503, detail=tool_manager.last_agent_error or "Failed to initialize MedRAX agent")

    attachment_paths, warnings = _resolve_attachment_paths(payload.attachments)
    agent_messages: list[dict[str, Any]] = []

    if attachment_paths:
        image_context = (
            f"[Image Context] The user has provided {len(attachment_paths)} image(s).\n"
            "When calling tools that require image paths, use these exact paths:\n\n"
        )
        for index, image_path in enumerate(attachment_paths, start=1):
            image_context += f"  • Image {index}: {image_path}\n"
        image_context += "\nIMPORTANT: Copy the exact paths above when calling tools."
        agent_messages.append({"role": "user", "content": image_context.strip()})

        for image_path in attachment_paths:
            image_file = Path(image_path)
            with image_file.open("rb") as handle:
                image_bytes = handle.read()
            agent_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{_infer_mime_type(image_file)};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
                            },
                        }
                    ],
                }
            )

    agent_messages.append(
        {
            "role": "user",
            "content": [{"type": "text", "text": payload.query}],
        }
    )

    final_answer = ""
    retrieval_output: dict[str, Any] = {}
    retrieval_metadata: dict[str, Any] = {}
    visual_blocks: list[dict[str, Any]] = []
    tools_used: list[str] = []

    config = {"configurable": {"thread_id": f"canvus-system:{request_id}"}}
    try:
        async for event in agent.workflow.astream({"messages": agent_messages}, config):
            if "agent" in event:
                messages = event["agent"].get("messages", [])
                if messages:
                    content = _extract_text_content(messages[-1].content)
                    if content:
                        final_answer = content
            elif "tools" in event:
                for tool_message in event["tools"].get("messages", []):
                    tool_name = getattr(tool_message, "name", "unknown")
                    if tool_name not in tools_used:
                        tools_used.append(tool_name)
                    result_data, metadata = _parse_tool_message_content(tool_message.content)
                    if tool_name == "canvus_rag_lookup" and result_data:
                        retrieval_output = result_data
                        retrieval_metadata = metadata
                    elif tool_name == "xray_phrase_grounding" and result_data:
                        grounding_block = _build_grounding_block(result_data, metadata)
                        if grounding_block is not None:
                            visual_blocks.append(grounding_block)
                    elif tool_name in _VISUAL_IMAGE_TOOL_IDS and result_data and result_data.get("segmentation_image_path"):
                        segmentation_block = _build_image_block(
                            image_path=result_data.get("segmentation_image_path"),
                            tool_name=tool_name,
                            caption=tool_name,
                        )
                        if segmentation_block is not None:
                            visual_blocks.append(segmentation_block)
                    elif tool_name in _VISUAL_IMAGE_TOOL_IDS and result_data and result_data.get("image_path"):
                        image_block = _build_image_block(
                            image_path=result_data.get("image_path"),
                            tool_name=tool_name,
                            caption=tool_name,
                        )
                        if image_block is not None:
                            visual_blocks.append(image_block)
                    elif tool_name in _VISUAL_IMAGE_TOOL_IDS and result_data and result_data.get("visualization_path"):
                        visualization_block = _build_image_block(
                            image_path=result_data.get("visualization_path"),
                            tool_name=tool_name,
                            caption=tool_name,
                        )
                        if visualization_block is not None:
                            visual_blocks.append(visualization_block)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MedRAX orchestration failed: {sanitize_fs_paths(str(exc))}") from exc

    if not retrieval_output:
        raise HTTPException(status_code=502, detail="MedRAX orchestration completed without canvus_rag_lookup output")

    answer = final_answer or str(retrieval_output.get("answer", "") or "")
    content_blocks = retrieval_output.get("content_blocks", []) or []

    if answer and not any(block.get("type") == "markdown" for block in content_blocks if isinstance(block, dict)):
        content_blocks.insert(0, {"type": "markdown", "markdown": answer})

    content_blocks.extend(visual_blocks)

    metadata = {
        **retrieval_metadata,
        "request_id": request_id,
        "analysis_status": retrieval_metadata.get("analysis_status", "completed" if answer else "failed"),
        "warnings": warnings,
        "tools_used": tools_used,
        "query_mode": retrieval_metadata.get("query_mode", "orchestrated"),
        "top_k": retrieval_metadata.get("top_k", payload.top_k),
    }

    return SystemOrchestrateQueryResponse(
        request_id=request_id,
        answer=answer,
        content_blocks=content_blocks,
        sources=retrieval_output.get("sources", []),
        context=retrieval_output.get("context", []),
        edges=retrieval_output.get("edges", []),
        canvas_id=retrieval_output.get("canvas_id", payload.canvas_id),
        remote_canvas_id=retrieval_output.get("remote_canvas_id", payload.remote_canvas_id),
        confidence=retrieval_output.get("confidence"),
        metadata=metadata,
    )
