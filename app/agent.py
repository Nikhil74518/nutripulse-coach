import json
import logging
import os
import re
import sys
from typing import Any, Dict

from google.adk.agents import Agent, LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events import Event
from google.adk.events.request_input import RequestInput
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.workflow import JoinNode, Workflow, START
from mcp import StdioServerParameters
from pydantic import BaseModel, Field

from app.config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nutripulse_security")


# -----------------------------------------------------------------------------
# Domain Pydantic Schemas
# -----------------------------------------------------------------------------
class MealPlanOutput(BaseModel):
    daily_calories: int = Field(description="Total target daily calories")
    macros: str = Field(description="Protein, carbs, and fat breakdown")
    suggested_meals: list[str] = Field(description="List of recommended meals")


class WellnessPlanOutput(BaseModel):
    hydration_target: str = Field(description="Daily hydration goal")
    workout_recommendation: str = Field(description="Recommended exercise/movement")
    wellness_tips: list[str] = Field(description="Key lifestyle or recovery tips")


# -----------------------------------------------------------------------------
# MCP Toolset Configuration (Phase 3)
# -----------------------------------------------------------------------------
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[os.path.join(os.path.dirname(__file__), "mcp_server.py")],
        )
    )
)


# -----------------------------------------------------------------------------
# Specialized LlmAgents (Phase 2 & Phase 3)
# -----------------------------------------------------------------------------
meal_planner_agent = LlmAgent(
    name="meal_planner",
    model=config.model,
    instruction=(
        "You are NutriPulse Meal Planner. Design balanced daily meal plans tailored to user goals. "
        "Use the MCP tools `search_recipes` and `get_macronutrient_targets` when applicable."
    ),
    tools=[mcp_toolset],
    output_schema=MealPlanOutput,
    output_key="meal_plan",
)

wellness_coach_agent = LlmAgent(
    name="wellness_coach",
    model=config.model,
    instruction=(
        "You are NutriPulse Wellness Coach. Provide actionable hydration, exercise, and recovery strategies. "
        "Use the MCP tools `calculate_bmi` and `log_daily_water_intake` when applicable."
    ),
    tools=[mcp_toolset],
    output_schema=WellnessPlanOutput,
    output_key="wellness_plan",
)


# -----------------------------------------------------------------------------
# Security Checkpoint Node (Phase 4)
# -----------------------------------------------------------------------------
def security_checkpoint(ctx: Context, node_input: Any) -> Event:
    raw_text = str(node_input)
    
    # 1. PII Scrubbing (Email, Phone, SSN, Credit Card)
    scrubbed_text = raw_text
    scrubbed_text = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[REDACTED_EMAIL]", scrubbed_text)
    scrubbed_text = re.sub(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "[REDACTED_PHONE]", scrubbed_text)
    scrubbed_text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]", scrubbed_text)
    scrubbed_text = re.sub(r"\b(?:\d[ -]*?){13,16}\b", "[REDACTED_CARD]", scrubbed_text)

    # 2. Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions", "system prompt", "bypass",
        "jailbreak", "override security", "act as DAN"
    ]
    is_injection = any(kw in raw_text.lower() for kw in injection_keywords)

    # 3. Domain-Specific Rule (Extreme Calorie Floor / Medical Danger)
    is_dangerous_diet = False
    cal_match = re.search(r"(\d+)\s*cal", raw_text.lower())
    if cal_match:
        cals = int(cal_match.group(1))
        if 0 < cals < 1000:
            is_dangerous_diet = True

    # Audit Logging
    audit_event = {
        "event": "security_scan",
        "session_id": getattr(ctx.session, "id", "unknown"),
        "pii_scrubbed": scrubbed_text != raw_text,
        "injection_detected": is_injection,
        "dangerous_diet_flagged": is_dangerous_diet,
    }

    if is_injection:
        audit_event["severity"] = "CRITICAL"
        logger.error(json.dumps(audit_event))
        return Event(
            output="[SECURITY BLOCKED] Potential prompt injection detected.",
            route="SECURITY_EVENT"
        )
    elif is_dangerous_diet:
        audit_event["severity"] = "WARNING"
        logger.warning(json.dumps(audit_event))
        ctx.state["security_warning"] = "Extreme low calorie goal flagged for medical review."
        return Event(output=scrubbed_text, route="PASSED", state={"clean_input": scrubbed_text})
    else:
        audit_event["severity"] = "INFO"
        logger.info(json.dumps(audit_event))
        return Event(output=scrubbed_text, route="PASSED", state={"clean_input": scrubbed_text})


