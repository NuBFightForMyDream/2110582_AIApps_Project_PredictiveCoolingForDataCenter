"""Small spot illustrations (inline SVG) in the style of the project cover: navy card, pastel shapes, rounded lines.

One per page, shown in the page header. Pure SVG strings, so they scale, need no files and work offline.
"""
NAVY, PANEL, LINE = "#1b2140", "#2a3263", "#3c4680"
LAV, MINT, SKY, PEACH, PINK, YELLOW, INK = "#a99cf2", "#8ee6c8", "#7cc4ff", "#ffb48a", "#ff8fa6", "#ffd66b", "#eef1ff"
FONT = "font-family='Inter, Segoe UI, Arial, sans-serif'"


def _frame(body: str) -> str:
    circuit = (f"<g stroke='{LINE}' stroke-width='2' fill='none' stroke-linecap='round'>"
               f"<path d='M8 22 h16 l8 -8 h12'/><path d='M232 128 h-16 l-8 8 h-12'/></g>"
               f"<circle cx='44' cy='14' r='2.6' fill='{LINE}'/><circle cx='196' cy='136' r='2.6' fill='{LINE}'/>")
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 240 150' role='img'>"
            f"<rect width='240' height='150' rx='18' fill='{NAVY}'/>{circuit}{body}</svg>")


