import os
import re
import json
import sys
import datetime
from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.tools import AgentTool
from google.adk.workflow import Workflow, START, node
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.genai import types

from .config import config

# Path to the MCP server
current_dir = os.path.dirname(os.path.abspath(__file__))
mcp_server_path = os.path.join(current_dir, "mcp_server.py")

# Stdio server parameters
mcp_server_params = StdioServerParameters(
    command=sys.executable,
    args=[mcp_server_path],
)

# McpToolset instance
mcp_tools = McpToolset(
    connection_params=StdioConnectionParams(server_params=mcp_server_params)
)

# 1. Specialized Sub-Agents
medication_manager = LlmAgent(
    name="medication_manager",
    model=config.model,
    instruction="""You are the MedicationManager. You help track daily medication schedules, dosage compliance, and check for missed doses.
Use your tools to retrieve medications, check schedules, or record adherence.
Always present a clear summary of compliance.
Be compassionate, clear, and direct. Respond in plain text.""",
    description="Manages medication lists, schedules, and pill adherence logs.",
    tools=[mcp_tools]
)

appointment_scheduler = LlmAgent(
    name="appointment_scheduler",
    model=config.model,
    instruction="""You are the AppointmentScheduler. You help coordinate calendar scheduling for doctor visits, match availability, and draft calendar invites.
Use your tools to retrieve or schedule appointments.
Always present scheduled details clearly.
Be polite and precise. Respond in plain text.""",
    description="Manages doctor appointments, scheduling lookups, and calendars.",
    tools=[mcp_tools]
)

# 2. Orchestrator Agent
care_coordinator = LlmAgent(
    name="care_coordinator",
    model=config.model,
    instruction="""You are the CareCoordinator, the main interface for an elderly care assistant.
Your job is to understand the user's intent and coordinate between the MedicationManager (for medication scheduling and compliance checks) and the AppointmentScheduler (for scheduling doctor appointments or checking calendars).
You MUST delegate tasks to the specialized agents using the tools provided when appropriate. Do not try to answer medication or scheduling requests yourself.
If the request requires sending a critical caregiver alert, you should also delegate that or use the alert_caregiver tool.
Keep responses concise, warm, and helpful. Respond in plain text.""",
    tools=[
        AgentTool(medication_manager),
        AgentTool(appointment_scheduler)
    ]
)

# 3. Security Checkpoint Function Node
def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    input_text = ""
    if hasattr(node_input, "parts") and node_input.parts:
        input_text = "".join([part.text for part in node_input.parts if part.text])
    elif isinstance(node_input, str):
        input_text = node_input

    # Audit Log Entry Template
    log_entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "severity": "INFO",
        "action": "security_check",
        "details": {}
    }

    # Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions", "system prompt", "override rules",
        "you are now", "dan mode", "ignore safety", "developer mode"
    ]
    for kw in injection_keywords:
        if kw in input_text.lower():
            log_entry["severity"] = "CRITICAL"
            log_entry["details"]["threat"] = "Prompt injection attempt"
            log_entry["details"]["keyword"] = kw
            print(json.dumps(log_entry))
            
            content = types.Content(
                role='model',
                parts=[types.Part.from_text(text="⚠️ Security Alert: Safety policy violation detected. Action blocked.")]
            )
            return Event(
                output="Blocked due to security policy.",
                route="SECURITY_EVENT",
                content=content
            )

    # PII Scrubbing
    scrubbed_text = input_text
    
    # Phone numbers
    phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
    if re.search(phone_pattern, scrubbed_text):
        scrubbed_text = re.sub(phone_pattern, "<REDACTED_PHONE>", scrubbed_text)
        log_entry["details"]["pii_scrubbed"] = log_entry.get("details", {}).get("pii_scrubbed", []) + ["phone"]
        log_entry["severity"] = "WARNING"
        
    # SSN
    ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
    if re.search(ssn_pattern, scrubbed_text):
        scrubbed_text = re.sub(ssn_pattern, "<REDACTED_SSN>", scrubbed_text)
        log_entry["details"]["pii_scrubbed"] = log_entry.get("details", {}).get("pii_scrubbed", []) + ["ssn"]
        log_entry["severity"] = "WARNING"

    # Medical ID
    med_id_pattern = r'\b[A-Z]{3}\d{8}\b'
    if re.search(med_id_pattern, scrubbed_text):
        scrubbed_text = re.sub(med_id_pattern, "<REDACTED_MED_ID>", scrubbed_text)
        log_entry["details"]["pii_scrubbed"] = log_entry.get("details", {}).get("pii_scrubbed", []) + ["medical_id"]
        log_entry["severity"] = "WARNING"

    # Domain rule: Flag halting of medication
    if "stop taking" in scrubbed_text.lower() or "cancel all medication" in scrubbed_text.lower():
        log_entry["severity"] = "WARNING"
        log_entry["details"]["domain_warning"] = "halting medication schedule without doctor approval"

    if log_entry["severity"] != "INFO":
        print(json.dumps(log_entry))

    # Save scrubbed input in state
    return Event(
        output=scrubbed_text,
        route="__DEFAULT__",
        state={"scrubbed_input": scrubbed_text}
    )

