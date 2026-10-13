import openai
import os
import pprint
from langchain_community.llms import OpenAI
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain.agents import load_tools
from langchain.agents import initialize_agent
from dotenv import load_dotenv
load_dotenv()

# load API keys; you will need to obtain these if you haven't yet
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
os.environ["SERPER_API_KEY"] = os.getenv("SERPER_API_KEY")

# llm = OpenAI(model_name="gpt-3.5-turbo-instruct" ,temperature=0)
# tools = load_tools(["google-serper", "llm-math"], llm=llm)
# agent = initialize_agent(tools, llm, agent="zero-shot-react-description", verbose=True)

# agent.run("Who is Olivia Wilde's boyfriend? What is his current age raised to the 0.23 power?")

# search = GoogleSerperAPIWrapper()
# search.run("Obama's first name?")

search = GoogleSerperAPIWrapper(type="images")
results = search.results("Lion")
pprint.pp(results)