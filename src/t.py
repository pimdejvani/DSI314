from openai import OpenAI
import os, json

client = OpenAI(
    base_url=os.getenv("AZURE_OPENAI_BASE_URL"),
    api_key=os.getenv("AZURE_AI_KEY"),
)

def call_phi_openai(messages):
    completion = client.chat.completions.create(
        model=os.getenv("AZURE_AI_MODEL"),  # deployment name
        messages=messages,
        temperature=0,
        max_tokens=20,
    )
    content = completion.choices[0].message.content
    return json.loads(content)

call_phi_openai("what is apple")