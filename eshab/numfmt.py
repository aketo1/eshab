"""Excel's number formats: a value as Excel shows it in a cell.

A format has up to four sections (positive; negative; zero; text), each with
an optional colour ([Red]) or condition ([>=100]). Numbers take digit
placeholders (0 # ?), thousands separators and scaling commas, percent,
scientific notation and fractions; dates and times take the y m d h s
tokens, AM/PM and elapsed [h]; quoted text, backslash escapes, _x spaces and
*x fills are kept as Excel keeps them.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from fractions import Fraction

#: Built-in formats Excel shows by id when the file does not spell them out.
BUILTIN = {0: "General", 1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00", 9: "0%", 10: "0.00%", 11: "0.00E+00",
           12: "# ?/?", 13: "# ??/??", 14: "m/d/yyyy", 15: "d-mmm-yy", 16: "d-mmm", 17: "mmm-yy", 18: "h:mm AM/PM",
           19: "h:mm:ss AM/PM", 20: "h:mm", 21: "h:mm:ss", 22: "m/d/yyyy h:mm", 37: "#,##0 ;(#,##0)",
           38: "#,##0 ;[Red](#,##0)", 39: "#,##0.00;(#,##0.00)", 40: "#,##0.00;[Red](#,##0.00)", 45: "mm:ss",
           46: "[h]:mm:ss", 47: "mmss.0", 48: "##0.0E+0", 49: "@"}
COLORS = {"black": "000000", "blue": "0000FF", "cyan": "00FFFF", "green": "00FF00", "magenta": "FF00FF",
          "red": "FF0000", "white": "FFFFFF", "yellow": "FFFF00"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_EPOCH = datetime(1899, 12, 30)
_EPOCH_1904 = datetime(1904, 1, 1)
_DATE_TOKENS = re.compile(r"\[(?:h+|m+|s+)\]|yyyy|yy|mmmmm|mmmm|mmm|mm|m|dddd|ddd|dd|d|hh|h|ss|s|AM/PM|am/pm|A/P|a/p|\.0+",
                          re.IGNORECASE)


def _sections(code: str) -> list[str]:
    """A format's sections, split on semicolons outside quotes and brackets."""
    out, current, quoted, bracket, escaped = [], [], False, False, False
    for char in code:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\" and not quoted:
            current.append(char)
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
        elif char == "[" and not quoted:
            bracket = True
        elif char == "]" and not quoted:
            bracket = False
        if char == ";" and not quoted and not bracket:
            out.append("".join(current))
            current = []
            continue
        current.append(char)
    out.append("".join(current))
    return out


_BRACKET = re.compile(r"\[([^\]]*)\]")


def _bracketed(section: str):
    """(section without colour, condition and locale tags, colour, condition, elapsed tokens kept)."""
    color = condition = None
    kept = []
    position = 0
    for match in _BRACKET.finditer(section):
        kept.append(section[position:match.start()])
        position = match.end()
        inner = match.group(1)
        lowered = inner.lower()
        if lowered in COLORS:
            color = COLORS[lowered]
        elif lowered.startswith("color"):
            try:
                color = _PALETTE[int(lowered[5:]) - 1]
            except (ValueError, IndexError):
                pass
        elif re.fullmatch(r"(<=|>=|<>|<|>|=)\s*-?[0-9.]+", inner):
            operator, number = re.match(r"(<=|>=|<>|<|>|=)\s*(-?[0-9.]+)", inner).groups()
            condition = (operator, float(number))
        elif re.fullmatch(r"h+|m+|s+", lowered):
            kept.append(match.group(0))              # elapsed time stays a token
        elif inner.startswith("$"):
            symbol = inner[1:].split("-")[0]
            kept.append('"' + symbol + '"' if symbol else "")
    kept.append(section[position:])
    return "".join(kept), color, condition


def _holds(condition, value: float) -> bool:
    operator, number = condition
    return {"<": value < number, "<=": value <= number, ">": value > number, ">=": value >= number,
            "=": value == number, "<>": value != number}[operator]


