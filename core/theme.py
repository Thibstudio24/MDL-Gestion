"""Charte visuelle : 6 palettes × clair/sombre + palette dérivée « couleurs du lycée ».

Aucun fichier CSS de thème figé : la vue ``/theme.css`` sert ``build_css()``.
"""
from __future__ import annotations

import colorsys
from collections import OrderedDict

PALETTES: OrderedDict[str, dict] = OrderedDict(
    [
        (
            "ardoise",
            {
                "label": "Ardoise — Bleu acier sobre",
                "light": {"bg": "#eef1f4", "surface": "#ffffff", "border": "#d3dbe3", "text": "#1d2732",
                          "primary": "#33556e", "accent": "#a76a43"},
                "dark": {"bg": "#12171c", "surface": "#1a2129", "border": "#33404c", "text": "#e4eaf0",
                         "primary": "#7ba7c9", "accent": "#d99a72"},
                "charts": ["#33556e", "#a76a43", "#2c6f52", "#96700f", "#3a6d94", "#7a4f6d", "#5c7f99", "#c2a878"],
            },
        ),
        (
            "canard",
            {
                "label": "Canard & sable",
                "light": {"bg": "#eef4f3", "surface": "#ffffff", "border": "#cfe0de", "text": "#123034",
                          "primary": "#17656f", "accent": "#c9843c"},
                "dark": {"bg": "#0f1a1b", "surface": "#162426", "border": "#2e4749", "text": "#dfeceb",
                         "primary": "#5cb9c2", "accent": "#e2a75f"},
                "charts": ["#17656f", "#c9843c", "#2c6f52", "#96700f", "#3a6d94", "#7a4f6d", "#5c8f99", "#c2a878"],
            },
        ),
        (
            "terracotta",
            {
                "label": "Terracotta — Chaud",
                "light": {"bg": "#f7f2ee", "surface": "#fffdfa", "border": "#e2d3c8", "text": "#2e211c",
                          "primary": "#a8543a", "accent": "#3f6b6d"},
                "dark": {"bg": "#191310", "surface": "#221a16", "border": "#45352d", "text": "#f0e6df",
                         "primary": "#e08a68", "accent": "#7fc2c4"},
                "charts": ["#a8543a", "#3f6b6d", "#2c6f52", "#96700f", "#3a6d94", "#7a4f6d", "#b07a5c", "#c2a878"],
            },
        ),
        (
            "foret",
            {
                "label": "Forêt — Vert profond",
                "light": {"bg": "#eff3ef", "surface": "#ffffff", "border": "#d1ded3", "text": "#18291f",
                          "primary": "#2c5c47", "accent": "#a8742f"},
                "dark": {"bg": "#0f1613", "surface": "#16211c", "border": "#2f453a", "text": "#e0ebe4",
                         "primary": "#7cc3a0", "accent": "#e0b46a"},
                "charts": ["#2c5c47", "#a8742f", "#3a6d94", "#96700f", "#7a4f6d", "#5c7f99", "#6b9c7f", "#c2a878"],
            },
        ),
        (
            "lavande",
            {
                "label": "Lavande — Violet doux",
                "light": {"bg": "#f2f0f7", "surface": "#ffffff", "border": "#dbd5e8", "text": "#241f33",
                          "primary": "#5a4b81", "accent": "#b5714b"},
                "dark": {"bg": "#14121c", "surface": "#1c1a26", "border": "#3a3550", "text": "#e8e5f1",
                         "primary": "#a896e0", "accent": "#e0a177"},
                "charts": ["#5a4b81", "#b5714b", "#2c6f52", "#96700f", "#3a6d94", "#8a4f6d", "#7c6fa8", "#c2a878"],
            },
        ),
        (
            "brume",
            {
                "label": "Brume — Gris neutres",
                "light": {"bg": "#f2f3f4", "surface": "#ffffff", "border": "#d9dde1", "text": "#22272c",
                          "primary": "#4a5560", "accent": "#2c6f8f"},
                "dark": {"bg": "#15181b", "surface": "#1d2126", "border": "#363f48", "text": "#e6e9ec",
                         "primary": "#aeb9c4", "accent": "#84c0dd"},
                "charts": ["#4a5560", "#2c6f8f", "#2c6f52", "#96700f", "#3a6d94", "#7a4f6d", "#6f7a85", "#c2a878"],
            },
        ),
    ]
)

