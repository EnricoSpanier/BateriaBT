"""
Dibujo vectorial de iconos y baterías con QPainter.

Todo se dibuja en un lienzo lógico de 24×24 escalado al tamaño real, así que se ve nítido
a cualquier escala de pantalla (100 %, 125 %, 150 %…) y adopta el color del tema al instante.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen

DEVICE_KINDS = ("keyboard", "mouse", "headset", "gamepad", "speaker", "phone", "tablet", "watch",
                "computer", "pen", "remote", "microphone", "camera", "tv", "car", "printer", "generic")

# cache (kind, style) -> (stroke, fill)
_icon_cache = {}


def _dot(path, x, y):
    path.moveTo(x, y)
    path.lineTo(x + 0.01, y)


def _line(path, *points):
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)


def _polygon(path, *points):
    _line(path, *points)
    path.closeSubpath()


def _other_device_paths(kind, style, stroke, fill):
    """Iconos de los demás tipos de dispositivo. En `fill`, lo que se solapa queda hueco (la pantalla de un móvil)."""
    filled, minimal = style == "filled", style == "minimal"
    if kind == "phone":
        if filled:
            fill.addRoundedRect(QRectF(6.0, 1.5, 12.0, 21.0), 2.8, 2.8)
            fill.addRoundedRect(QRectF(7.8, 4.0, 8.4, 14.4), 0.8, 0.8)
            fill.addEllipse(QPointF(12.0, 20.3), 1.05, 1.05)
        elif minimal:
            stroke.addRoundedRect(QRectF(7.0, 2.5, 10.0, 19.0), 2.2, 2.2)
            fill.addEllipse(QPointF(12.0, 18.4), 1.0, 1.0)
        else:
            stroke.addRoundedRect(QRectF(6.5, 2.0, 11.0, 20.0), 2.6, 2.6)
            _line(stroke, (10.4, 18.8), (13.6, 18.8))
    elif kind == "tablet":
        if filled:
            fill.addRoundedRect(QRectF(3.5, 1.5, 17.0, 21.0), 2.6, 2.6)
            fill.addRoundedRect(QRectF(5.2, 3.6, 13.6, 15.0), 0.8, 0.8)
            fill.addEllipse(QPointF(12.0, 20.5), 1.05, 1.05)
        elif minimal:
            stroke.addRoundedRect(QRectF(4.5, 2.5, 15.0, 19.0), 2.0, 2.0)
            fill.addEllipse(QPointF(12.0, 18.4), 1.0, 1.0)
        else:
            stroke.addRoundedRect(QRectF(4.0, 2.0, 16.0, 20.0), 2.4, 2.4)
            _line(stroke, (10.2, 18.8), (13.8, 18.8))
    elif kind == "watch":
        if filled:
            fill.addRoundedRect(QRectF(6.0, 6.0, 12.0, 12.0), 3.2, 3.2)
            fill.addRoundedRect(QRectF(8.0, 8.0, 8.0, 8.0), 2.0, 2.0)
            _polygon(fill, (8.6, 6.0), (9.4, 1.8), (14.6, 1.8), (15.4, 6.0))
            _polygon(fill, (8.6, 18.0), (9.4, 22.2), (14.6, 22.2), (15.4, 18.0))
        elif minimal:
            stroke.addRoundedRect(QRectF(7.0, 7.0, 10.0, 10.0), 2.6, 2.6)
            _line(stroke, (10.0, 7.0), (10.0, 3.0))
            _line(stroke, (14.0, 7.0), (14.0, 3.0))
            _line(stroke, (10.0, 17.0), (10.0, 21.0))
            _line(stroke, (14.0, 17.0), (14.0, 21.0))
        else:
            stroke.addRoundedRect(QRectF(6.5, 6.5, 11.0, 11.0), 3.0, 3.0)
            _line(stroke, (9.0, 6.5), (9.6, 2.5), (14.4, 2.5), (15.0, 6.5))
            _line(stroke, (9.0, 17.5), (9.6, 21.5), (14.4, 21.5), (15.0, 17.5))
            _line(stroke, (12.0, 9.4), (12.0, 12.0), (13.8, 13.2))
    elif kind == "computer":
        if filled:
            fill.addRoundedRect(QRectF(4.0, 3.5, 16.0, 13.0), 2.0, 2.0)
            fill.addRoundedRect(QRectF(5.8, 5.3, 12.4, 9.4), 0.6, 0.6)
            fill.addRoundedRect(QRectF(1.5, 17.4, 21.0, 3.1), 1.5, 1.5)
        else:
            stroke.addRoundedRect(QRectF(4.5, 4.5, 15.0, 11.0), 1.8, 1.8)
            _line(stroke, (2.2, 19.0), (21.8, 19.0))
    elif kind == "pen":
        shape = ((16.8, 3.2), (20.8, 7.2), (8.8, 19.2), (3.8, 20.2), (4.8, 15.2))
        if filled:
            _polygon(fill, *shape)
        else:
            _polygon(stroke, *shape)
            if not minimal:
                _line(stroke, (14.4, 5.6), (18.4, 9.6))
    elif kind == "remote":
        if filled:
            fill.addRoundedRect(QRectF(7.5, 1.5, 9.0, 21.0), 2.8, 2.8)
            fill.addEllipse(QPointF(12.0, 6.6), 1.9, 1.9)
            for y in (11.4, 14.6, 17.8):
                fill.addRoundedRect(QRectF(10.2, y, 3.6, 1.6), 0.7, 0.7)
        elif minimal:
            stroke.addRoundedRect(QRectF(8.0, 2.5, 8.0, 19.0), 2.4, 2.4)
            fill.addEllipse(QPointF(12.0, 7.0), 1.4, 1.4)
        else:
            stroke.addRoundedRect(QRectF(8.0, 2.0, 8.0, 20.0), 2.6, 2.6)
            stroke.addEllipse(QPointF(12.0, 6.8), 1.5, 1.5)
            for y in (11.6, 14.6, 17.6):
                _dot(stroke, 12.0, y)
    elif kind == "microphone":
        if filled:
            fill.addRoundedRect(QRectF(8.4, 2.0, 7.2, 12.5), 3.6, 3.6)
        else:
            stroke.addRoundedRect(QRectF(8.8, 2.5, 6.4, 11.5), 3.2, 3.2)
        stroke.moveTo(5.2, 11.5)
        stroke.cubicTo(5.2, 20.0, 18.8, 20.0, 18.8, 11.5)
        _line(stroke, (12.0, 17.8), (12.0, 21.5))
        if not minimal:
            _line(stroke, (8.6, 21.5), (15.4, 21.5))
    elif kind == "camera":
        if filled:
            fill.addRoundedRect(QRectF(2.0, 7.0, 20.0, 13.5), 2.8, 2.8)
            fill.addEllipse(QPointF(12.0, 13.6), 3.7, 3.7)
            _polygon(fill, (8.0, 7.0), (9.4, 4.0), (14.6, 4.0), (16.0, 7.0))
        else:
            stroke.addRoundedRect(QRectF(2.5, 7.0, 19.0, 13.2), 2.6, 2.6)
            stroke.addEllipse(QPointF(12.0, 13.6), 3.5, 3.5)
            if not minimal:
                _line(stroke, (8.2, 7.0), (9.6, 4.2), (14.4, 4.2), (15.8, 7.0))
    elif kind == "tv":
        if filled:
            fill.addRoundedRect(QRectF(2.0, 4.0, 20.0, 14.0), 2.2, 2.2)
            fill.addRoundedRect(QRectF(3.9, 5.9, 16.2, 10.2), 0.6, 0.6)
        else:
            stroke.addRoundedRect(QRectF(2.5, 4.5, 19.0, 13.0), 2.0, 2.0)
        _line(stroke, (7.8, 21.0), (16.2, 21.0))
        if not minimal:
            _line(stroke, (12.0, 17.5), (12.0, 21.0))
    elif kind == "car":
        if filled:
            fill.addRoundedRect(QRectF(2.2, 11.4, 19.6, 6.4), 2.2, 2.2)
            _polygon(fill, (5.0, 11.4), (7.0, 5.6), (17.0, 5.6), (19.0, 11.4))
            fill.addEllipse(QPointF(7.0, 19.6), 1.7, 1.7)
            fill.addEllipse(QPointF(17.0, 19.6), 1.7, 1.7)
        else:
            stroke.addRoundedRect(QRectF(2.8, 11.5, 18.4, 6.0), 2.2, 2.2)
            _line(stroke, (5.2, 11.5), (7.2, 6.0), (16.8, 6.0), (18.8, 11.5))
            fill.addEllipse(QPointF(7.0, 19.8), 1.6, 1.6)
            fill.addEllipse(QPointF(17.0, 19.8), 1.6, 1.6)
            if not minimal:
                _dot(stroke, 6.4, 14.5)
                _dot(stroke, 17.6, 14.5)
    elif kind == "printer":
        if filled:
            fill.addRoundedRect(QRectF(2.2, 8.6, 19.6, 9.2), 2.2, 2.2)
            fill.addRect(QRectF(7.0, 3.2, 10.0, 5.4))
            fill.addRect(QRectF(7.0, 14.2, 10.0, 3.6))
            fill.addRect(QRectF(7.0, 17.8, 10.0, 3.2))
        else:
            stroke.addRoundedRect(QRectF(2.8, 8.8, 18.4, 8.6), 2.0, 2.0)
            _line(stroke, (7.0, 8.8), (7.0, 3.5), (17.0, 3.5), (17.0, 8.8))
            _polygon(stroke, (7.0, 14.4), (17.0, 14.4), (17.0, 20.5), (7.0, 20.5))
            if not minimal:
                _dot(stroke, 17.8, 11.6)
    else:
        return False
    return True


def _device_paths(kind, style="outline"):
    """Devuelve (trazo, relleno) del icono en coordenadas 24×24 según el estilo elegido."""
    cache_key = (kind, style)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]
    stroke, fill = QPainterPath(), QPainterPath()

    if _other_device_paths(kind, style, stroke, fill):
        pass
    elif style == "filled":
        if kind == "keyboard":
            fill.setFillRule(Qt.OddEvenFill)
            fill.addRoundedRect(QRectF(2.0, 5.0, 20.0, 14.0), 3.0, 3.0)
            for x in (4.2, 8.2, 12.2, 16.2):
                fill.addRoundedRect(QRectF(x, 7.5, 3.2, 2.3), 0.7, 0.7)
            for x in (4.2, 8.2, 12.2, 16.2):
                fill.addRoundedRect(QRectF(x, 11.0, 3.2, 2.3), 0.7, 0.7)
            fill.addRoundedRect(QRectF(6.5, 14.5, 11.0, 2.2), 0.8, 0.8)
        elif kind == "mouse":
            fill.setFillRule(Qt.OddEvenFill)
            fill.addRoundedRect(QRectF(6.0, 2.0, 12.0, 20.0), 6.0, 6.0)
            fill.addRoundedRect(QRectF(11.0, 4.8, 2.0, 5.4), 1.0, 1.0)
            fill.addRect(QRectF(11.5, 10.5, 1.0, 2.5))
        elif kind == "headset":
            stroke.moveTo(4.5, 14.0)
            stroke.lineTo(4.5, 11.0)
            stroke.arcTo(QRectF(4.5, 3.5, 15.0, 15.0), 180, -180)
            stroke.lineTo(19.5, 14.0)
            fill.addRoundedRect(QRectF(2.0, 11.0, 5.5, 9.5), 2.6, 2.6)
            fill.addRoundedRect(QRectF(16.5, 11.0, 5.5, 9.5), 2.6, 2.6)
        elif kind == "gamepad":
            fill.setFillRule(Qt.OddEvenFill)
            fill.addRoundedRect(QRectF(2.0, 6.0, 20.0, 12.5), 6.0, 6.0)
            fill.addRect(QRectF(5.5, 11.2, 4.6, 1.8))
            fill.addRect(QRectF(6.9, 9.8, 1.8, 4.6))
            fill.addEllipse(QPointF(15.5, 10.8), 1.15, 1.15)
            fill.addEllipse(QPointF(18.0, 13.0), 1.15, 1.15)
        elif kind == "speaker":
            fill.setFillRule(Qt.OddEvenFill)
            fill.addRoundedRect(QRectF(5.0, 2.0, 14.0, 20.0), 3.0, 3.0)
            fill.addEllipse(QPointF(12.0, 6.8), 1.8, 1.8)
            fill.addEllipse(QPointF(12.0, 14.8), 4.2, 4.2)
        else:
            # genérico: símbolo Bluetooth
            stroke.moveTo(7.0, 7.5)
            stroke.lineTo(16.8, 16.3)
            stroke.lineTo(12.0, 20.8)
            stroke.lineTo(12.0, 3.2)
            stroke.lineTo(16.8, 7.7)
            stroke.lineTo(7.0, 16.5)
            fill.addEllipse(QPointF(12.0, 12.0), 2.0, 2.0)
    elif style == "minimal":
        if kind == "keyboard":
            stroke.addRoundedRect(QRectF(3.0, 6.5, 18.0, 11.0), 2.2, 2.2)
            stroke.moveTo(5.5, 12.0)
            stroke.lineTo(18.5, 12.0)
            stroke.moveTo(9.5, 6.5)
            stroke.lineTo(9.5, 12.0)
            stroke.moveTo(14.5, 6.5)
            stroke.lineTo(14.5, 12.0)
        elif kind == "mouse":
            stroke.addRoundedRect(QRectF(7.0, 3.0, 10.0, 18.0), 5.0, 5.0)
            fill.addEllipse(QPointF(12.0, 8.0), 1.3, 1.3)
        elif kind == "headset":
            stroke.arcMoveTo(QRectF(4.0, 4.0, 16.0, 16.0), 200)
            stroke.arcTo(QRectF(4.0, 4.0, 16.0, 16.0), 200, -220)
            stroke.addRoundedRect(QRectF(3.0, 12.0, 3.2, 8.0), 1.6, 1.6)
            stroke.addRoundedRect(QRectF(17.8, 12.0, 3.2, 8.0), 1.6, 1.6)
        elif kind == "gamepad":
            stroke.addRoundedRect(QRectF(3.0, 7.0, 18.0, 11.0), 5.5, 5.5)
            fill.addEllipse(QPointF(8.0, 13.0), 1.5, 1.5)
            fill.addEllipse(QPointF(16.0, 13.0), 1.5, 1.5)
        elif kind == "speaker":
            stroke.addRoundedRect(QRectF(6.0, 3.0, 12.0, 18.0), 2.5, 2.5)
            stroke.addEllipse(QPointF(12.0, 14.0), 3.0, 3.0)
        else:
            stroke.moveTo(7.5, 7.5)
            stroke.lineTo(16.5, 16.0)
            stroke.lineTo(12.0, 20.5)
            stroke.lineTo(12.0, 3.5)
            stroke.lineTo(16.5, 8.0)
            stroke.lineTo(7.5, 16.5)
    else:  # "outline"
        if kind == "keyboard":
            stroke.addRoundedRect(QRectF(2.5, 6.0, 19.0, 12.0), 2.6, 2.6)
            for x in (6.5, 10.2, 13.8, 17.5):
                _dot(stroke, x, 10.0)
            _dot(stroke, 6.5, 14.0)
            _dot(stroke, 17.5, 14.0)
            stroke.moveTo(9.3, 14.0)
            stroke.lineTo(14.7, 14.0)
        elif kind == "mouse":
            stroke.addRoundedRect(QRectF(6.5, 2.5, 11.0, 19.0), 5.5, 5.5)
            stroke.moveTo(12.0, 6.3)
            stroke.lineTo(12.0, 9.3)
        elif kind == "headset":
            stroke.moveTo(4.8, 14.0)
            stroke.lineTo(4.8, 11.5)
            stroke.arcTo(QRectF(4.8, 4.3, 14.4, 14.4), 180, -180)
            stroke.lineTo(19.2, 14.0)
            fill.addRoundedRect(QRectF(3.0, 12.6, 4.8, 8.2), 2.0, 2.0)
            fill.addRoundedRect(QRectF(16.2, 12.6, 4.8, 8.2), 2.0, 2.0)
        elif kind == "gamepad":
            stroke.addRoundedRect(QRectF(2.5, 6.8, 19.0, 11.4), 5.7, 5.7)
            stroke.moveTo(7.6, 10.4)
            stroke.lineTo(7.6, 14.6)
            stroke.moveTo(5.5, 12.5)
            stroke.lineTo(9.7, 12.5)
            fill.addEllipse(QPointF(15.8, 11.2), 1.25, 1.25)
            fill.addEllipse(QPointF(18.1, 13.7), 1.25, 1.25)
        elif kind == "speaker":
            stroke.addRoundedRect(QRectF(6.0, 2.5, 12.0, 19.0), 3.0, 3.0)
            stroke.addEllipse(QPointF(12.0, 14.6), 3.3, 3.3)
            fill.addEllipse(QPointF(12.0, 7.4), 1.2, 1.2)
        else:
            stroke.moveTo(7.3, 7.6)
            stroke.lineTo(16.6, 16.2)
            stroke.lineTo(12.0, 20.6)
            stroke.lineTo(12.0, 3.4)
            stroke.lineTo(16.6, 7.8)
            stroke.lineTo(7.3, 16.4)

    _icon_cache[cache_key] = (stroke, fill)
    return stroke, fill


def _begin_box(p: QPainter, rect: QRectF, box=24.0):
    s = min(rect.width(), rect.height()) / box
    p.translate(rect.x() + (rect.width() - box * s) / 2, rect.y() + (rect.height() - box * s) / 2)
    p.scale(s, s)
    return s


def _pen(color, width):
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def draw_device_icon(p: QPainter, rect: QRectF, kind: str, color, weight=1.8, style="outline"):
    stroke, fill = _device_paths(kind if kind in DEVICE_KINDS else "generic", style=style)
    p.save()
    _begin_box(p, rect)
    p.setPen(_pen(color, weight))
    p.setBrush(Qt.NoBrush)
    if not stroke.isEmpty():
        p.drawPath(stroke)
    if not fill.isEmpty():
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawPath(fill)
    p.restore()


_BOLT = ((6.2, 0.0), (0.6, 9.3), (4.7, 9.3), (3.8, 16.0), (9.4, 6.4), (5.3, 6.4))


def bolt_path(rect: QRectF) -> QPainterPath:
    """Rayo centrado en `rect` manteniendo su proporción 10:16."""
    s = min(rect.width() / 10.0, rect.height() / 16.0)
    ox = rect.x() + (rect.width() - 10.0 * s) / 2
    oy = rect.y() + (rect.height() - 16.0 * s) / 2
    path = QPainterPath()
    path.moveTo(ox + _BOLT[0][0] * s, oy + _BOLT[0][1] * s)
    for x, y in _BOLT[1:]:
        path.lineTo(ox + x * s, oy + y * s)
    path.closeSubpath()
    return path


def draw_bolt(p: QPainter, rect: QRectF, fill, outline=None, outline_width=1.2):
    path = bolt_path(rect)
    p.save()
    if outline is not None:
        pen = _pen(outline, outline_width * 2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(fill))
    p.drawPath(path)
    p.restore()


def draw_battery(p: QPainter, rect: QRectF, level, fill, outline, track=None,
                 charging=False, phase=0.0, bolt_fill="#FFFFFF", bolt_outline=None):
    """
    Pila horizontal. `level` 0–100 (None = desconocido). Si `charging`, dibuja un rayo y un
    brillo que recorre el relleno según `phase` (0–1) para indicar la carga en curso.
    """
    h = rect.height()
    nub_w = max(1.6, h * 0.16)
    gap = max(0.8, h * 0.07)
    body = QRectF(rect.x(), rect.y(), rect.width() - nub_w - gap, h)
    stroke = max(1.0, h * 0.1)
    radius = h * 0.27

    p.save()
    outline_c = QColor(outline)
    p.setPen(QPen(outline_c, stroke))
    p.setBrush(QColor(track) if track is not None else Qt.NoBrush)
    half = stroke / 2
    p.drawRoundedRect(body.adjusted(half, half, -half, -half), radius, radius)

    nub_h = h * 0.4
    p.setPen(Qt.NoPen)
    p.setBrush(outline_c)
    p.drawRoundedRect(QRectF(body.right() + gap, rect.center().y() - nub_h / 2, nub_w, nub_h),
                      nub_w * 0.45, nub_w * 0.45)

    pad = stroke + max(0.8, h * 0.08)
    inner = body.adjusted(pad, pad, -pad, -pad)
    if level is not None and fill is not None and inner.width() > 0:
        level = max(0, min(100, int(level)))
        width = inner.width() * level / 100.0
        if level > 0:
            width = max(width, min(inner.width(), max(1.3, h * 0.13)))
        fill_rect = QRectF(inner.x(), inner.y(), width, inner.height())
        inner_radius = max(0.6, radius * 0.5)
        p.setBrush(QColor(fill))
        p.drawRoundedRect(fill_rect, inner_radius, inner_radius)
        if charging and width > 2:
            # brilho que percorre o preenchimento
            band = max(inner.width() * 0.5, 4.0)
            x = inner.x() - band + (inner.width() + band) * (phase % 1.0)
            grad = QLinearGradient(x, 0, x + band, 0)
            grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            grad.setColorAt(0.5, QColor(255, 255, 255, 110))
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setClipRect(fill_rect)
            p.setBrush(grad)
            p.drawRect(fill_rect)
            p.setClipping(False)

    if charging:
        bh = h * 1.02
        bw = bh * 10.0 / 16.0
        bolt_rect = QRectF(body.center().x() - bw / 2, rect.center().y() - bh / 2, bw, bh)
        draw_bolt(p, bolt_rect, bolt_fill, bolt_outline, outline_width=max(0.8, h * 0.08))
    p.restore()


def draw_battery_vertical(p: QPainter, rect: QRectF, level, fill, outline, track=None,
                          charging=False, phase=0.0, bolt_fill="#FFFFFF", bolt_outline=None):
    """
    Pila vertical. `level` 0–100 (None = desconocido). Borne arriba, cuerpo rellenado desde abajo
    hacia arriba. Si `charging`, dibuja un rayo adaptado y un brillo ascendente según `phase` (0–1).
    """
    w = rect.width()
    h = rect.height()
    nub_h = max(1.5, h * 0.12)
    gap = max(0.6, h * 0.05)
    nub_w = max(3.0, w * 0.44)
    body = QRectF(rect.x(), rect.y() + nub_h + gap, w, h - nub_h - gap)
    stroke = max(1.0, w * 0.11)
    radius = max(1.8, w * 0.28)

    p.save()
    outline_c = QColor(outline)
    p.setPen(QPen(outline_c, stroke))
    p.setBrush(QColor(track) if track is not None else Qt.NoBrush)
    half = stroke / 2.0
    p.drawRoundedRect(body.adjusted(half, half, -half, -half), radius, radius)

    # borne em cima
    p.setPen(Qt.NoPen)
    p.setBrush(outline_c)
    p.drawRoundedRect(QRectF(rect.center().x() - nub_w / 2.0, rect.top(), nub_w, nub_h),
                      nub_w * 0.35, nub_w * 0.35)

    pad = stroke + max(0.6, w * 0.08)
    inner = body.adjusted(pad, pad, -pad, -pad)
    if level is not None and fill is not None and inner.height() > 0:
        level = max(0, min(100, int(level)))
        fill_h = inner.height() * level / 100.0
        if level > 0:
            fill_h = max(fill_h, min(inner.height(), max(1.3, w * 0.15)))
        fill_rect = QRectF(inner.x(), inner.bottom() - fill_h, inner.width(), fill_h)
        inner_radius = max(0.6, radius * 0.5)
        p.setBrush(QColor(fill))
        p.drawRoundedRect(fill_rect, inner_radius, inner_radius)
        if charging and fill_h > 2:
            band = max(inner.height() * 0.5, 4.0)
            y = inner.bottom() + band - (inner.height() + band) * (phase % 1.0)
            grad = QLinearGradient(0, y, 0, y - band)
            grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            grad.setColorAt(0.5, QColor(255, 255, 255, 110))
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setClipRect(fill_rect)
            p.setBrush(grad)
            p.drawRect(fill_rect)
            p.setClipping(False)

    if charging:
        bh = min(body.height() * 0.82, max(8.0, h * 0.62))
        bw = bh * 10.0 / 16.0
        bolt_rect = QRectF(body.center().x() - bw / 2.0, body.center().y() - bh / 2.0, bw, bh)
        draw_bolt(p, bolt_rect, bolt_fill, bolt_outline, outline_width=max(0.8, w * 0.09))
    p.restore()


def draw_chevron(p: QPainter, center: QPointF, size: float, color, down=True, weight=1.6):
    p.save()
    p.setPen(_pen(color, weight))
    dy = size * 0.28 if down else -size * 0.28
    path = QPainterPath()
    path.moveTo(center.x() - size / 2, center.y() - dy)
    path.lineTo(center.x(), center.y() + dy)
    path.lineTo(center.x() + size / 2, center.y() - dy)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.restore()


def draw_close(p: QPainter, rect: QRectF, color, weight=1.6):
    p.save()
    p.setPen(_pen(color, weight))
    m = rect.width() * 0.3
    p.drawLine(QPointF(rect.left() + m, rect.top() + m), QPointF(rect.right() - m, rect.bottom() - m))
    p.drawLine(QPointF(rect.right() - m, rect.top() + m), QPointF(rect.left() + m, rect.bottom() - m))
    p.restore()


def draw_refresh(p: QPainter, rect: QRectF, color, angle=0.0, weight=1.7):
    """Flecha circular; `angle` en grados permite animarla girando."""
    p.save()
    c = rect.center()
    p.translate(c)
    p.rotate(angle)
    r = min(rect.width(), rect.height()) * 0.3
    p.setPen(_pen(color, weight))
    p.setBrush(Qt.NoBrush)
    arc = QRectF(-r, -r, 2 * r, 2 * r)
    p.drawArc(arc, 960, 4480)  # 60° .. 340° (unidades de 1/16°)
    tip = QPointF(r * math.cos(math.radians(60)), -r * math.sin(math.radians(60)))
    head = r * 0.62
    path = QPainterPath()
    path.moveTo(tip.x() - head * 0.95, tip.y() - head * 0.35)
    path.lineTo(tip.x(), tip.y())
    path.lineTo(tip.x() - head * 0.1, tip.y() + head * 0.95)
    p.drawPath(path)
    p.restore()


def draw_eye(p: QPainter, rect: QRectF, color, crossed=False, weight=1.6):
    p.save()
    _begin_box(p, rect)
    p.setPen(_pen(color, weight))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(3.0, 12.0)
    path.cubicTo(6.5, 6.3, 17.5, 6.3, 21.0, 12.0)
    path.cubicTo(17.5, 17.7, 6.5, 17.7, 3.0, 12.0)
    p.drawPath(path)
    p.drawEllipse(QPointF(12.0, 12.0), 2.8, 2.8)
    if crossed:
        p.drawLine(QPointF(4.5, 4.5), QPointF(19.5, 19.5))
    p.restore()


def draw_app_glyph(p: QPainter, rect: QRectF, accent, bg, fg, level_color="#10B981"):
    """Logotipo de la app: pila con rayo sobre fondo redondeado."""
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(bg))
    rad = rect.width() * 0.26
    p.drawRoundedRect(rect, rad, rad)
    bw = rect.width() * 0.66
    bh = rect.height() * 0.36
    br = QRectF(rect.center().x() - bw / 2, rect.center().y() - bh / 2, bw, bh)
    draw_battery(p, br, 70, level_color, accent, None, charging=True, bolt_fill=fg, bolt_outline=bg)
    p.restore()


def draw_lock(p: QPainter, rect: QRectF, color, open_shackle=False, weight=1.4):
    """Candado vectorial nítido para opciones e indicadores Pro."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    w, h = rect.width(), rect.height()
    side = min(w, h)
    cx, cy = rect.center().x(), rect.center().y()
    bw = side * 0.72
    bh = side * 0.5
    bx = cx - bw / 2.0
    by = cy + side * 0.5 - bh
    sw = bw * 0.62
    sh = side * 0.46
    sx = cx - sw / 2.0
    sy = by - sh + 1.5
    pen_w = max(1.2, side * 0.13)  # `weight` não é usado no original
    p.setPen(QPen(QColor(color), pen_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    shackle = QPainterPath()
    shackle.moveTo(sx + pen_w / 2, by + 1.0)
    shackle.lineTo(sx + pen_w / 2, sy + sw / 2)
    shackle.arcTo(QRectF(sx + pen_w / 2, sy, sw - pen_w, sw - pen_w), 180, -180)
    if open_shackle:
        shackle.lineTo(sx + sw - pen_w / 2, sy + sw / 2)
    else:
        shackle.lineTo(sx + sw - pen_w / 2, by + 1.0)
    p.drawPath(shackle)
    body_rect = QRectF(bx, by, bw, bh)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    radius = max(1.5, bw * 0.2)
    p.drawRoundedRect(body_rect, radius, radius)
    hole_c = QColor(0, 0, 0, 160)
    p.setBrush(hole_c)
    kr = max(1.0, bw * 0.12)
    p.drawEllipse(QRectF(cx - kr, by + bh * 0.35 - kr, kr * 2, kr * 2))
    slit = QPainterPath()
    slit.moveTo(cx - kr * 0.6, by + bh * 0.35)
    slit.lineTo(cx + kr * 0.6, by + bh * 0.35)
    slit.lineTo(cx + kr * 0.4, by + bh * 0.72)
    slit.lineTo(cx - kr * 0.4, by + bh * 0.72)
    slit.closeSubpath()
    p.drawPath(slit)
    p.restore()
