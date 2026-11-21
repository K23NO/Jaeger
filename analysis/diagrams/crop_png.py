"""Crops white margins of diagram_<n>.png and saves the report names."""
import os
from PIL import Image, ImageChops
HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {1: "electronic_architecture.png", 2: "program_flowchart.png", 3: "base_cascade_control.png", 4: "ball_position_control.png"}
for n, name in NAMES.items():
    im = Image.open(os.path.join(HERE, f"diagram_{n}.png")).convert("RGB")
    bbox = ImageChops.difference(im, Image.new("RGB", im.size, "white")).getbbox()
    pad = 30
    im.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(im.width, bbox[2] + pad), min(im.height, bbox[3] + pad))).save(os.path.join(HERE, name))
    os.remove(os.path.join(HERE, f"diagram_{n}.png"))
    print(name)
