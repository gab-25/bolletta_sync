from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """
Sei un agente per eseguire scraping nei siti di fornitori luce, acqua, telefono e gas.
I gestori che gestisci sono Fastweb, Fastweb Energia, Umbra Acque, Eni Planitude.
"""

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
tools = []
prompt = ChatPromptTemplate([SystemMessage(SYSTEM_PROMPT), HumanMessage("{request}")])
agent = create_react_agent(llm, tools, prompt=prompt)


def execute(request: str) -> str:
    result = agent.invoke({"request": request})
    return result.get("messages")[-1].content
