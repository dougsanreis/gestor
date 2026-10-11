# Starter project: Claude Code + FFmpeg

Este starter gera cortes de uma única fonte com intervalos manuais em segundos e exporta MP4 H.264 em três proporções. Requer Python 3 e FFmpeg/FFprobe no `PATH`. Claude Code é opcional para rodar os scripts, mas necessário para aproveitar a skill de planejamento.

## Preparação

1. Copie uma mídia autorizada para `media/source.mp4` (não use como output a mesma pasta da fonte).
2. Verifique com `python3 scripts/media_preflight.py media/source.mp4`.
3. Copie `edit-plan.example.json` para `edit-plan.json`. Atualize `source`, `fps`, `fit`, `profiles` e os segmentos. Todos os caminhos da fonte precisam permanecer dentro desta pasta.
4. Valide: `python3 scripts/render_edl.py edit-plan.json --validate-only`.
5. Renderize: `python3 scripts/render_edl.py edit-plan.json`.
6. Revise `exports/source_landscape.mp4`, `exports/source_vertical.mp4` e `exports/source_square.mp4` visualmente e em áudio.

Para usar Claude Code, abra o terminal nesta pasta e execute `claude`. A skill disponível é `/video-pipeline`.

## Regras do script

- Só uma fonte e um ou mais trechos dela. A ordem no JSON é a ordem de saída.
- `cover` corta as bordas no centro; `contain` mantém a imagem e adiciona barras pretas. A base não reposiciona pessoa/objeto por IA.
- O script recusa caminhos absolutos/fora do workspace, fonte sem vídeo, múltiplos streams de vídeo, perfis desconhecidos, tempos inválidos e arquivo final já existente.
- O script prova dimensões e duração, confirma áudio quando esperado e decodifica o arquivo inteiro. Isso não prova que o corte é bom.
- MP4/H.264/AAC é o preset implementado, não uma configuração universal para qualquer plataforma. Ajuste perfis/codec com critério e valide no destino.
- Não há suporte à edição de vários arquivos diferentes, captions, transcrição, música ou publicação automática. Veja os guias do pacote pai para extensões.

O arquivo `TEST-CHECKLIST.md` descreve os casos de validação incluídos e os limites dessa base.
