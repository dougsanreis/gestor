#!/usr/bin/env python3
"""Transcrição local para o servidor de teste (STT_PROVIDER=command).

Uso: python3 scripts/transcribe_local.py <audio> <saida.json>
Requer: pip install faster-whisper  (baixa o modelo do Hugging Face na 1ª execução)
Modelo: WHISPER_LOCAL_MODEL (padrão "small"); idioma: WHISPER_LANGUAGE (padrão "pt").
Saída no formato do Whisper: {text, language, segments:[{start,end,text}], words:[{start,end,word}]}.
"""
import json
import os
import sys

from faster_whisper import WhisperModel


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    audio, out_path = sys.argv[1], sys.argv[2]
    model = WhisperModel(os.environ.get("WHISPER_LOCAL_MODEL", "small"), device="cpu", compute_type="int8")
    segs, info = model.transcribe(audio, language=os.environ.get("WHISPER_LANGUAGE", "pt") or None, word_timestamps=True)
    out = {"text": "", "language": info.language, "segments": [], "words": []}
    for s in segs:
        out["segments"].append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()})
        for w in s.words or []:
            out["words"].append({"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word.strip()})
    out["text"] = " ".join(s["text"] for s in out["segments"]).strip()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
