# Project Submission: Elderly Care Assistant Agent

## Problem Statement
Caring for elderly relatives is a complex, high-stakes responsibility. Caregivers and senior family members often struggle to manage medications (dosage and adherence) and coordinate frequent medical appointments. Miscommunication can lead to skipped doses, double-dosing, or missed doctor visits. 

The **Elderly Care Assistant** provides a secure, intuitive, and autonomous agentic interface to manage pill schedules, log adherence, track doctor visits, and send caregiver alerts, providing peace of mind and reducing operational overhead for families.

## Solution Architecture

```mermaid
graph TD
    START[START] --> SecCheck[Security Checkpoint Node]
    SecCheck -- SECURITY_EVENT --> SecAlert[Security Alert Node]
    SecCheck -- __DEFAULT__ --> Orchestrator[Care Coordinator Orchestrator]
    
    Orchestrator -- needs_approval --> HITL[Human Approval Node]
    Orchestrator -- __DEFAULT__ --> Final[Final Output Node]
    
    HITL -- confirmed --> ExecAction[Execute Action Node]
    HITL -- cancelled --> Final
    
    ExecAction --> Final
    
    subgraph Sub-Agents (Connected to MCP Server)
        MedMgr[Medication Manager]
        ApptSch[Appointment Scheduler]
    end
    
    Orchestrator -. AgentTool .-> MedMgr
    Orchestrator -. AgentTool .-> ApptSch
    
    subgraph Stdio MCP Server
        get_meds[get_medications]
        log_med[record_med_adherence]
        get_appts[get_appointments]
        sch_appt[schedule_appointment]
        alert_cg[alert_caregiver]
    end
    
    MedMgr -. McpToolset .-> get_meds
    MedMgr -. McpToolset .-> log_med
    ApptSch -. McpToolset .-> get_appts
    ApptSch -. McpToolset .-> sch_appt
    ApptSch -. McpToolset .-> alert_cg
```

## Concepts Used

1. **ADK Workflow (Graph API)**: Implemented in `app/agent.py`. The system uses a graph-based state-machine starting with a security checkpoint, routing to the orchestrator, and splitting off into human approval and execution phases.
2. **LlmAgents**: Implemented in `app/agent.py` as:
   - `care_coordinator` (Orchestrator LlmAgent)
   - `medication_manager` (Specialized LlmAgent)
   - `appointment_scheduler` (Specialized LlmAgent)
3. **AgentTool**: Used in `app/agent.py` to expose specialized sub-agents (`medication_manager`, `appointment_scheduler`) as tools for the orchestrator, keeping parent-in-control delegation clean.
4. **MCP Server**: Implemented in `app/mcp_server.py`. Runs as a Stdio subprocess connecting standard tools to the sub-agents via `McpToolset`.
5. **Security Checkpoint**: Implemented in `app/agent.py` as `security_checkpoint`. Scrubs PII, stops prompt injections, prints structured logs, and routes to a blocked screen.
6. **Agents CLI**: Used for project creation (`agents-cli scaffold create`), package configuration (`pyproject.toml`), and local debugging (`agents-cli playground`).

## Security Design

- **PII Scrubbing**: Regex filters automatically scrub sensitive data like Phone Numbers, SSNs, and Medical IDs from inputs before they are passed to the model. This protects patient privacy.
- **Prompt Injection Defense**: Keyword scanning intercepts prompt injections (e.g. `ignore previous instructions`), immediately rerouting the flow to a `security_alert_node` and logging a `CRITICAL` alert.
- **Audit Logs**: Generates JSON audit logs detailing security classifications, PII scrub status, and threats.
- **Domain-Specific Rules**: Flags attempts to modify or stop medication schedules as `WARNING` logs.

## MCP Server Design

- `get_medications`: Retrieves pill schedules, dosage, and purposes.
- `record_med_adherence`: Logs daily compliance (taken/missed) for audit.
- `get_appointments`: Checks upcoming doctor calendars.
- `schedule_appointment`: Books dates and locations for doctor check-ups.
- `alert_caregiver`: Sends caregiver emergency notices for missed doses or abnormal metrics.

## Human-in-the-Loop (HITL) Flow

To prevent accidental changes to schedules or appointments, any query referencing scheduling, cancellations, or caregiver alerts triggers the **Consent Verification** prompt in `human_approval_node` using `yield RequestInput`. This pauses the workflow graph execution, prompting the user/caregiver in the ADK UI. Only upon receiving explicit confirmation (`yes`) is the `execute_action_node` invoked to run the actual action tool.

## Demo Walkthrough

1. **Retrieving Schedules**: The user asks for daily pills. The MedicationManager executes `get_medications` via MCP, returning the list.
2. **Rescheduling Appointments (HITL)**: The user asks to schedule Dr. Smith. The flow halts, displaying a consent dialog in the UI. If confirmed, the scheduler runs `schedule_appointment`.
3. **Safety / Security Blocking**: An attempt to inject prompts or query with raw PII triggers the Security Checkpoint, logging a warning and displaying a standard safety error.

## Impact / Value Statement

This agent bridges the gap between complex health data and seniors/caregivers. By providing structured scheduling, logging compliance, protecting PII, and enforcing human consent, the Elderly Care Assistant enhances care coordination, minimizes medication errors, and keeps family members safely informed.