def _rack(x, y, w=40, h=78, leds=MINT):
    slots = "".join(f"<rect x='{x + 5}' y='{y + 7 + i * 14}' width='{w - 10}' height='9' rx='2' fill='{NAVY}'/>"
                    f"<circle cx='{x + w - 10}' cy='{y + 11.5 + i * 14}' r='1.8' fill='{leds}'/>"
                    f"<circle cx='{x + w - 15}' cy='{y + 11.5 + i * 14}' r='1.8' fill='{leds}'/>" for i in range(int((h - 8) // 14)))
    return f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='5' fill='{PANEL}' stroke='{LINE}' stroke-width='1.5'/>{slots}"


def _robot(cx, cy, size=1.0, color=LAV):
    w, h = 40 * size, 32 * size
    return (f"<line x1='{cx}' y1='{cy - h / 2}' x2='{cx}' y2='{cy - h / 2 - 9 * size}' stroke='{INK}' stroke-width='2'/>"
            f"<circle cx='{cx}' cy='{cy - h / 2 - 10 * size}' r='{3.4 * size}' fill='{PEACH}'/>"
            f"<rect x='{cx - w / 2}' y='{cy - h / 2}' width='{w}' height='{h}' rx='{11 * size}' fill='{INK}'/>"
            f"<rect x='{cx - w / 2 + 5 * size}' y='{cy - h / 2 + 6 * size}' width='{w - 10 * size}' height='{h - 13 * size}' "
            f"rx='{7 * size}' fill='{NAVY}'/>"
            f"<circle cx='{cx - 7 * size}' cy='{cy - 1 * size}' r='{2.8 * size}' fill='{color}'/>"
            f"<circle cx='{cx + 7 * size}' cy='{cy - 1 * size}' r='{2.8 * size}' fill='{color}'/>"
            f"<path d='M{cx - 4 * size} {cy + 4.5 * size} q{4 * size} {3 * size} {8 * size} 0' stroke='{color}' stroke-width='1.8' "
            f"fill='none' stroke-linecap='round'/>")


def _sparkle(x, y, r=6, color=YELLOW):
    return f"<path d='M{x} {y - r} Q{x} {y} {x + r} {y} Q{x} {y} {x} {y + r} Q{x} {y} {x - r} {y} Q{x} {y} {x} {y - r} Z' fill='{color}'/>"


def _shield(cx, cy, s=1.0, stroke=MINT):
    return (f"<path d='M{cx} {cy - 50 * s} L{cx + 42 * s} {cy - 35 * s} V{cy + 2 * s} C{cx + 42 * s} {cy + 28 * s} {cx + 22 * s} "
            f"{cy + 44 * s} {cx} {cy + 54 * s} C{cx - 22 * s} {cy + 44 * s} {cx - 42 * s} {cy + 28 * s} {cx - 42 * s} {cy + 2 * s} "
            f"V{cy - 35 * s} Z' fill='{PANEL}' stroke='{stroke}' stroke-width='4' stroke-linejoin='round'/>")


ARROW = (f"<defs><marker id='a' viewBox='0 0 10 10' refX='6' refY='5' markerWidth='5' markerHeight='5' orient='auto'>"
         f"<path d='M0 0 L10 5 L0 10 z' fill='{INK}'/></marker></defs>")

ART = {
    "sensors": _frame(
        _rack(58, 44) + _rack(104, 44, leds=SKY)
        + "".join(f"<path d='M{x - r} 34 a{r} {r} 0 0 1 {2 * r} 0' stroke='{SKY}' stroke-width='3' fill='none' "
                  f"stroke-linecap='round' opacity='{o}'/>" for x, r, o in ((78, 7, 1), (78, 14, .7), (78, 21, .45)))
        + f"<rect x='170' y='34' width='14' height='68' rx='7' fill='{INK}'/><rect x='174' y='58' width='6' height='44' "
          f"fill='{PINK}'/><circle cx='177' cy='108' r='12' fill='{PINK}'/>"
        + f"<text x='194' y='52' {FONT} font-size='13' font-weight='700' fill='{INK}'>27°</text>"),
    "cleaning": _frame(
        f"<polyline points='22,96 34,74 44,106 54,58 64,98 74,86 86,112 96,90' fill='none' stroke='{PEACH}' stroke-width='3.5' "
        f"stroke-linejoin='round' stroke-linecap='round'/>"
        + f"<g stroke='{PINK}' stroke-width='3' stroke-linecap='round'><path d='M50 46 l8 8 M58 46 l-8 8'/>"
          f"<path d='M82 122 l7 7 M89 122 l-7 7'/></g>"
        + ARROW + f"<line x1='104' y1='84' x2='130' y2='84' stroke='{INK}' stroke-width='3' marker-end='url(#a)'/>"
        + f"<path d='M142 98 C160 66 182 66 218 86' fill='none' stroke='{MINT}' stroke-width='4' stroke-linecap='round'/>"
        + _sparkle(166, 50, 8) + _sparkle(206, 58, 5) + _sparkle(190, 112, 6, MINT)),
    "forecast": _frame(
        f"<path d='M30 30 V118 H214' fill='none' stroke='{LINE}' stroke-width='2'/>"
        + f"<polygon points='126,80 152,52 178,46 208,34 208,66 178,72 152,76 126,84' fill='{LAV}' opacity='.28'/>"
        + f"<polyline points='30,100 52,94 74,98 96,80 126,82' fill='none' stroke='{SKY}' stroke-width='4' stroke-linecap='round' "
          f"stroke-linejoin='round'/>"
        + f"<polyline points='126,82 152,64 178,59 208,50' fill='none' stroke='{LAV}' stroke-width='4' stroke-dasharray='7 6' "
          f"stroke-linecap='round'/>"
        + f"<line x1='126' y1='30' x2='126' y2='118' stroke='{INK}' stroke-width='1.6' stroke-dasharray='3 4' opacity='.7'/>"
        + f"<text x='112' y='132' {FONT} font-size='11' fill='{INK}' opacity='.8'>now</text>"
        + f"<circle cx='58' cy='44' r='13' fill='none' stroke='{YELLOW}' stroke-width='3'/>"
          f"<path d='M58 36 V44 L64 48' stroke='{YELLOW}' stroke-width='3' fill='none' stroke-linecap='round'/>"),
    "mpc": _frame(
        "".join(f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{LINE}' stroke-width='2.4'/>"
                for x1, y1 in ((88, 40), (88, 75), (88, 110)) for x2, y2 in ((148, y1 - 22), (148, y1), (148, y1 + 22)))
        + "".join(f"<line x1='34' y1='75' x2='88' y2='{y}' stroke='{LINE}' stroke-width='2.4'/>" for y in (40, 75, 110))
        + f"<polyline points='34,75 88,75 148,53 204,46' fill='none' stroke='{MINT}' stroke-width='5' stroke-linecap='round' "
          f"stroke-linejoin='round'/>"
        + f"<circle cx='34' cy='75' r='7' fill='{SKY}'/><circle cx='88' cy='75' r='5' fill='{MINT}'/>"
          f"<circle cx='148' cy='53' r='5' fill='{MINT}'/>"
        + f"<path d='M204 26 V50' stroke='{INK}' stroke-width='2.5'/><path d='M204 27 h20 l-6 7 l6 7 h-20 z' fill='{YELLOW}'/>"
        + f"<g stroke='{PINK}' stroke-width='3.4' stroke-linecap='round'><path d='M142 12 l12 12 M154 12 l-12 12'/>"
          f"<path d='M142 126 l12 12 M154 126 l-12 12'/></g>"
        + f"<text x='160' y='108' {FONT} font-size='14' font-weight='700' fill='{INK}'>81 plans</text>"),
    "safety": _frame(
        _shield(120, 76) + f"<path d='M100 76 l14 14 l28 -30' fill='none' stroke='{MINT}' stroke-width='7' stroke-linecap='round' "
                           f"stroke-linejoin='round'/>"
        + "".join(f"<rect x='{x}' y='{y}' width='30' height='17' rx='8.5' fill='{c}'/>"
                  f"<text x='{x + 15}' y='{y + 12.5}' {FONT} font-size='10.5' font-weight='700' fill='{NAVY}' text-anchor='middle'>{t}</text>"
                  for x, y, c, t in ((28, 36, LAV, 'R1'), (28, 66, SKY, 'R2'), (28, 96, PEACH, 'R3'), (182, 36, LAV, 'R4'),
                                     (182, 66, YELLOW, 'R5'), (182, 96, PINK, 'R6')))),
    "results": _frame(
        f"<path d='M28 122 H160' stroke='{LINE}' stroke-width='2'/>"
        + "".join(f"<rect x='{x}' y='{122 - h}' width='28' height='{h}' rx='6' fill='{c}'/>"
                  for x, h, c in ((40, 78, MINT), (80, 70, PEACH), (120, 58, SKY)))
        + f"<path d='M186 104 C172 72 196 44 224 40 C226 70 212 98 186 104 Z' fill='{MINT}'/>"
          f"<path d='M188 102 C198 82 208 66 220 46' stroke='{NAVY}' stroke-width='2.2' fill='none'/>"
        + f"<path d='M204 66 l-10 18 h9 l-4 16 l14 -22 h-9 l5 -12 z' fill='{YELLOW}'/>"),
    "agents": _frame(
        "".join(f"<line x1='120' y1='66' x2='{x}' y2='{y}' stroke='{INK}' stroke-width='1.6' stroke-dasharray='4 5' opacity='.5'/>"
                for x, y in ((48, 50), (192, 50), (64, 116), (176, 116)))
        + _robot(120, 66, 1.15, LAV) + _robot(48, 50, .75, SKY) + _robot(192, 50, .75, MINT) + _robot(64, 116, .75, PEACH)
        + _robot(176, 116, .75, PINK)),
    "plant": _frame(
        f"<rect x='34' y='54' width='172' height='74' rx='8' fill='{PANEL}' stroke='{LINE}' stroke-width='2'/>"
        + _rack(104, 68, 26, 50) + _rack(140, 68, 26, 50, SKY)
        + f"<rect x='46' y='70' width='38' height='46' rx='6' fill='{INK}'/><circle cx='65' cy='93' r='13' fill='none' "
          f"stroke='{SKY}' stroke-width='3'/>"
        + "".join(f"<ellipse cx='65' cy='93' rx='4' ry='11' fill='{SKY}' transform='rotate({a} 65 93)'/>" for a in (0, 60, 120))
        + f"<path d='M150 54 l6 -26 h30 l6 26 z' fill='{INK}'/>"
        + "".join(f"<path d='M{x} 22 q-5 -6 0 -12 q5 -6 0 -12' stroke='{INK}' stroke-width='2.4' fill='none' opacity='.7' "
                  f"stroke-linecap='round'/>" for x in (162, 172, 182))
        + f"<g stroke='{SKY}' stroke-width='2.6' stroke-linecap='round'>"
          + "".join(f"<line x1='60' y1='36' x2='{60 + 11 * dx}' y2='{36 + 11 * dy}'/>"
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (.7, .7), (-.7, -.7), (.7, -.7), (-.7, .7))) + "</g>"
        + f"<path d='M214 118 l-9 15 h8 l-3 12 l12 -18 h-8 l4 -9 z' fill='{YELLOW}'/>"),
    "hardware": _frame(
        f"<circle cx='96' cy='76' r='36' fill='{PANEL}' stroke='{SKY}' stroke-width='4'/>"
        + "".join(f"<ellipse cx='96' cy='60' rx='8' ry='15' fill='{LAV}' transform='rotate({a} 96 76)'/>" for a in (0, 90, 180, 270))
        + f"<circle cx='96' cy='76' r='7' fill='{INK}'/>"
        + "".join(f"<path d='M{x} 58 q-6 18 0 36' stroke='{PEACH}' stroke-width='2.6' fill='none' stroke-linecap='round' opacity='{o}'/>"
                  for x, o in ((48, 1), (38, .6)))
        + f"<path d='M150 76 a28 28 0 0 1 56 0' fill='none' stroke='{LINE}' stroke-width='8' stroke-linecap='round'/>"
          f"<path d='M190 56 a28 28 0 0 1 16 20' fill='none' stroke='{PINK}' stroke-width='8' stroke-linecap='round'/>"
          f"<line x1='178' y1='76' x2='196' y2='58' stroke='{INK}' stroke-width='3.4' stroke-linecap='round'/>"
          f"<circle cx='178' cy='76' r='4.5' fill='{INK}'/>"
        + f"<g transform='rotate(-40 178 114)'><rect x='160' y='109' width='40' height='10' rx='5' fill='{MINT}'/>"
          f"<circle cx='160' cy='114' r='10' fill='{MINT}'/><rect x='150' y='111' width='10' height='6' fill='{NAVY}'/></g>"),
    "upgrades": _frame(
        f"<path d='M28 122 H170' stroke='{LINE}' stroke-width='2'/>"
        + f"<rect x='44' y='42' width='34' height='80' rx='7' fill='{PEACH}'/><rect x='118' y='72' width='34' height='50' rx='7' "
          f"fill='{MINT}'/>"
        + ARROW + f"<path d='M84 60 Q100 52 112 70' fill='none' stroke='{INK}' stroke-width='3' marker-end='url(#a)'/>"
        + f"<text x='46' y='36' {FONT} font-size='11' fill='{INK}' opacity='.85'>before</text>"
          f"<text x='122' y='66' {FONT} font-size='11' fill='{INK}' opacity='.85'>after</text>"
        + f"<circle cx='198' cy='56' r='20' fill='{YELLOW}'/><circle cx='198' cy='56' r='13' fill='none' stroke='{NAVY}' "
          f"stroke-width='2.4' opacity='.6'/>"
        + f"<path d='M184 118 C176 98 190 82 212 80 C212 100 204 114 184 118 Z' fill='{MINT}'/>" + _sparkle(222, 104, 6)),
    "security": _frame(
        "".join(f"<line x1='{a}' y1='{b}' x2='{c}' y2='{d}' stroke='{LINE}' stroke-width='2.4'/>"
                for a, b, c, d in ((30, 44, 58, 76), (58, 76, 30, 110), (58, 76, 84, 76)))
        + "".join(f"<circle cx='{x}' cy='{y}' r='7' fill='{c}'/>" for x, y, c in ((30, 44, SKY), (58, 76, LAV), (30, 110, MINT)))
        + f"<line x1='212' y1='36' x2='176' y2='52' stroke='{PINK}' stroke-width='2.4' stroke-dasharray='4 4'/>"
          f"<circle cx='214' cy='34' r='9' fill='{PINK}'/><path d='M209 29 l10 10 M219 29 l-10 10' stroke='{NAVY}' stroke-width='2.6' "
          f"stroke-linecap='round'/><line x1='168' y1='44' x2='182' y2='60' stroke='{PINK}' stroke-width='4' stroke-linecap='round'/>"
        + _shield(130, 78, .92, LAV)
        + f"<path d='M118 72 v-8 a12 12 0 0 1 24 0 v8' fill='none' stroke='{MINT}' stroke-width='5'/>"
          f"<rect x='111' y='70' width='38' height='30' rx='7' fill='{MINT}'/><circle cx='130' cy='83' r='4' fill='{NAVY}'/>"
          f"<rect x='128.5' y='84' width='3' height='9' rx='1.5' fill='{NAVY}'/>"),
}

LOGO = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='16' fill='%s'/>"
        "<g stroke='%s' stroke-width='4.4' stroke-linecap='round'>%s</g><circle cx='32' cy='32' r='5' fill='%s'/></svg>"
        % (NAVY, SKY, "".join(f"<line x1='32' y1='32' x2='{32 + 18 * dx:.1f}' y2='{32 + 18 * dy:.1f}'/>"
                              for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (.71, .71), (-.71, -.71), (.71, -.71), (-.71, .71))),
           MINT))
