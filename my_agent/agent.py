from langchain.globals import set_debug
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from .tools.fastweb import get_invoices_fastweb, get_invoice_fastweb


SYSTEM_PROMPT = """
Sei un agente per scaricare bollette dei fornitori di luce, acqua, telefono e gas.
I gestori che gestisci sono Fastweb, Fastweb Energia, Umbra Acque, Eni Planitude.
Hai a disposizione i seguenti tool per ogni gestore:
- Fastweb:
    - get_invoces_fastweb per visualizarre tutte le bollette
    - get_invoce_fastweb per visualizzare una singola bolletta
"""

set_debug(True)

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
tools = [get_invoices_fastweb, get_invoice_fastweb]
agent_executor = create_react_agent(llm, tools)


def execute(request: str) -> str:
    """
    execute a request using the agent.
    """
    result = agent_executor.invoke(
        {"messages": [SystemMessage(SYSTEM_PROMPT), HumanMessage(f"{request}")]}
    )
    return result.get("messages")[-1].content
