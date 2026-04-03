"""
System API Routes

Routes for system-level operations like API secret validation and prompt retrieval.
"""

import re
from pathlib import Path
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
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
