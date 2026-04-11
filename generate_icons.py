"""
Run this once to generate PWA icons:
  python generate_icons.py

Requires Pillow:
  pip install Pillow
"""

from PIL import Image, ImageDraw, ImageFont
import os

os.makedirs("static/icons", exist_ok=True)

def make_icon(size, path):
    img = Image.new("RGBA", (size, size), "#0d0f14")
    draw = ImageDraw.Draw(img)

    # Yellow rounded square background
    margin = int(size * 0.1)
    radius = int(size * 0.22)
    x0, y0, x1, y1 = margin, margin, size - margin, size - margin

    # Draw rounded rectangle
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill="#f5c518")

    # Draw "P" letter
    font_size = int(size * 0.55)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()

    text = "P"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0]
    ty = (size - th) // 2 - bbox[1]
    draw.text((tx, ty), text, fill="#0d0f14", font=font)

    img.save(path, "PNG")
    print(f"Created {path}")

make_icon(192, "static/icons/icon-192.png")
make_icon(512, "static/icons/icon-512.png")
print("Icons generated successfully!")
