"""Synthetic, nonpersonal images for a repeatable API compatibility check."""
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def make_quiz(lines):
    font_file = Path("C:/Windows/Fonts/segoeui.ttf")
    font = ImageFont.truetype(str(font_file), 26) if font_file.exists() else ImageFont.load_default(size=26)
    image = Image.new("RGB", (1000, 60 + len(lines) * 44), "white")
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((24, 20 + index * 44), line, font=font, fill="black")
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def cases(base):
    result = [
        ("one-question", make_quiz(["Q1. What is 2 + 2?", "A) 3    B) 4    C) 5    D) 6"]), "B"),
        ("two-questions", make_quiz(["Q1. How many centimeters are in 1 meter?",
            "A) 10    B) 100    C) 1000    D) 1", "",
            "Q2. Which number is prime?", "A) 4    B) 9    C) 11    D) 15"]), "Q1: B\nQ2: C"),
    ]
    reference = Path(base) / "samples" / "questions-3.png"
    if reference.exists():
        result.append(("three-questions", reference.read_bytes(), "A2: 4\nA3: 1\nA4: 2"))
    else:
        result.append(("three-questions", make_quiz(["A2. How many millimeters are in 6 cm and 1 mm?",
            "1) 7 mm    2) 60 mm    3) 16 mm    4) 61 mm", "",
            "A3. How many decimeters are in 7 meters?", "1) 70 dm    2) 7 dm    3) 7 cm    4) 70 cm", "",
            "A4. Which number comes immediately after 89?", "1) 87    2) 90    3) 88    4) 80"]),
            "A2: 4\nA3: 1\nA4: 2"))
    return result