# 4. Security Alert Node
def security_alert_node(node_input: str) -> Event:
    return Event(
        content=types.Content(
            role='model',
            parts=[types.Part.from_text(text="⚠️ I cannot complete this request due to security and safety rules. Please try again.")]
        ),
        output="Request blocked by security checkpoint."
    )

# 5. Orchestrator Node
@node(rerun_on_resume=True)
async def orchestrator(ctx: Context, node_input: str) -> Event:
    # Check if a sensitive action (scheduling, changing schedule, alerts) is requested
    # and not yet approved by HITL
    input_lower = node_input.lower()
    needs_hitl = ("schedule" in input_lower or "appointment" in input_lower or "alert" in input_lower or "took" in input_lower)
    
    if needs_hitl and not ctx.state.get("approved"):
        return Event(
            output=node_input,
            route="needs_approval",
            state={"pending_action": node_input}
        )
        
    # Otherwise run care coordinator
    response = await ctx.run_node(care_coordinator, node_input=node_input)
    response_text = ""
    if hasattr(response, "parts") and response.parts:
        response_text = "".join([p.text for p in response.parts if p.text])
    else:
        response_text = str(response)

    return Event(output=response_text, route="__DEFAULT__")

# 6. Human Approval Node
@node(rerun_on_resume=True)
async def human_approval_node(ctx: Context, node_input: str):
    if not ctx.resume_inputs or "confirm_action" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="confirm_action",
            message="⚠️ Consent Verification Required: Please confirm to proceed with this scheduling/medication action (yes/no):"
        )
        return

    confirm_val = ctx.resume_inputs.get("confirm_action", "")
    if isinstance(confirm_val, dict):
        confirm_response = confirm_val.get("response", "")
    else:
        confirm_response = confirm_val
    confirm_response = str(confirm_response).strip().lower()

    if confirm_response in ["yes", "y", "confirm", "ok"]:
        yield Event(
            output=ctx.state.get("pending_action", node_input),
            route="confirmed",
            state={"approved": True}
        )
    else:
        yield Event(
            output="Action cancelled by user/caregiver.",
            route="cancelled",
            state={"approved": False}
        )

# 7. Execute Action Node
@node(rerun_on_resume=True)
async def execute_action_node(ctx: Context, node_input: str) -> Event:
    # Rerun the orchestrator now that approved is set to True
    response = await ctx.run_node(care_coordinator, node_input=node_input)
    response_text = ""
    if hasattr(response, "parts") and response.parts:
        response_text = "".join([p.text for p in response.parts if p.text])
    else:
        response_text = str(response)
        
    return Event(output=f"Action confirmed. Result:\n{response_text}")

# 8. Final Output Formatting Node
def final_output(node_input: str) -> Event:
    return Event(
        content=types.Content(
            role='model',
            parts=[types.Part.from_text(text=node_input)]
        ),
        output=node_input
    )

from google.adk.workflow import Workflow, START, node

# 9. Workflow definition
root_agent = Workflow(
    name="elderly_care_assistant_workflow",
    edges=[
        (START, security_checkpoint),
        (security_checkpoint, {'SECURITY_EVENT': security_alert_node, '__DEFAULT__': orchestrator}),
        (orchestrator, {'needs_approval': human_approval_node, '__DEFAULT__': final_output}),
        (human_approval_node, {'confirmed': execute_action_node, 'cancelled': final_output}),
        (execute_action_node, final_output)
    ]
)

app = App(
    root_agent=root_agent,
    name="app",
)
