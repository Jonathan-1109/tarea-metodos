from google import genai
from dotenv import load_dotenv
from os import getenv

load_dotenv()

apikey = getenv("GEMINI_API_KEY")
client = genai.Client(api_key=apikey)

interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input="Hola"
)
print(interaction.output_text)