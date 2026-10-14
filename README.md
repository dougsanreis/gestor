# gestor

## Automação de vídeo com Claude Code

O pacote em [`video-automation/`](video-automation/README.md) traz pesquisa, arquitetura, prompts e um projeto inicial (`starter-project/`). Esse projeto renderiza cortes de uma única fonte em 16:9, 9:16 e 1:1 com FFmpeg, depois faz um QA técnico.

```bash
cd video-automation/starter-project
python3 scripts/media_preflight.py media/source.mp4
cp edit-plan.example.json edit-plan.json   # ajuste fonte e timecodes
python3 scripts/render_edl.py edit-plan.json --validate-only
python3 scripts/render_edl.py edit-plan.json --preview --job v1
python3 scripts/render_edl.py edit-plan.json --job v1
```

Abra `claude` dentro de `starter-project/` para usar a skill `/video-pipeline`. Vídeos em `media/` e `exports/` ficam fora do git. Cada versão vai para `exports/<job>/`.

## SYRA Cut AI

[`syra-cut-ai/`](syra-cut-ai/) é a ferramenta: app Lovable (TanStack Start + Supabase) e o worker de
render em [`syra-cut-ai/worker/`](syra-cut-ai/worker/README.md). O worker aplica as regras do kit acima:
preflight antes de gastar, legenda só de transcrição real, cortes validados e encaixados na fala,
QA bloqueante (dimensões, codecs, duração, decodificação integral), arquivos versionados sem
sobrescrever e configuração que falha fechado. Regras para o Claude Code em
[`syra-cut-ai/CLAUDE.md`](syra-cut-ai/CLAUDE.md); contrato app ↔ worker em
[`syra-cut-ai/docs/worker-contract.md`](syra-cut-ai/docs/worker-contract.md).

## CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda em push e PR:

- **worker:** typecheck, lint, testes (unidade, contrato com o app e render real com FFmpeg) e build;
- **app:** typecheck e build;
- **video-kit:** smoke test do starter (`video-automation/starter-project/tests/smoke.sh`).
