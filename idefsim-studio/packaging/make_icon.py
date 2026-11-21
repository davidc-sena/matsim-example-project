"""Gera idefsim/resources/icon.png (1024 px) com os símbolos IDEF-SIM.

Uso:  python packaging/make_icon.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen  # noqa: E402

from idefsim.gui import shapes  # noqa: E402
from idefsim.model import ConnectionKind as CK, ElementKind as EK  # noqa: E402

app = QGuiApplication([])
S = 1024
img = QImage(S, S, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
bg = QPainterPath()
bg.addRoundedRect(QRectF(40, 40, S - 80, S - 80), 190, 190)
p.fillPath(bg, QBrush(QColor("#1f4e8c")))
p.translate(S / 2 + 42, S / 2)
p.scale(4.2, 4.2)
# entidade --(entrada)--> função, recurso por baixo
shapes.paint_node(p, EK.ENTITY, QRectF(-100, -42, 44, 44), "", show_name=False)
shapes.paint_node(p, EK.FUNCTION, QRectF(-28, -48, 108, 56), "", show_name=False)
shapes.draw_link(p, CK.ENTRY, [QPointF(-55, -20), QPointF(-29, -20)], QColor("white"), scale=0.9)
shapes.draw_link(p, CK.RESOURCE, [QPointF(26, 52), QPointF(26, 9)], QColor("white"), scale=1.1)
p.setPen(QPen(QColor("white"), 3))
p.drawLine(QPointF(4, 52), QPointF(48, 52))
p.end()
out = ROOT / "idefsim" / "resources" / "icon.png"
img.save(str(out))
print("ícone salvo em", out)
