#!/usr/bin/env python3
"""Render a single-source edit plan into H.264 MP4 aspect-ratio variants."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from datetime import datetime
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
    # Cada trecho é uma entrada própria (input i = trecho i), aberta com -ss/-t. Assim o FFmpeg
    # não decodifica a fonte inteira nem guarda quadros na memória quando os trechos estão fora
    # da ordem da fonte (o antigo split+trim chegava a ~2,2 GB com 20 s reordenados em 1080p).
    w, h = PROFILES[profile]
    if fit == "cover":
        framing = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    else:
        framing = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
    parts = []
    for i, (start, end) in enumerate(segments):
        d = end - start
        parts.append(f"[{i}:v:0]trim=duration={d:.6f},setpts=PTS-STARTPTS,{framing},setsar=1,fps={fps},format=yuv420p[v{i}]")
        if has_audio:
            parts.append(f"[{i}:a:0]atrim=duration={d:.6f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{i}]")
    n = len(segments)
    if has_audio:
        parts.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vout][aout]")
    else:
        parts.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vout]")
    return ";".join(parts)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", help="Caminho para edit-plan.json")
    parser.add_argument("--validate-only", action="store_true", help="validar plano/fonte sem renderizar")
    parser.add_argument("--job", help="nome da versão; saída em exports/<job>/ (padrão: data-hora atual)")
    parser.add_argument("--preview", action="store_true",
                        help="render rápido: só os primeiros segundos de cada trecho, encode veloz")
    parser.add_argument("--preview-seconds", type=float, default=3.0,
                        help="segundos por trecho no preview (padrão: 3)")
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
        if args.preview:
            if not math.isfinite(args.preview_seconds) or args.preview_seconds <= 0:
                fail("--preview-seconds precisa ser maior que zero.")
            segments = [(s, min(e, s + args.preview_seconds)) for s, e in segments]
        job = args.job or datetime.now().strftime("%Y%m%d-%H%M%S")
        if args.preview:
            job += "-preview"
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", job):
            fail("--job aceita até 64 caracteres: letras, números, ponto, hífen e sublinhado.")
        expected_duration = sum(end - start for start, end in segments)
        exports_root = (root / "exports").resolve()
        output_dir = (exports_root / job).resolve()
        try:
            output_dir.relative_to(root)
        except ValueError:
            fail("A pasta exports aponta para fora do workspace (possível symlink).")
        print(json.dumps({"valid": True, "source": str(source), "source_duration_seconds": round(source_duration, 3),
                          "selected_duration_seconds": round(expected_duration, 3), "has_audio": has_audio,
                          "profiles": plan["profiles"], "fit": plan["fit"], "preview": args.preview,
                          "output_dir": str(output_dir)}, ensure_ascii=False, indent=2))
        if args.validate_only:
            return 0
        if output_dir.exists() or output_dir.is_symlink():
            fail(f"A versão {job} já existe em exports/; use outro --job. Nada foi sobrescrito.")
        output_dir.mkdir(parents=True)
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", source.stem).strip("._") or "video"
        preset, crf = ("veryfast", "28") if args.preview else ("medium", "20")
        inputs: list[str] = []
        for start, end in segments:
            inputs += ["-ss", f"{start:.6f}", "-t", f"{end - start:.6f}", "-i", str(source)]
        outputs = []
        for profile in plan["profiles"]:
            final = output_dir / f"{safe_stem}_{profile}.mp4"
            temp = output_dir / f".{safe_stem}_{profile}.partial.mp4"
            graph = build_graph(segments, profile, plan["fit"], plan["fps"], has_audio)
            cmd = [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", *inputs, "-filter_complex", graph,
                   "-map", "[vout]"]
            if has_audio:
                cmd += ["-map", "[aout]"]
            cmd += ["-map_metadata", "-1", "-c:v", "libx264", "-preset", preset, "-crf", crf,
                    "-pix_fmt", "yuv420p", "-r", str(plan["fps"])]
            if has_audio:
                cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
            cmd += ["-movflags", "+faststart", "-n", str(temp)]
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
                outputs.append({"profile": profile, "file": final.name, "width": w, "height": h,
                                "duration_seconds": round(out_duration, 3), "video_codec": vstreams[0].get("codec_name"),
                                "audio_codec": astreams[0].get("codec_name") if astreams else None,
                                "full_decode": "passed", "sha256": sha256(final)})
                print(f"OK: {final}")
            finally:
                if temp.exists():
                    temp.unlink()
        version = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, check=False).stdout.splitlines()
        report = {"status": "rendered_and_technical_qa_passed", "job": job, "preview": args.preview,
                  "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                  "plan_file": str(plan_path), "source": plan["source"], "source_size_bytes": source.stat().st_size,
                  "segments_rendered": [{"start": s, "end": e} for s, e in segments],
                  "encode": {"preset": preset, "crf": int(crf)}, "ffmpeg_version": version[0] if version else None,
                  "outputs": outputs}
        (output_dir / "edit-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("Revisão visual/auditiva humana ainda é necessária.")
        return 0
    except (OSError, json.JSONDecodeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