# -----------------------------------------------------------------------------
# Security Violation Terminal Handler (Phase 4)
# -----------------------------------------------------------------------------
def security_violation_handler(node_input: str) -> str:
    return f"Security Alert: Your request was blocked due to system security policy violation. Reason: {node_input}"


# -----------------------------------------------------------------------------
# Orchestrator & HITL Nodes (Phase 2)
# -----------------------------------------------------------------------------
def orchestrator_prep(ctx: Context, node_input: Any) -> Dict[str, Any]:
    # Shared data initialization in ctx.state
    ctx.state["processed_by_orchestrator"] = True
    clean_input = ctx.state.get("clean_input", str(node_input))
    return {"user_query": clean_input}


def hitl_approval(ctx: Context, node_input: Any):
    """Human-in-the-loop review step for custom diet plan confirmation."""
    if ctx.resume_inputs and "user_approval" in ctx.resume_inputs:
        user_choice = ctx.resume_inputs["user_approval"]
        return Event(output=f"Plan confirmed by user ({user_choice}). Processing final summary.", route="APPROVED")
    
    # Pause for user input
    yield RequestInput(
        interrupt_id="user_approval",
        message="NutriPulse has generated your initial plan! Please reply 'proceed' to finalize or 'modify' to change goals."
    )


def final_summary(ctx: Context, node_input: Any) -> str:
    meal_plan = ctx.state.get("meal_plan", {})
    wellness_plan = ctx.state.get("wellness_plan", {})
    sec_warn = ctx.state.get("security_warning", "")

    summary = (
        "🥗 **NutriPulse Personalized Wellness Plan Summary**\n\n"
        f"**Meal Guidance:**\n"
        f"- Target Calories: {meal_plan.get('daily_calories', 'N/A')} kcal\n"
        f"- Macros: {meal_plan.get('macros', 'N/A')}\n"
        f"- Suggested Meals: {', '.join(meal_plan.get('suggested_meals', []))}\n\n"
        f"**Wellness & Hydration:**\n"
        f"- Hydration Goal: {wellness_plan.get('hydration_target', 'N/A')}\n"
        f"- Workout Plan: {wellness_plan.get('workout_recommendation', 'N/A')}\n"
        f"- Tips: {', '.join(wellness_plan.get('wellness_tips', []))}\n"
    )
    if sec_warn:
        summary += f"\n⚠️ **Medical Note:** {sec_warn}"
    return summary


# -----------------------------------------------------------------------------
# ADK 2.0 Workflow Graph Assembly (Phase 2)
# -----------------------------------------------------------------------------
join_plans = JoinNode(name="join_plans")

root_agent = Workflow(
    name="nutripulse_workflow",
    edges=[
        # Entry into security checkpoint
        (START, security_checkpoint),
        
        # Security routing using dict mapping
        (security_checkpoint, {
            "SECURITY_EVENT": security_violation_handler,
            "PASSED": orchestrator_prep
        }),
        
        # Parallel branch execution for specialized agents
        (orchestrator_prep, (meal_planner_agent, wellness_coach_agent)),
        ((meal_planner_agent, wellness_coach_agent), join_plans),
        
        # HITL flow and final synthesis
        (join_plans, hitl_approval),
        (hitl_approval, final_summary),
    ]
)

app = App(
    root_agent=root_agent,
    name="app",
)
