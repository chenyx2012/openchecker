import requests
import io
from PIL import Image, ImageDraw, ImageFont
import os


org_name = "OpenHarmony TPC"

font_path = "fonts/HowdyLemon-5yBlz.ttf"
font_size = 80
font = ImageFont.truetype(font_path, font_size)

projects = []

for file in os.listdir("./imgs/flux"):
    if file.endswith(".png"):
        projects.append(file)        

for project_name in projects:
    
    image = Image.open("./imgs/flux/" + project_name)

    # Add text overlay
    draw = ImageDraw.Draw(image)

    text1_width, text1_height = draw.textsize(project_name, font=font)
    text1_x = image.width // 2 - text1_width // 2
    text1_y = image.height * 0.8 - text1_height // 2

    # draw.text((text1_x, text1_y), project_name, font=font, fill=(3, 168, 158))

    text2_width, text2_height = draw.textsize(org_name, font=font)
    text2_x = image.width // 2 - text2_width // 2
    text2_y = image.height * 0.8 - text2_height // 2 + text1_height + 30

    draw.text((text2_x, text2_y), org_name, font=font, fill=(102, 205, 170))

    image.save(f"./imgs/flux-text-color/{project_name}")

    print(f"{project_name} done!")
