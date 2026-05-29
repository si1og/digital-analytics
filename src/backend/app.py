import math
import re
from typing import Any, Literal

from coloraide.everything import ColorAll as Color
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


Format = Literal["HEX", "sRGB", "CIELAB", "LCH", "OKLCH", "CMYK"]

FORMAT_TO_SPACE: dict[str, str] = {
    "HEX": "srgb",
    "sRGB": "srgb",
    "CIELAB": "lab",
    "LCH": "lch",
    "OKLCH": "oklch",
    "CMYK": "cmyk",
}

SUPPORTED_FORMATS = list(FORMAT_TO_SPACE.keys())

HEX_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
FUNCTION_PATTERN = re.compile(r"^(?P<name>rgb|lab|lch|oklch)\((?P<body>.*)\)$", re.IGNORECASE)
CMYK_PATTERN = re.compile(r"^color\(\s*--cmyk\s+(?P<body>.*)\)$", re.IGNORECASE)

app = FastAPI(title="Palette Contrast API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConvertRequest(BaseModel):
    value: str = Field(min_length=1, max_length=64)
    output_format: Format = "HEX"


class AnalyzeRequest(ConvertRequest):
    shade_count: int = Field(default=9, ge=1)
    text_color: str | None = Field(default=None, max_length=64)


def split_components(body: str) -> list[str]:
    if "/" in body:
        raise HTTPException(status_code=400, detail="Альфа-канал не поддерживается")
    return [part for part in re.split(r"[\s,]+", body.strip()) if part]


def parse_component(token: str, *, allow_percent: bool = False) -> tuple[float, bool]:
    is_percent = token.endswith("%")
    if is_percent and not allow_percent:
        raise HTTPException(status_code=400, detail=f"Проценты здесь не поддерживаются: {token}")

    raw = token[:-1] if is_percent else token
    try:
        value = float(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Некорректное числовое значение: {token}") from exc

    if not math.isfinite(value):
        raise HTTPException(status_code=400, detail=f"Некорректное числовое значение: {token}")

    return value, is_percent


def check_range(name: str, value: float, min_value: float, max_value: float) -> None:
    if value < min_value or value > max_value:
        raise HTTPException(
            status_code=400,
            detail=f"{name}: значение должно быть в диапазоне {min_value:g}..{max_value:g}",
        )


def validate_color_value(value: str) -> str:
    normalized = value.strip()

    if HEX_PATTERN.fullmatch(normalized):
        return normalized

    function_match = FUNCTION_PATTERN.fullmatch(normalized)
    cmyk_match = CMYK_PATTERN.fullmatch(normalized)

    if function_match:
        name = function_match.group("name").lower()
        parts = split_components(function_match.group("body"))

        if len(parts) != 3:
            raise HTTPException(status_code=400, detail=f"{name}() должен содержать ровно 3 компонента")

        parsed = [parse_component(part, allow_percent=name == "rgb") for part in parts]
        values = [component for component, _ in parsed]

        if name == "rgb":
            for index, (component, is_percent) in enumerate(parsed, start=1):
                if is_percent:
                    check_range(f"sRGB, компонент {index}", component, 0, 100)
                else:
                    check_range(f"sRGB, компонент {index}", component, 0, 255)
        elif name == "lab":
            check_range("CIELAB, светлота L", values[0], 0, 100)
            check_range("CIELAB, координата a", values[1], -128, 127)
            check_range("CIELAB, координата b", values[2], -128, 127)
        elif name == "lch":
            check_range("LCH, светлота L", values[0], 0, 100)
            check_range("LCH, насыщенность C", values[1], 0, 150)
            check_range("LCH, тон H", values[2], 0, 360)
        elif name == "oklch":
            check_range("OKLCH, светлота L", values[0], 0, 1)
            check_range("OKLCH, насыщенность C", values[1], 0, 0.4)
            check_range("OKLCH, тон H", values[2], 0, 360)

        return normalized

    if cmyk_match:
        parts = split_components(cmyk_match.group("body"))

        if len(parts) != 4:
            raise HTTPException(status_code=400, detail="color(--cmyk ...) должен содержать ровно 4 компонента")

        for index, part in enumerate(parts, start=1):
            component, is_percent = parse_component(part, allow_percent=True)
            if is_percent:
                check_range(f"CMYK, компонент {index}", component, 0, 100)
            else:
                check_range(f"CMYK, компонент {index}", component, 0, 1)

        return normalized

    raise HTTPException(status_code=400, detail="Неподдерживаемый формат цвета")


def parse_color(value: str) -> Color:
    normalized = validate_color_value(value)
    try:
        return Color(normalized)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Некорректное значение цвета") from exc


def as_hex(color: Color) -> str:
    return color.convert("srgb").fit("srgb").to_string(hex=True)


def format_color(color: Color, output_format: str) -> str:
    if output_format == "HEX":
        return as_hex(color)

    space = FORMAT_TO_SPACE[output_format]
    converted = color.convert(space)
    if space == "srgb":
        converted = converted.fit("srgb")
    return converted.to_string(precision=4)


def all_formats(color: Color) -> dict[str, str]:
    return {name: format_color(color, name) for name in SUPPORTED_FORMATS}


def wcag_contrast(background: Color, text: Color) -> float:
    return round(text.convert("srgb").fit("srgb").contrast(background.convert("srgb").fit("srgb"), method="wcag21"), 2)


def contrast_info(background: Color, text_color: str | None = None) -> dict[str, Any]:
    black = Color("black")
    white = Color("white")
    custom_color = parse_color(text_color) if text_color else None
    black_ratio = wcag_contrast(background, black)
    white_ratio = wcag_contrast(background, white)
    recommended_name = "black" if black_ratio >= white_ratio else "white"
    recommended = black if recommended_name == "black" else white
    custom = wcag_contrast(background, custom_color) if custom_color else None

    return {
        "black": black_ratio,
        "white": white_ratio,
        "recommended": recommended_name,
        "recommended_hex": as_hex(recommended),
        "custom": custom,
        "text_hex": as_hex(custom_color) if custom_color else None,
        "passes_aa": max(black_ratio, white_ratio) >= 4.5,
    }


def generate_shades(color: Color, count: int, output_format: str, text_color: str | None = None) -> list[dict[str, Any]]:
    oklch = color.convert("oklch")
    lightness, chroma, hue = oklch.coords()
    shades = []
    lightness_values = [lightness] if count == 1 else [0.08 + (0.86 * index / (count - 1)) for index in range(count)]

    for index, target_lightness in enumerate(lightness_values):
        shade = Color("oklch", [target_lightness, chroma, hue]).convert("srgb").fit("srgb")
        shades.append(
            {
                "index": index + 1,
                "is_source_position": abs(target_lightness - lightness) < 0.06,
                "hex": as_hex(shade),
                "value": format_color(shade, output_format),
                "formats": all_formats(shade),
                "contrast": contrast_info(shade, text_color),
            }
        )

    return shades


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/formats")
def formats() -> dict[str, list[str]]:
    return {"formats": SUPPORTED_FORMATS}


@app.post("/api/colors/convert")
def convert_color(payload: ConvertRequest) -> dict[str, Any]:
    color = parse_color(payload.value)
    return {
        "input": payload.value,
        "detected_space": color.space(),
        "output_format": payload.output_format,
        "value": format_color(color, payload.output_format),
        "formats": all_formats(color),
        "hex": as_hex(color),
    }


@app.post("/api/colors/analyze")
def analyze_color(payload: AnalyzeRequest) -> dict[str, Any]:
    color = parse_color(payload.value)
    return {
        "input": payload.value,
        "detected_space": color.space(),
        "output_format": payload.output_format,
        "hex": as_hex(color),
        "value": format_color(color, payload.output_format),
        "formats": all_formats(color),
        "contrast": contrast_info(color, payload.text_color),
        "text_color": contrast_info(color, payload.text_color)["text_hex"],
        "shades": generate_shades(color, payload.shade_count, payload.output_format, payload.text_color),
    }
