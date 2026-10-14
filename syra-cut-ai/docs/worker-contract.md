# SYRA VideoOS — Contrato do Worker Externo

O processamento pesado de vídeo (ffprobe, extração de áudio, transcrição, FFmpeg)
**não roda na Lovable**. Ele é delegado a um worker externo via HTTP. O app aciona
o worker e recebe o resultado por callback.

## Configuração

Defina os secrets na Lovable Cloud:

| Secret           | Descrição                                                         |
| ---------------- | ----------------------------------------------------------------- |
| `WORKER_API_URL` | Base URL do worker (ex.: `https://worker.exemplo.com`)            |
| `WORKER_API_KEY` | Bearer token compartilhado entre app e worker (≥ 24 caracteres)   |
| `APP_PUBLIC_URL` | URL pública do app, usada no `callback_url` (ex.: `https://syra.lovable.app`) |
| `ANTHROPIC_MODEL` | Opcional. Modelo do roteador de IA do app (padrão `claude-opus-5-5`) |

No worker, `CALLBACK_ALLOWED_HOSTS` precisa conter o host de `APP_PUBLIC_URL`, e
`INPUT_ALLOWED_HOSTS` (padrão: host do `SUPABASE_URL`) o host das signed URLs. Fora da lista, o
worker recusa o job com 400. Veja `worker/README.md`.

Sem esses secrets, o app cria o job e o mantém em `QUEUED`, registrando um evento
`CONFIG_REQUIRED`. Nenhuma legenda, título ou render é inventado.

## 1. App → Worker

```
POST {WORKER_API_URL}/process
Authorization: Bearer {WORKER_API_KEY}
Content-Type: application/json

{
  "job_id": "uuid",
  "user_id": "uuid",
  "source_file_url": "https://...signed-url...",
  "target_format": "9:16",
  "max_duration": 75,
  "output_profiles": ["tiktok_viral", "reels_premium", "shorts_clean"],
  "callback_url": "https://<app>/api/public/update-video-job"
}
```

O `source_file_url` é uma signed URL temporária (1h) do bucket `source-videos`.

O worker também aceita o formato de `video-worker-client.server.ts` (`target_ratio`,
`variants: [{ id, speed, zoom, captions }]`, `ai_plan`). `job_id` precisa ser UUID ou slug
`[A-Za-z0-9_-]`; só `9:16` é suportado; `max_duration` é respeitado (5–180 s).

## 2. Pipeline esperado no worker

1. `ffprobe` do arquivo de origem
2. extração de áudio
3. transcrição via Whisper com tempo por palavra e por frase (sem transcrição → `FAILED` antes do render)
4. plano editorial da IA sobre a transcrição com tempos; cortes encaixados nos limites de frase
5. pausas longas removidas (heurística local quando a IA falha)
6. título a partir do transcript
7. legenda ASS só com palavras reais, em área segura
8. render FFmpeg (9:16, 1080×1920, h264/aac, 30 fps, loudnorm), enquadramento automático
9. validação: ffprobe + duração vs plano + decodificação integral
10. upload do MP4 final no bucket `rendered-videos` (sem sobrescrever)
11. `mission_report.json` no bucket `reports`
12. callback para o app (com retentativas)

### Organização de storage

```
source-videos/{user_id}/{job_id}/source.mp4
rendered-videos/{user_id}/{job_id}/final_viral_cut.mp4      (retentativa: final_viral_cut_r2.mp4)
rendered-videos/{user_id}/{job_id}/final_clean_caption.mp4
rendered-videos/{user_id}/{job_id}/final_speed_dynamic.mp4
reports/{user_id}/{job_id}/mission_report.json
```

## 3. Worker → App (callback)

```
POST {callback_url}   ->  /api/public/update-video-job
Authorization: Bearer {WORKER_API_KEY}
Content-Type: application/json
```

### Sucesso

```json
{
  "job_id": "uuid",
  "status": "READY_FOR_HUMAN_REVIEW",
  "progress": 100,
  "output_file_url": "https://...",
  "output_file_path": "{user_id}/{job_id}/final_viral_cut.mp4",
  "transcript": "texto real transcrito...",
  "title_suggestion": "título baseado no transcript",
  "virality_score": 78,
  "technical_report": {
    "width": 1080,
    "height": 1920,
    "codec": "h264",
    "duration": 45.2,
    "cuts": 12,
    "subtitle_words": 180
  }
}
```

### Falha

```json
{
  "job_id": "uuid",
  "status": "FAILED",
  "error_message": "descrição do erro"
}
```

## Regras de qualidade (aplicadas pelo app)

O status só é aceito como `READY_FOR_HUMAN_REVIEW` quando **todas** as condições
abaixo forem verdadeiras. Caso contrário, o app força `FAILED`:

- `output_file_url` presente
- `technical_report.width == 1080`
- `technical_report.height == 1920`
- `technical_report.codec == "h264"`
- `technical_report.duration > 3`
- `transcript` não vazio (legenda só vem de transcrição real)

`READY_FOR_HUMAN_REVIEW` **nunca** significa aprovação automática — sempre exige
revisão humana.

## Status progressivos sugeridos

Durante o processamento, o worker pode emitir callbacks intermediários atualizando
`status` e `progress`:

`QUEUED → PROCESSING → TRANSCRIBING → ANALYZING → CUTTING → RENDERING → VALIDATING → READY_FOR_HUMAN_REVIEW`

## Updates progressivos

Cada callback é registrado em `video_job_events`, alimentando o painel de logs e os
updates em tempo real (Supabase Realtime) na UI.
