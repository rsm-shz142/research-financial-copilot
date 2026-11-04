from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda, RunnableSerializable
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from agents.financial_tools import review_transactions
from agents.grant_monitoring import (
    create_review_case,
    forecast_grant_spending,
    generate_financial_review_report,
    monitor_grant_budget,
    monitor_grant_deadlines,
    transition_review_case,
)
from agents.grant_policies import (
    screen_grant_transactions,
    search_grant_policies,
    verify_policy_claim,
)
from core import get_model
from schema.models import OllamaModelName

FINANCIAL_COPILOT_MODEL = OllamaModelName.OLLAMA_GENERIC


class AgentState(MessagesState):
    pass


tools = [
    review_transactions,
    search_grant_policies,
    verify_policy_claim,
    screen_grant_transactions,
    monitor_grant_budget,
    forecast_grant_spending,
    monitor_grant_deadlines,
    generate_financial_review_report,
    create_review_case,
    transition_review_case,
]


def wrap_model(model: BaseChatModel) -> RunnableSerializable:
    bound_model = model.bind_tools(tools)
    preprocessor = RunnableLambda(
        lambda state: [
            SystemMessage(
                content=(
                    "You are a financial copilot that reviews synthetic transaction CSV files. "
                    "For synthetic audits, omit csv_path or use exactly data/sample_transactions.csv; "
                    "csv_path is a file path and must never be constructed from grant_id. "
                    "grant_id independently filters transactions and is not a filename. "
                    "If a caller supplies a missing path, report the structured tool error and do not retry "
                    "with an invented grants/<grant_id>.csv path. "
                    "Use policy tools to retrieve source-grounded research grant requirements. "
                    "Never search policies using a grant ID; use expenditure categories, "
                    "financial indicators, or regulatory questions instead. "
                    "Keep financial anomalies separate from potential compliance issues; never "
                    "state that a violation is confirmed without sufficient evidence."
                )
            ),
            *state["messages"],
        ],
        name="StateModifier",
    )
    return preprocessor | bound_model


async def acall_model(state: AgentState, config: RunnableConfig) -> AgentState:
    model = get_model(config["configurable"].get("model", FINANCIAL_COPILOT_MODEL))
    response = await wrap_model(model).ainvoke(state, config)
    return {"messages": [response]}


def pending_tool_calls(state: AgentState) -> Literal["tools", "done"]:
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage):
        raise TypeError(f"Expected AIMessage, got {type(last_message)}")
    return "tools" if last_message.tool_calls else "done"


agent = StateGraph(AgentState)
agent.add_node("model", acall_model)
agent.add_node("tools", ToolNode(tools))
agent.set_entry_point("model")
agent.add_edge("tools", "model")
agent.add_conditional_edges("model", pending_tool_calls, {"tools": "tools", "done": END})

financial_copilot = agent.compile()