def _strip_literals(section: str) -> str:
    """The section with quoted text and escapes taken out, to look at its tokens."""
    return re.sub(r'"[^"]*"|\\.|_.|\*.', "", section)


def is_date_format(code: str) -> bool:
    section = _bracketed(_sections(code or "General")[0])[0]
    plain = _strip_literals(section)
    return bool(re.search(r"[ymdhs]|AM/PM|A/P|\[h\]", plain, re.IGNORECASE)) and "general" not in plain.lower()


def format_value(value, code: str | None, date1904: bool = False, short_date: str | None = None) -> tuple[str, str | None]:
    """(text, colour as RRGGBB or None) for a cell's value in a number format."""
    code = code or "General"
    if code == "m/d/yyyy" and short_date:
        code = short_date
    if value is None:
        return "", None
    if isinstance(value, bool):
        return ("TRUE" if value else "FALSE"), None
    if isinstance(value, datetime):
        value = to_serial(value, date1904)
    elif hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):       # a date
        value = to_serial(datetime(value.year, value.month, value.day), date1904)
    elif isinstance(value, timedelta):
        value = value.total_seconds() / 86400.0
    elif hasattr(value, "hour") and hasattr(value, "minute") and not hasattr(value, "year"):  # a time of day
        value = (value.hour * 3600 + value.minute * 60 + value.second + getattr(value, "microsecond", 0) / 1e6) / 86400.0
    sections = _sections(code)
    if isinstance(value, str):
        if len(sections) >= 4:
            section, color, _ = _bracketed(sections[3])
            return _literal_text(section).replace("\0", value), color
        if "@" in sections[0]:
            section, color, _ = _bracketed(sections[0])
            return _literal_text(section).replace("\0", value), color
        return value, None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value), None
    if math.isnan(number) or math.isinf(number):
        return "#NUM!", None
    parsed = [_bracketed(s) for s in sections]
    chosen, sign = _choose(parsed, number)
    section, color, _ = chosen
    if section.strip().lower() in ("general", ""):
        text = general(abs(number) if not sign else number)
        return (("-" + text) if sign and number < 0 and not text.startswith("-") else text), color
    if is_date_format(section):
        return _date_text(number, section, date1904), color
    text = _number_text(abs(number), section)
    return ("-" + text if sign and number < 0 else text), color


def _choose(parsed, number: float):
    """The section a number takes, and whether it still needs its minus sign."""
    if any(p[2] is not None for p in parsed[:2]):
        for index, item in enumerate(parsed[:2]):
            if item[2] is not None and _holds(item[2], number):
                return item, number < 0 and index == 0
        return (parsed[2] if len(parsed) > 2 else parsed[-1]), number < 0
    if number > 0 or len(parsed) == 1:
        return parsed[0], number < 0
    if number < 0:
        return (parsed[1], False) if len(parsed) > 1 and parsed[1][0] != "" else (parsed[0], True)
    if len(parsed) > 2:
        return parsed[2], False
    return parsed[0], False


def general(number: float) -> str:
    """Excel's General: up to 11 characters, switching to scientific when it must."""
    if number == 0:
        return "0"
    magnitude = abs(number)
    if magnitude >= 1e11 or magnitude < 1e-9:
        mantissa, exponent = f"{number:.5E}".split("E")
        mantissa = mantissa.rstrip("0").rstrip(".")
        return f"{mantissa}E{int(exponent):+03d}"
    digits = 10 - max(0, int(math.floor(math.log10(magnitude))))
    text = f"{round(number, max(0, digits)):.{max(0, digits)}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    # never more than 11 characters with the sign and point
    while len(text.lstrip("-")) > 11 and "." in text:
        text = text[:-1].rstrip(".")
    return text


def _literal_text(section: str) -> str:
    """A text section: quoted text and escapes kept, @ stands for the value (as \\0)."""
    out, index = [], 0
    while index < len(section):
        char = section[index]
        if char == '"':
            end = section.find('"', index + 1)
            end = len(section) if end < 0 else end
            out.append(section[index + 1:end])
            index = end + 1
            continue
        if char == "\\" and index + 1 < len(section):
            out.append(section[index + 1])
            index += 2
            continue
        if char == "_" and index + 1 < len(section):
            out.append(" ")
            index += 2
            continue
        if char == "*" and index + 1 < len(section):
            index += 2
            continue
        out.append("\0" if char == "@" else char)
        index += 1
    return "".join(out)


