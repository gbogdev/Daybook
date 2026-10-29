"""Generate daybook/assets/icon.png and icon.ico (rounded square with a check mark)."""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen

OUT = Path(__file__).resolve().parent.parent / "daybook" / "assets"
SIZES = (16, 32, 48, 64, 128, 256)


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#5b8def"))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    # open book: two white pages meeting at a spine
    p.setBrush(QColor("white"))
    for sign in (-1, 1):
        def pt(x: float, y: float) -> QPointF:
            return QPointF(size * (0.5 + sign * x), size * y)
        page = QPainterPath(pt(0.02, 0.30))
        page.cubicTo(pt(0.14, 0.24), pt(0.28, 0.24), pt(0.34, 0.28))
        page.lineTo(pt(0.34, 0.74))
        page.cubicTo(pt(0.28, 0.70), pt(0.14, 0.70), pt(0.02, 0.76))
        page.closeSubpath()
        p.drawPath(page)
    if size >= 48:  # text lines on the pages
        p.setPen(QPen(QColor("#5b8def"), size * 0.028, Qt.SolidLine, Qt.RoundCap))
        for sign in (-1, 1):
            for y in (0.40, 0.50, 0.60):
                p.drawLine(QPointF(size * (0.5 + sign * 0.10), size * y),
                           QPointF(size * (0.5 + sign * 0.27), size * (y - 0.01)))
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def main() -> None:
    QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    pngs = {s: png_bytes(render(s)) for s in SIZES}
    (OUT / "icon.png").write_bytes(pngs[256])
    header = struct.pack("<HHH", 0, 1, len(SIZES))
    offset = 6 + 16 * len(SIZES)
    entries, blobs = b"", b""
    for s in SIZES:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(pngs[s]), offset)
        blobs += pngs[s]
        offset += len(pngs[s])
    (OUT / "icon.ico").write_bytes(header + entries + blobs)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
