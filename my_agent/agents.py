from google.adk import Agent
from vertexai.preview.reasoning_engines.templates.adk import AdkApp

agent = Agent(
    name='my_agent',
    model='gemini-2.0-flash'
)
app = AdkApp(agent=agent)
