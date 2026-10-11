from django import template

register = template.Library()

SEVERITY_LABELS = {"critica": "Crítico", "alta": "Alto", "media": "Médio", "baixa": "Baixo"}


@register.filter
def severity_label(value):
    return SEVERITY_LABELS.get(value, value)


@register.filter
def seconds(ms):
    if ms in (None, ""):
        return "—"
    return f"{float(ms) / 1000:.1f}".replace(".", ",") + " s"


@register.filter
def megabytes(value):
    if not value:
        return "—"
    return f"{float(value) / 1_000_000:.1f}".replace(".", ",") + " MB"


@register.filter
def gauge_offset(score, circumference=282.7):
    """stroke-dashoffset do velocímetro (arco de 0 a 100)."""
    # Devolve texto: um float passaria pela localização pt-BR e viraria "90,5", inválido no SVG.
    try:
        return f"{circumference * (1 - float(score or 0) / 100):.1f}"
    except (TypeError, ValueError):
        return f"{circumference:.1f}"


@register.simple_tag
def box_style(box, captura):
    """Posiciona a marcação sobre a captura em porcentagem, independente do tamanho exibido."""
    width = (captura or {}).get("largura") or 1440
    height = (captura or {}).get("altura") or 900
    left = box["x"] / width * 100
    top = box["y"] / height * 100
    w = max(box["w"] / width * 100, 1.5)
    h = max(box["h"] / height * 100, 0.6)
    return f"left:{left:.2f}%;top:{top:.2f}%;width:{w:.2f}%;height:{h:.2f}%"


@register.filter
def visible_boxes(boxes, captura):
    height = (captura or {}).get("altura") or 900
    return [b for b in (boxes or []) if b.get("y", 0) < height]


@register.simple_tag
def crop_style(boxes, captura, window_ratio=0.625):
    """Desloca uma captura de página inteira para mostrar a região da primeira marcação."""
    width = (captura or {}).get("largura") or 1440
    height = (captura or {}).get("altura") or 900
    if not boxes:
        return ""
    window = width * float(window_ratio)
    y = max(0, min(b["y"] for b in boxes) - window * 0.15)
    y = min(y, max(0, height - window))
    return f"transform:translateY(-{y / height * 100:.2f}%)"
