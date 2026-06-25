"""
Generate a sample sensor measurement PDF for testing upload/plot APIs.
Run: python scripts/create_sample_sensor_pdf.py
"""
import math
from pathlib import Path

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
except ImportError:
    print("Install reportlab: pip install reportlab")
    raise

OUTPUT = Path(__file__).resolve().parent.parent / "sample_sensor_data.pdf"


def main():
    c = canvas.Canvas(str(OUTPUT), pagesize=letter)
    width, height = letter
    y = height - 50
    lines = ["timestamp,ch0,ch1"]
    fs = 25600
    for i in range(512):
        t = i / fs
        ch0 = 0.5 * math.sin(2 * math.pi * 120 * t) + 0.1 * math.sin(2 * math.pi * 480 * t)
        ch1 = 0.3 * math.sin(2 * math.pi * 60 * t)
        lines.append(f"{t:.6f},{ch0:.6f},{ch1:.6f}")

    c.setFont("Courier", 8)
    for line in lines:
        if y < 40:
            c.showPage()
            c.setFont("Courier", 8)
            y = height - 50
        c.drawString(40, y, line)
        y -= 10

    c.save()
    print(f"Created: {OUTPUT}")


if __name__ == "__main__":
    main()
