"""The 133 outfit colors of the Tibia client (same formula OTClient uses)."""


def _color(c):
    steps, values = 19, 7
    if c % steps:
        h = c % steps / 18.0
        s, i = [(0.25, 1.0), (0.25, 0.75), (0.5, 0.75), (0.667, 0.75), (1.0, 1.0), (1.0, 0.75), (1.0, 0.5)][c // steps]
    else:
        h, s, i = 0.0, 0.0, 1 - c / steps / values
    if i == 0:
        return "#000000"
    if s == 0:
        v = int(i * 255)
        return f"#{v:02x}{v:02x}{v:02x}"
    if h < 1 / 6:
        r, b = i, i * (1 - s)
        g = b + (i - b) * 6 * h
    elif h < 2 / 6:
        g, b = i, i * (1 - s)
        r = g - (i - b) * (6 * h - 1)
    elif h < 3 / 6:
        g, r = i, i * (1 - s)
        b = r + (i - r) * (6 * h - 2)
    elif h < 4 / 6:
        b, r = i, i * (1 - s)
        g = b - (i - r) * (6 * h - 3)
    elif h < 5 / 6:
        b, g = i, i * (1 - s)
        r = g + (i - g) * (6 * h - 4)
    else:
        r, g = i, i * (1 - s)
        b = r - (i - g) * (6 * h - 5)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


PALETTE = [_color(c) for c in range(133)]