SEMANTIC_LIGHT = {"success": "#2c6f52", "warning": "#96700f", "danger": "#a63a3a", "info": "#3a6d94"}
SEMANTIC_DARK = {"success": "#74c19b", "warning": "#dcbc63", "danger": "#e88a86", "info": "#8dbde0"}

DEFAULT_PALETTE = "ardoise"
MODES = ("light", "dark", "auto")
DENSITIES = ("confort", "compacte")


# --------------------------------------------------------------------------- #
# Couleurs
# --------------------------------------------------------------------------- #
def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = (value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return 0, 0, 0


def rgb_to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def hex_to_hsl(value: str):
    r, g, b = (c / 255 for c in hex_to_rgb(value))
    h, lightness, s = colorsys.rgb_to_hls(r, g, b)
    return h, s, lightness


def hsl_to_hex(h: float, s: float, lightness: float) -> str:
    h = (h % 1.0 + 1.0) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, lightness)), max(0.0, min(1.0, s)))
    return rgb_to_hex((r * 255, g * 255, b * 255))


def relative_luminance(value: str) -> float:
    def channel(c: int) -> float:
        cs = c / 255
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4

    r, g, b = hex_to_rgb(value)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(foreground: str, background: str) -> float:
    a, b = relative_luminance(foreground), relative_luminance(background)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def mix(color: str, target: str, ratio: float) -> str:
    """Mélange ``color`` vers ``target`` (ratio 0..1)."""
    c1, c2 = hex_to_rgb(color), hex_to_rgb(target)
    return rgb_to_hex(tuple(c1[i] + (c2[i] - c1[i]) * ratio for i in range(3)))


def soften(color: str, ratio: float = 0.88) -> str:
    """Version pastel (-soft) : mélange vers le blanc."""
    return mix(color, "#ffffff", ratio)


def chart_colors(primary: str) -> list[str]:
    """8 teintes espacées de 54° (0,15) à partir de la couleur primaire."""
    h, s, lightness = hex_to_hsl(primary)
    s = max(0.28, min(0.72, s))
    out = []
    for i in range(8):
        hue = h + i * (54 / 360)
        lum = lightness + (0.06 if i % 2 else -0.04) * (1 if i < 4 else -1)
        out.append(hsl_to_hex(hue, s, max(0.22, min(0.62, lum))))
    return out


def derive(color: str) -> dict:
    """« Aux couleurs du lycée » : une seule couleur saisie → toute la palette.

    luminance primaire bornée 0.22-0.42, accent = teinte + 0.42,
    surfaces mélangées à blanc à 2,5-14 %, texte teinté, 8 teintes pour les graphiques.
    """
    h, s, lightness = hex_to_hsl(color)
    s = max(0.22, min(0.68, s))
    lum = max(0.22, min(0.42, lightness))
    primary = hsl_to_hex(h, s, lum)
    accent = hsl_to_hex(h + 0.42, min(0.72, s + 0.12), min(0.52, lum + 0.14))
    light = {
        "bg": mix(primary, "#ffffff", 0.94),          # 6 % de primaire
        "surface": mix(primary, "#ffffff", 0.975),    # 2,5 %
        "border": mix(primary, "#ffffff", 0.86),      # 14 %
        "text": mix(primary, "#14181c", 0.82),
        "primary": primary,
        "accent": accent,
    }
    dark_primary = hsl_to_hex(h, min(0.5, s), 0.68)
    dark = {
        "bg": mix(dark_primary, "#0d1013", 0.94),
        "surface": mix(dark_primary, "#151a1f", 0.92),
        "border": mix(dark_primary, "#2c343c", 0.72),
        "text": mix(dark_primary, "#e8eef4", 0.14),
        "primary": dark_primary,
        "accent": hsl_to_hex(h + 0.42, min(0.6, s + 0.05), 0.66),
    }
    return {
        "label": "Couleurs du lycée",
        "light": light,
        "dark": dark,
        "charts": chart_colors(primary),
        "seed": color,
    }


def palette(name: str, seed: str | None = None) -> dict:
    if name == "lycee" and seed:
        return derive(seed)
    return PALETTES.get(name or DEFAULT_PALETTE, PALETTES[DEFAULT_PALETTE])


def palette_choices() -> list[tuple[str, str]]:
    return [(key, data["label"]) for key, data in PALETTES.items()] + [("lycee", "Couleurs du lycée")]


