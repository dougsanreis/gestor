# gestor

## Automação de vídeo com Claude Code

O pacote em [`video-automation/`](video-automation/README.md) traz pesquisa, arquitetura, prompts e um projeto inicial (`starter-project/`). Esse projeto renderiza cortes de uma única fonte em 16:9, 9:16 e 1:1 com FFmpeg, depois faz um QA técnico.

```bash
cd video-automation/starter-project
python3 scripts/media_preflight.py media/source.mp4
cp edit-plan.example.json edit-plan.json   # ajuste fonte e timecodes
python3 scripts/render_edl.py edit-plan.json --validate-only
python3 scripts/render_edl.py edit-plan.json
```

Abra `claude` dentro de `starter-project/` para usar a skill `/video-pipeline`. Vídeos em `media/` e `exports/` ficam fora do git.
