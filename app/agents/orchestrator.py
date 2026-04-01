# Agent quản lý luồng (nếu có nhiều Agent làm việc với nhau)
from google.adk.agents import SequentialAgent

from app.agents.base_agent import interactive_agent
from app.utils.load_instruction_from_file import load_instruction_from_file

flow_orchestrator_agent = SequentialAgent(
    name="Flow_Orchestrator_Agent",
    sub_agents=[interactive_agent],
    description=load_instruction_from_file("prompts/flow_orchestrator_agent.md")
)