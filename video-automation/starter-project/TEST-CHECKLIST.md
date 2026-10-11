# Checklist de validação do starter

Use mídia própria ou autorizada. Faça primeiro cópias pequenas; não teste em único original.

## Setup

- [ ] `ffmpeg -version` e `ffprobe -version` mostram versões compatíveis.
- [ ] `python3 scripts/media_preflight.py media/source.mp4` gera JSON e identifica streams.
- [ ] `python3 scripts/render_edl.py edit-plan.json --validate-only` aceita somente paths dentro do workspace.

## Testes de falha esperada

- [ ] Fonte ausente deve falhar antes do render.
- [ ] JSON inválido, intervalo negativo, `end <= start`, `end` além da duração e FPS não inteiro devem falhar.
- [ ] Fonte sem stream de vídeo e fonte com múltiplos streams de vídeo devem falhar com mensagem compreensível.
- [ ] Perfil fora da lista ou fit desconhecido deve falhar.
- [ ] `source` apontando para `../` ou symlink fora da pasta do projeto deve ser recusado.
- [ ] Saída já existente deve falhar sem modificá-la.
- [ ] Se um perfil falhar, nenhum arquivo parcial deve permanecer com nome final.

## Testes de saída

- [ ] Arquivo com áudio e arquivo sem áudio preservam corretamente o estado de áudio.
- [ ] O início/fim de cada corte é assistido para verificar frame errado, silêncio, clique ou áudio truncado.
- [ ] `landscape` = 1920×1080, `vertical` = 1080×1920, `square` = 1080×1080.
- [ ] Duração é aproximadamente a soma dos segmentos e fps corresponde ao plano.
- [ ] `ffprobe` detecta H.264 e AAC quando existe áudio; FFmpeg decodifica cada arquivo até o fim.
- [ ] Reproduzir todos os exports no player-alvo; conferir crop, safe areas, legibilidade, sync e conteúdo.

O sucesso do script cobre verificações determinísticas incluídas. Não valida narrativa, precisão de transcrição, direito de uso, qualidade do corte ou publicação em plataforma.
