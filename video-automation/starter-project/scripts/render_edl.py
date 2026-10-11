#!/usr/bin/env python3
"""Render a single-source edit plan into H.264 MP4 aspect-ratio variants."""
from __future__ import annotations
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

PROFILES = {"landscape": (1920, 1080), "vertical": (1080, 1920), "square": (1080, 1080)}


def fail(message: str) -> None:
    raise ValueError(message)


def probe(path: Path, ffprobe: str) -> dict[str, Any]:
    cp = subprocess.run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                        capture_output=True, text=True, check=False)
    if cp.returncode:
        fail(f"ffprobe falhou para {path}: {cp.stderr.strip()}")
    try:
        return json.loads(cp.stdout)
    except json.JSONDecodeError as exc:
        fail(f"Resposta ffprobe inválida: {exc}")


def safe_inside(root: Path, relative: str, label: str) -> Path:
    p = Path(relative)
    if p.is_absolute():
        fail(f"{label} deve ser um caminho relativo ao projeto: {relative}")
    resolved = (root / p).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        fail(f"{label} aponta para fora do workspace: {relative}")
    return resolved


def validate(plan: dict[str, Any], root: Path, ffprobe: str) -> tuple[Path, float, bool, list[tuple[float, float]]]:
    required = {"version", "source", "fps", "fit", "profiles", "segments"}
    missing = required - plan.keys()
    if missing:
        fail("Campos ausentes no plano: " + ", ".join(sorted(missing)))
    if plan["version"] != 1:
        fail("Somente version=1 é suportado.")
    if isinstance(plan["fps"], bool) or not isinstance(plan["fps"], int) or not 1 <= plan["fps"] <= 120:
        fail("fps precisa ser um inteiro entre 1 e 120.")
    if plan["fit"] not in ("cover", "contain"):
        fail("fit deve ser cover ou contain.")
    profiles = plan["profiles"]
    if (not isinstance(profiles, list) or not profiles
            or any(not isinstance(p, str) or p not in PROFILES for p in profiles)
            or len(set(profiles)) != len(profiles)):
        fail("profiles deve conter perfis únicos: landscape, vertical e/ou square.")
    segments = plan["segments"]
    if not isinstance(segments, list) or not segments:
        fail("O plano precisa de ao menos um segmento.")
    if not isinstance(plan["source"], str) or not plan["source"].strip():
        fail("source precisa ser uma string não vazia.")
    source = safe_inside(root, plan["source"], "source")
    if not source.is_file():
        fail(f"Fonte não encontrada: {source}")
    info = probe(source, ffprobe)
    streams = info.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if not videos:
        fail("A fonte não contém stream de vídeo.")
    if len(videos) > 1:
        fail("A fonte contém múltiplos streams de vídeo; este starter exige escolha/normalização prévia.")
    try:
        duration = float(info["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        fail("Não foi possível determinar a duração da fonte.")
    if not math.isfinite(duration) or duration <= 0:
        fail("Duração da fonte inválida.")
    normalized: list[tuple[float, float]] = []
    for i, seg in enumerate(segments, 1):
        if not isinstance(seg, dict) or "start" not in seg or "end" not in seg:
            fail(f"Segmento {i} precisa de start e end em segundos.")
        start, end = seg["start"], seg["end"]
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            fail(f"Segmento {i}: start/end devem ser números.")
        start, end = float(start), float(end)
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            fail(f"Segmento {i}: intervalo inválido ({start}, {end}).")
        if end > duration + 0.05:
            fail(f"Segmento {i} termina após a duração da fonte ({duration:.3f}s).")
        normalized.append((start, end))
    return source, duration, bool(audios), normalized


def build_graph(segments: list[tuple[float, float]], profile: str, fit: str, fps: int, has_audio: bool) -> str:
    w, h = PROFILES[profile]
    n = len(segments)
    parts = []
    if n == 1:
        parts.append("[0:v:0]null[vsrc0]")
    else:
        parts.append(f"[0:v:0]split={n}" + "".join(f"[vsrc{i}]" for i in range(n)))
    for i, (start, end) in enumerate(segments):
        if fit == "cover":
            framing = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
        else:
            framing = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
        parts.append(f"[vsrc{i}]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS,{framing},setsar=1,fps={fps},format=yuv420p[v{i}]")
    if has_audio:
        if n == 1:
            parts.append("[0:a:0]anull[asrc0]")
        else:
            parts.append(f"[0:a:0]asplit={n}" + "".join(f"[asrc{i}]" for i in range(n)))
        for i, (start, end) in enumerate(segments):
            parts.append(f"[asrc{i}]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
        parts.append(f"{concat_inputs}concat=n={n}:v=1:a=1[vout][aout]")
    else:
        concat_inputs = "".join(f"[v{i}]" for i in range(n))
        parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vout]")
    return ";".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", help="Caminho para edit-plan.json")
    parser.add_argument("--validate-only", action="store_true", help="validar plano/fonte sem renderizar")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    plan_path = Path(args.plan).expanduser().resolve()
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        print("Instale FFmpeg e FFprobe e confirme que estão no PATH.", file=sys.stderr)
        return 2
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            fail("O plano deve ser um objeto JSON.")
        source, source_duration, has_audio, segments = validate(plan, root, ffprobe)
        expected_duration = sum(end - start for start, end in segments)
        output_dir = (root / "exports").resolve()
        try:
            output_dir.relative_to(root)
        except ValueError:
            fail("A pasta exports aponta para fora do workspace (possível symlink).")
        print(json.dumps({"valid": True, "source": str(source), "source_duration_seconds": round(source_duration, 3),
                          "selected_duration_seconds": round(expected_duration, 3), "has_audio": has_audio,
                          "profiles": plan["profiles"], "fit": plan["fit"]}, ensure_ascii=False, indent=2))
        if args.validate_only:
            return 0
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", source.stem).strip("._") or "video"
        finals = [output_dir / f"{safe_stem}_{profile}.mp4" for profile in plan["profiles"]]
        for final in finals:
            if final.exists() or final.is_symlink():
                fail(f"Saída já existe; não será sobrescrita: {final}")
        outputs = []
        for profile, final in zip(plan["profiles"], finals):
            fd, tmp_name = tempfile.mkstemp(prefix=f".{safe_stem}_{profile}_", suffix=".partial.mp4", dir=output_dir)
            os.close(fd)
            temp = Path(tmp_name)
            temp.unlink()
            graph = build_graph(segments, profile, plan["fit"], plan["fps"], has_audio)
            cmd = [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-i", str(source), "-filter_complex", graph,
                   "-map", "[vout]"]
            if has_audio:
                cmd += ["-map", "[aout]"]
            cmd += ["-map_metadata", "-1", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-r", str(plan["fps"])]
            if has_audio:
                cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
            cmd += ["-movflags", "+faststart", "-y", str(temp)]
            timeout = max(300, int(expected_duration * 120))
            try:
                cp = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
                if cp.returncode:
                    fail(f"FFmpeg falhou no perfil {profile}: {cp.stderr.strip()[-3000:]}")
                check = probe(temp, ffprobe)
                vstreams = [s for s in check.get("streams", []) if s.get("codec_type") == "video"]
                astreams = [s for s in check.get("streams", []) if s.get("codec_type") == "audio"]
                w, h = PROFILES[profile]
                if not vstreams or (vstreams[0].get("width"), vstreams[0].get("height")) != (w, h):
                    fail(f"QA de dimensão falhou no perfil {profile}.")
                if has_audio and not astreams:
                    fail(f"QA de áudio falhou: áudio esperado no perfil {profile}.")
                out_duration = float(check.get("format", {}).get("duration", 0))
                if abs(out_duration - expected_duration) > max(0.35, 2 / plan["fps"]):
                    fail(f"QA de duração fora da tolerância no perfil {profile}: {out_duration:.3f}s vs {expected_duration:.3f}s.")
                decode = subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-i", str(temp), "-f", "null", "-"],
                                        capture_output=True, text=True, check=False, timeout=timeout)
                if decode.returncode:
                    fail(f"Decodificação integral falhou no perfil {profile}: {decode.stderr.strip()[-2000:]}")
                temp.rename(final)
                outputs.append({"profile": profile, "file": str(final), "width": w, "height": h,
                                "duration_seconds": round(out_duration, 3), "video_codec": vstreams[0].get("codec_name"),
                                "audio_codec": astreams[0].get("codec_name") if astreams else None,
                                "full_decode": "passed"})
                print(f"OK: {final}")
            finally:
                if temp.exists():
                    temp.unlink()
        print(json.dumps({"status": "rendered_and_technical_qa_passed", "outputs": outputs}, ensure_ascii=False, indent=2))
        print("Revisão visual/auditiva humana ainda é necessária.")
        return 0
    except (OSError, json.JSONDecodeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
