import re
from dateutil import parser as dateutil_parser
from datetime import datetime


def extract_int(x) -> int | None:
    """
    Extracts an integer from a string, handling European number formatting.

    Examples:
        "200.000" -> 200000 (dot as thousand separator)
        "200,000" -> 200000 (comma as thousand separator)
        "200m2"   -> 200
        "3 300 000 kr" -> 3300000
        "97 m²"   -> 97
    """
    if not isinstance(x, str):
        return None
    uten_mellomrom = re.sub(r'\s', '', x)
    match = re.search(r'[\d.,]+', uten_mellomrom)
    if not match:
        return None
    nummer_str = match.group(0)
    has_separator = '.' in nummer_str or ',' in nummer_str
    if ',' in nummer_str and '.' in nummer_str:
        if nummer_str.rfind(',') > nummer_str.rfind('.'):
            nummer_str_parsed = nummer_str.replace('.', '').replace(',', '.')
        else:
            nummer_str_parsed = nummer_str.replace(',', '')
    elif ',' in nummer_str:
        nummer_str_parsed = nummer_str.replace(',', '.')
    else:
        nummer_str_parsed = nummer_str
    try:
        nummer_float = float(nummer_str_parsed)
    except (ValueError, TypeError):
        return None
    if not has_separator:
        if nummer_float.is_integer():
            return int(nummer_float)
        else:
            return None
    else:
        multiplied = nummer_float * 1000
        return int(round(multiplied))


def extract_float(x) -> float | None:
    """
    Extracts a float number from a string, handling European number formatting.

    Examples:
        "200.000" -> 200.0
        "200,000" -> 200.0
        "200m2"   -> 200.0
        "435,5 kr" -> 435.5
    """
    if not isinstance(x, str):
        return None
    uten_mellomrom = re.sub(r'\s', '', x)
    match = re.search(r'[\d.,]+', uten_mellomrom)
    if not match:
        return None
    nummer_str = match.group(0)
    if ',' in nummer_str and '.' in nummer_str:
        if nummer_str.rfind(',') > nummer_str.rfind('.'):
            nummer_str = nummer_str.replace('.', '').replace(',', '.')
        else:
            nummer_str = nummer_str.replace(',', '')
    elif ',' in nummer_str:
        nummer_str = nummer_str.replace(',', '.')
    try:
        return float(nummer_str)
    except (ValueError, TypeError):
        return None


def extract_postnummer(x) -> str | None:
    """Extracts a 4-digit Norwegian postal code from a string."""
    if not isinstance(x, str):
        return x
    match_ = re.search(r'\d{4}', x)
    if match_:
        return match_.group()
    return None


def extract_datetime(x) -> datetime | None:
    """
    Extracts a datetime object from a string, handling both English and Norwegian month names.

    Examples:
        'July 12, 2025, at 12:23 PM' -> datetime(2025, 7, 12, 12, 23)
        '2024-05-28 13:35:00'         -> datetime(2024, 5, 28, 13, 35)
        '4. februar 2025, 17:12'      -> datetime(2025, 2, 4, 17, 12)
        '15. jan. 2026 22:19'         -> datetime(2026, 1, 15, 22, 19)
    """
    if not isinstance(x, str):
        return None
    x = x.replace('\u202f', ' ')
    nor_abbrev = {
        'jan.': 'Jan', 'feb.': 'Feb', 'mar.': 'Mar', 'apr.': 'Apr',
        'mai.': 'May', 'jun.': 'Jun', 'jul.': 'Jul', 'aug.': 'Aug',
        'sep.': 'Sep', 'okt.': 'Oct', 'nov.': 'Nov', 'des.': 'Dec',
    }
    nor_to_eng = {
        'januar': 'January',
        'februar': 'February',
        'mars': 'March',
        'april': 'April',
        'mai': 'May',
        'juni': 'June',
        'juli': 'July',
        'august': 'August',
        'september': 'September',
        'oktober': 'October',
        'november': 'November',
        'desember': 'December',
    }
    x_trans = x.lower()
    for nor, eng in nor_abbrev.items():
        x_trans = x_trans.replace(nor, eng)
    for nor, eng in nor_to_eng.items():
        x_trans = re.sub(r'\b' + re.escape(nor) + r'\b', eng, x_trans, flags=re.IGNORECASE)
    try:
        dt = dateutil_parser.parse(x_trans, fuzzy=True)
        return dt
    except (ValueError, TypeError):
        return None