def _number_text(number: float, section: str) -> str:
    """A positive number through a number section."""
    plain = _strip_literals(section)
    if "/" in plain and re.search(r"[0#?]+\s*/\s*[0-9#?]+", plain):
        return _fraction_text(number, section)
    percent = plain.count("%")
    number *= 100 ** percent
    # Commas right after the last digit placeholder divide by a thousand each.
    scaled = re.search(r"([0#?])(,+)(?![0#?])", plain)
    if scaled:
        number /= 1000 ** len(scaled.group(2))
    scientific = re.search(r"[eE]([+-])([0#]+)", plain)
    tokens = _tokens(section)
    placeholders = "".join(t[1] for t in tokens if t[0] == "digit")
    if not placeholders:                     # a section of text only shows the text
        return "".join(t[1] for t in tokens if t[0] in ("literal", "percent"))
    if scientific:
        return _scientific(number, tokens, scientific)
    point = next((i for i, t in enumerate(tokens) if t[0] == "point"), None)
    whole_tokens = tokens if point is None else tokens[:point]
    fraction_tokens = [] if point is None else tokens[point + 1:]
    decimals = sum(1 for t in fraction_tokens if t[0] == "digit")
    rounded = _round_half_up(number, decimals)
    whole, _, frac = f"{rounded:.{decimals}f}".partition(".")
    grouping = any(t[0] == "comma" for t in whole_tokens) and placeholders
    whole_digits = [t for t in whole_tokens if t[0] == "digit"]
    whole_text = _fill_whole(whole, whole_digits, grouping)
    frac_text = _fill_fraction(frac, [t for t in fraction_tokens if t[0] == "digit"])
    out = []
    digit_index = 0
    placed_whole = False
    for token in whole_tokens:
        if token[0] == "digit":
            if not placed_whole:
                out.append(whole_text)
                placed_whole = True
            digit_index += 1
        elif token[0] in ("literal", "percent"):
            out.append(token[1])
    if not placed_whole and whole_text not in ("", "0"):
        out.append(whole_text)
    if point is not None:
        out.append(".")
        placed_frac = False
        for token in fraction_tokens:
            if token[0] == "digit":
                if not placed_frac:
                    out.append(frac_text)
                    placed_frac = True
            elif token[0] in ("literal", "percent"):
                out.append(token[1])
    return "".join(out)


def _round_half_up(number: float, decimals: int) -> float:
    factor = 10 ** decimals
    return math.floor(number * factor + 0.5 + 1e-9) / factor


def _tokens(section: str) -> list[tuple[str, str]]:
    """A number section as (kind, text): digit placeholders, the point, commas, literals."""
    out, index = [], 0
    while index < len(section):
        char = section[index]
        if char == '"':
            end = section.find('"', index + 1)
            end = len(section) if end < 0 else end
            out.append(("literal", section[index + 1:end]))
            index = end + 1
            continue
        if char == "\\" and index + 1 < len(section):
            out.append(("literal", section[index + 1]))
            index += 2
            continue
        if char == "_" and index + 1 < len(section):
            out.append(("literal", " "))
            index += 2
            continue
        if char == "*" and index + 1 < len(section):
            index += 2
            continue
        if char in "0#?":
            out.append(("digit", char))
        elif char == ".":
            out.append(("point", char))
        elif char == ",":
            out.append(("comma", char))
        elif char == "%":
            out.append(("percent", char))
        elif char in "eE" and index + 1 < len(section) and section[index + 1] in "+-":
            out.append(("exp", char + section[index + 1]))
            index += 2
            continue
        else:
            out.append(("literal", char))
        index += 1
    return out


