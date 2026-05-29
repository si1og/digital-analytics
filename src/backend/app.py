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


def parse_color(value: str) -> Color:
    try:
        return Color(value.strip())
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid color value") from exc


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
