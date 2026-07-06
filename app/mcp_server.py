import asyncio
import json
from mcp.server import Server
import mcp.types as types

server = Server("elderly-care-mcp")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_medications",
            description="Retrieve the current list of medications and schedules.",
            inputSchema={
                "type": "object",
                "properties": {},
            }
        ),
        types.Tool(
            name="record_med_adherence",
            description="Record that a medication was taken or missed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "med_name": {"type": "string", "description": "Name of the medication"},
                    "status": {"type": "string", "enum": ["taken", "missed"], "description": "Adherence status"},
                    "time": {"type": "string", "description": "Time of adherence check (e.g. HH:MM)"}
                },
                "required": ["med_name", "status"]
            }
        ),
        types.Tool(
            name="get_appointments",
            description="Retrieve upcoming doctor appointments.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="schedule_appointment",
            description="Schedule a new doctor appointment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "doctor": {"type": "string", "description": "Doctor's name or clinic"},
                    "time": {"type": "string", "description": "Appointment date and time (e.g. 'next Tuesday at 2 PM')"},
                    "purpose": {"type": "string", "description": "Reason for the visit"}
                },
                "required": ["doctor", "time"]
            }
        ),
        types.Tool(
            name="alert_caregiver",
            description="Send an urgent alert to the caregiver.",
            inputSchema={
                "type": "object",
                "properties": {
                    "alert_type": {"type": "string", "description": "Type of alert (e.g., 'missed_dose', 'abnormal_vitals')"},
                    "message": {"type": "string", "description": "Detailed alert message"}
                },
                "required": ["alert_type", "message"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_medications":
        meds = [
            {"name": "Metformin", "dose": "500mg", "schedule": "8:00 AM", "purpose": "Diabetes"},
            {"name": "Lisinopril", "dose": "10mg", "schedule": "8:00 AM", "purpose": "Blood Pressure"},
            {"name": "Atorvastatin", "dose": "20mg", "schedule": "8:00 PM", "purpose": "Cholesterol"}
        ]
        return [types.TextContent(type="text", text=json.dumps(meds))]
        
    elif name == "record_med_adherence":
        med = arguments.get("med_name")
        status = arguments.get("status")
        time = arguments.get("time", "now")
        return [types.TextContent(type="text", text=f"Successfully recorded adherence for {med}: {status} at {time}.")]
        
    elif name == "get_appointments":
        apps = [
            {"doctor": "Dr. Smith (Cardiologist)", "time": "Next Tuesday at 2:00 PM", "purpose": "Cardiac Follow-up"},
            {"doctor": "Dr. Davis (Dentist)", "time": "July 24th at 10:00 AM", "purpose": "Routine cleaning"}
        ]
        return [types.TextContent(type="text", text=json.dumps(apps))]
        
    elif name == "schedule_appointment":
        doc = arguments.get("doctor")
        time = arguments.get("time")
        purpose = arguments.get("purpose", "General follow-up")
        return [types.TextContent(type="text", text=f"Successfully scheduled appointment with {doc} on {time} for {purpose}.")]
        
    elif name == "alert_caregiver":
        alert_type = arguments.get("alert_type")
        msg = arguments.get("message")
        return [types.TextContent(type="text", text=f"CARE-ALERT: Alert of type '{alert_type}' sent to caregiver: '{msg}'.")]
        
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