def _fill_whole(digits: str, placeholders, grouping: bool) -> str:
    """The whole part: at least as many digits as its zeros ask for, ? as spaces."""
    digits = digits.lstrip("0")
    forced = sum(1 for p in placeholders if p[1] == "0")
    padded = sum(1 for p in placeholders if p[1] == "?")
    if len(digits) < forced:
        digits = "0" * (forced - len(digits)) + digits
    if grouping and digits:
        groups = []
        while len(digits) > 3:
            groups.insert(0, digits[-3:])
            digits = digits[:-3]
        groups.insert(0, digits)
        digits = ",".join(groups)
    if padded and len(digits) < forced + padded:
        digits = " " * (forced + padded - len(digits)) + digits
    return digits


def _fill_fraction(digits: str, placeholders) -> str:
    """The decimals: zeros kept for 0, dropped for #, spaces for ?."""
    out = list(digits)
    for index in range(len(placeholders) - 1, -1, -1):
        kind = placeholders[index][1]
        if index >= len(out):
            continue
        if out[index] == "0" and kind != "0" and all(c in "0 " for c in out[index:]):
            out[index] = " " if kind == "?" else ""
        else:
            break
    return "".join(out)


def _scientific(number: float, tokens, match) -> str:
    before = []
    for token in tokens:
        if token[0] == "exp":
            break
        before.append(token)
    point = next((i for i, t in enumerate(before) if t[0] == "point"), None)
    whole = [t for t in (before if point is None else before[:point]) if t[0] == "digit"]
    decimals = 0 if point is None else sum(1 for t in before[point + 1:] if t[0] == "digit")
    exponent_digits = len(match.group(2))
    if number == 0:
        mantissa, exponent = 0.0, 0
    else:
        exponent = int(math.floor(math.log10(number)))
        step = max(1, len(whole))
        if step > 1:                               # engineering formats: the exponent a multiple of the whole digits
            exponent -= exponent % step
        mantissa = number / 10 ** exponent
        if round(mantissa, decimals) >= 10 ** max(1, len(whole)):
            exponent += max(1, len(whole))
            mantissa = number / 10 ** exponent
    text = f"{_round_half_up(mantissa, decimals):.{decimals}f}"
    sign = "-" if exponent < 0 else ("+" if match.group(1) == "+" else "")
    return f"{text}E{sign}{abs(exponent):0{exponent_digits}d}"


def _fraction_text(number: float, section: str) -> str:
    plain = _strip_literals(section)
    match = re.search(r"(?:([#0?]+)\s+)?([#0?]+)\s*/\s*([0-9]+|[#0?]+)", plain)
    whole_part = match.group(1) is not None
    denominator_text = match.group(3)
    whole = int(number) if whole_part else 0
    rest = number - whole if whole_part else number
    if denominator_text.isdigit():
        denominator = int(denominator_text)
        numerator = int(round(rest * denominator))
    else:
        limit = 10 ** len(denominator_text) - 1
        fraction = Fraction(rest).limit_denominator(limit)
        numerator, denominator = fraction.numerator, fraction.denominator
    if numerator == denominator and denominator:
        whole, numerator = whole + 1, 0
    if numerator == 0:
        return str(whole) if whole_part else "0"
    head = f"{whole} " if whole_part and whole else ""
    return f"{head}{numerator}/{denominator}"


def to_serial(moment: datetime, date1904: bool = False) -> float:
    base = _EPOCH_1904 if date1904 else _EPOCH
    delta = moment - base
    return delta.days + delta.seconds / 86400.0 + delta.microseconds / 86400e6


