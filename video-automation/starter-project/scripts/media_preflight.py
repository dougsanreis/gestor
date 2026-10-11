#!/usr/bin/env python3
"""Inspect a media file with ffprobe. Read-only; emits a JSON report."""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: python3 scripts/media_preflight.py <arquivo>", file=sys.stderr)
        return 2
    source = Path(sys.argv[1]).expanduser().resolve()
    if not source.is_file():
        print(f"Arquivo não encontrado: {source}", file=sys.stderr)
        return 2
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        print("ffprobe não encontrado. Instale FFmpeg/FFprobe.", file=sys.stderr)
        return 2
    cmd = [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode:
        print(result.stderr.strip() or "ffprobe falhou", file=sys.stderr)
        return result.returncode
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    fmt = data.get("format", {})
    warnings = []
    if not video:
        warnings.append("Nenhum stream de vídeo detectado; o render de vídeo não poderá continuar.")
    if len(video) > 1:
        warnings.append("Há mais de um stream de vídeo; escolha explicitamente qual usar antes de editar.")
    if not audio:
        warnings.append("Nenhum stream de áudio detectado; o export será silencioso.")
    def rate(value: str | None) -> float | None:
        try:
            n, d = (value or "0/1").split("/", 1)
            return round(float(n) / float(d), 4) if float(d) and float(n) else None
        except (ValueError, ZeroDivisionError, TypeError):
            return None

    if video:
        v = video[0]
        fps, fps_avg = rate(v.get("r_frame_rate")), rate(v.get("avg_frame_rate"))
        # Celular/WhatsApp costuma gravar com taxa variável: r_frame_rate vira 120 e a média real fica ~27-30.
        if fps and fps_avg and abs(fps - fps_avg) / fps_avg > 0.05:
            warnings.append(f"Taxa de quadros variável (nominal {fps:g}, média {fps_avg:g}); "
                            f"use fps do plano próximo da média (ex.: {min(60, max(24, round(fps_avg)))}).")
        w, h = v.get("width") or 0, v.get("height") or 0
        if w and h and min(w, h) < 720:
            warnings.append(f"Resolução baixa ({w}x{h}); exportar em 1080p amplia a imagem e pode ficar suave. "
                            "Para proporções diferentes da fonte, prefira fit=contain.")
    else:
        v, fps, fps_avg = {}, None, None
    report = {
        "source": str(source),
        "size_bytes": source.stat().st_size,
        "container": fmt.get("format_name"),
        "duration_seconds": float(fmt["duration"]) if fmt.get("duration") else None,
        "video": {
            "codec": v.get("codec_name"), "width": v.get("width"), "height": v.get("height"),
            "fps_nominal": fps, "fps_average": fps_avg, "pixel_format": v.get("pix_fmt"), "color_space": v.get("color_space"),
            "rotation_tag": v.get("tags", {}).get("rotate")
        } if video else None,
        "audio": [{"codec": s.get("codec_name"), "sample_rate": s.get("sample_rate"),
                   "channels": s.get("channels"), "layout": s.get("channel_layout")} for s in audio],
        "warnings": warnings,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if video else 1


if __name__ == "__main__":
    raise SystemExit(main())