# --------------------------------------------------------------------------- #
# Génération du CSS
# --------------------------------------------------------------------------- #
def _vars_block(values: dict, mode: str) -> str:
    semantic = SEMANTIC_DARK if mode == "dark" else SEMANTIC_LIGHT
    lines = []
    for key, value in values.items():
        lines.append("  --%s: %s;" % (key, value))
    for key, value in semantic.items():
        lines.append("  --%s: %s;" % (key, value))
        lines.append("  --%s-soft: %s;" % (key, soften(value, 0.86 if mode == "light" else 0.72)))
    lines.append("  --on-primary: %s;" % ("#ffffff" if contrast("#ffffff", values["primary"]) >= 3 else "#12161a"))
    return "\n".join(lines)


def _charts(values: list[str]) -> str:
    return "\n".join("  --chart-%d: %s;" % (i + 1, c) for i, c in enumerate(values[:8])) + \
        "\n  --c-charts: %s;" % ",".join(values[:8])


def build_css(name: str = DEFAULT_PALETTE, seed: str | None = None) -> str:
    """CSS servi par ``/theme.css`` : variables par ``html[data-palette][data-mode]``."""
    blocks: list[str] = [
        "/* MDL Gestion — thème généré dynamiquement (core.theme.build_css) */",
        ":root { color-scheme: light; }",
    ]
    for key, data in PALETTES.items():
        blocks.append('html[data-palette="%s"][data-mode="light"] {\n%s\n%s\n}'
                      % (key, _vars_block(data["light"], "light"), _charts(data["charts"])))
        blocks.append('html[data-palette="%s"][data-mode="dark"] {\n%s\n%s\n}'
                      % (key, _vars_block(data["dark"], "dark"), _charts(data["charts"])))
        blocks.append(
            'html[data-palette="%s"][data-mode="auto"] {\n%s\n}\n'
            "@media (prefers-color-scheme: dark) {\n"
            'html[data-palette="%s"][data-mode="auto"] {\n%s\n}\n}'
            % (key, _vars_block(data["light"], "light"), key, _vars_block(data["dark"], "dark"))
        )
    derived = derive(seed or "#33556e")
    blocks.append('html[data-palette="lycee"][data-mode="light"] {\n%s\n%s\n}'
                  % (_vars_block(derived["light"], "light"), _charts(derived["charts"])))
    blocks.append('html[data-palette="lycee"][data-mode="dark"] {\n%s\n%s\n}'
                  % (_vars_block(derived["dark"], "dark"), _charts(derived["charts"])))
    blocks.append(
        'html[data-palette="lycee"][data-mode="auto"] {\n%s\n}\n'
        '@media (prefers-color-scheme: dark) {\nhtml[data-palette="lycee"][data-mode="auto"] {\n%s\n}\n}'
        % (_vars_block(derived["light"], "light"), _vars_block(derived["dark"], "dark"))
    )
    blocks.append(_density_css())
    return "\n".join(blocks) + "\n"


def _density_css() -> str:
    return """
html[data-density="compacte"] { --row-pad: 4px; --cell-pad: 5px 8px; --base-size: 13px; --gap: 10px; }
html[data-density="confort"] { --row-pad: 8px; --cell-pad: 9px 12px; --base-size: 14px; --gap: 16px; }
"""


def preview_svg(name: str, mode: str = "light", seed: str | None = None) -> str:
    """Petit aperçu SVG utilisé dans Réglages → Apparence."""
    data = palette(name, seed)
    v = data[mode]
    return (
        '<svg viewBox="0 0 120 72" xmlns="http://www.w3.org/2000/svg" role="img">'
        '<rect width="120" height="72" rx="6" fill="{bg}"/>'
        '<rect x="6" y="6" width="26" height="60" rx="4" fill="{primary}"/>'
        '<rect x="38" y="6" width="76" height="14" rx="4" fill="{surface}"/>'
        '<rect x="38" y="26" width="36" height="18" rx="4" fill="{surface}" stroke="{border}"/>'
        '<rect x="78" y="26" width="36" height="18" rx="4" fill="{surface}" stroke="{border}"/>'
        '<rect x="38" y="50" width="76" height="16" rx="4" fill="{accent}" opacity="0.35"/>'
        '<circle cx="19" cy="18" r="5" fill="{accent}"/>'
        "</svg>"
    ).format(**v)
