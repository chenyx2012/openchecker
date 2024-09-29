from openai import OpenAI
import requests

client = OpenAI()

project_name = "axios" # aki

prompt1 = f"Design a logo for the {project_name} software project with a simple style, and ensure that the project name is placed below the logo."
prompt2 = f"Design a logo for the {project_name} software project. The logo should be simple in style and must include the project name positioned underneath."
prompt3 = f"Design a logo for the {project_name} software project with white background"

response = client.images.generate(
  model="dall-e-3",
  prompt=prompt1,
  size="1024x1024",
  quality="standard",
  n=1,
)

image_url = response.data[0].url

print(image_url)

response = requests.get(image_url)

if response.status_code == 200:
    with open(f"./{project_name}.png", "wb") as f:
        f.write(response.content)
        print("Image saved successfully.")
else:
    print("Failed to download image.")