def _date_text(serial: float, section: str, date1904: bool) -> str:
    base = _EPOCH_1904 if date1904 else _EPOCH
    tokens = list(_DATE_TOKENS.finditer(section))
    fractional = max((len(t.group(0)) - 1 for t in tokens if t.group(0).startswith(".")), default=0)
    # Excel rounds to the smallest unit shown.
    smallest = 1 / 86400.0 / (10 ** fractional)
    serial = round(serial / smallest) * smallest
    try:
        moment = base + timedelta(days=serial)
    except (OverflowError, ValueError):
        return "#" * 8
    twelve = any(t.group(0).lower() in ("am/pm", "a/p") for t in tokens)
    out, position = [], 0
    kinds = [t.group(0).lower() for t in tokens]
    for index, token in enumerate(tokens):
        out.append(_literal_text(section[position:token.start()]))
        position = token.end()
        word = token.group(0)
        low = word.lower()
        if low.startswith("[h"):
            out.append(f"{int(serial * 24):0{len(low) - 2}d}")
        elif low.startswith("[m"):
            out.append(f"{int(round(serial * 1440, 6)):0{len(low) - 2}d}")
        elif low.startswith("[s"):
            out.append(f"{int(round(serial * 86400)):0{len(low) - 2}d}")
        elif low == "yyyy":
            out.append(f"{moment.year:04d}")
        elif low == "yy":
            out.append(f"{moment.year % 100:02d}")
        elif low in ("m", "mm") and _is_minute(kinds, index):
            out.append(f"{moment.minute:02d}" if low == "mm" else str(moment.minute))
        elif low == "mmmmm":
            out.append(MONTHS[moment.month - 1][0])
        elif low == "mmmm":
            out.append(MONTHS[moment.month - 1])
        elif low == "mmm":
            out.append(MONTHS[moment.month - 1][:3])
        elif low == "mm":
            out.append(f"{moment.month:02d}")
        elif low == "m":
            out.append(str(moment.month))
        elif low == "dddd":
            out.append(DAYS[moment.weekday()])
        elif low == "ddd":
            out.append(DAYS[moment.weekday()][:3])
        elif low == "dd":
            out.append(f"{moment.day:02d}")
        elif low == "d":
            out.append(str(moment.day))
        elif low in ("hh", "h"):
            hour = moment.hour
            if twelve:
                hour = hour % 12 or 12
            out.append(f"{hour:02d}" if low == "hh" else str(hour))
        elif low in ("ss", "s"):
            out.append(f"{moment.second:02d}" if low == "ss" else str(moment.second))
        elif low.startswith("."):
            digits = len(low) - 1
            out.append("." + f"{moment.microsecond / 1e6:.{digits}f}"[2:])
        elif low == "am/pm":
            text = "AM" if moment.hour < 12 else "PM"
            out.append(text if word[0].isupper() else text.lower())
        elif low == "a/p":
            text = "A" if moment.hour < 12 else "P"
            out.append(text if word[0].isupper() else text.lower())
    out.append(_literal_text(section[position:]))
    return "".join(out)


def _is_minute(kinds, index: int) -> bool:
    """An m after an hour or before a second is a minute, not a month."""
    for back in range(index - 1, -1, -1):
        if kinds[back] in ("h", "hh") or kinds[back].startswith("[h"):
            return True
        if kinds[back] not in ("am/pm", "a/p") and not kinds[back].startswith("."):
            break
    for ahead in range(index + 1, len(kinds)):
        if kinds[ahead] in ("s", "ss") or kinds[ahead].startswith("[s"):
            return True
        if not kinds[ahead].startswith("."):
            break
    return False


#: Excel's 56-colour palette, for [ColorN] and indexed cell colours.
_PALETTE = ["000000", "FFFFFF", "FF0000", "00FF00", "0000FF", "FFFF00", "FF00FF", "00FFFF", "800000", "008000",
            "000080", "808000", "800080", "008080", "C0C0C0", "808080", "9999FF", "993366", "FFFFCC", "CCFFFF",
            "660066", "FF8080", "0066CC", "CCCCFF", "000080", "FF00FF", "FFFF00", "00FFFF", "800080", "800000",
            "008080", "0000FF", "00CCFF", "CCFFFF", "CCFFCC", "FFFF99", "99CCFF", "FF99CC", "CC99FF", "FFCC99",
            "3366FF", "33CCCC", "99CC00", "FFCC00", "FF9900", "FF6600", "666699", "969696", "003366", "339966",
            "003300", "333300", "993300", "993366", "333399", "333333"]
#: Indexed colours 0-7 repeat the first eight; 8-63 are the palette above.
INDEXED = _PALETTE[:8] + _PALETTE
