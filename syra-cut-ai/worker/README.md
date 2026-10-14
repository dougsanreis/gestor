# SYRA Video Worker

Worker externo do SYRA VideoOS. Recebe o job do app, roda o pipeline real e devolve o resultado por
callback. O processamento pesado (FFmpeg, transcrição, IA) não roda no Lovable.

## Pipeline

```
POST /process (ou /jobs)          ← app, com Authorization: Bearer WORKER_API_KEY
  → valida payload (job_id seguro, hosts permitidos, 9:16)
  → baixa a fonte em stream (limite de bytes e de tempo)
  → preflight ffprobe: sem vídeo / sem áudio / duração inválida → FAILED na hora
    avisos: taxa variável (celular/WhatsApp), resolução baixa
  → extrai áudio (MP3 mono 16 kHz) → Whisper com tempo por palavra e por frase
    sem transcrição → FAILED na hora (o app reprova READY sem transcrição real)
  → IA editorial com a transcrição COM TEMPOS: Claude → Grok → Mistral → heurística local
  → EDL: valida, encaixa os cortes nos limites de frase, ordena, junta, limita a max_duration
  → enquadramento automático: 9:16 parecido → corte central; 16:9 → fundo desfocado
  → legendas ASS só com palavras reais do Whisper, em área segura (acima da UI do TikTok/Reels)
  → render das variantes (cada trecho como entrada própria, 30 fps CFR, loudnorm)
  → QA bloqueante: 1080x1920, h264+aac, duração vs plano, decodificação integral
  → upload em rendered-videos/{user_id}/{job_id}/final_<variante>.mp4 (retentativa: _r2, _r3…)
  → mission_report.json em reports/{user_id}/{job_id}/ (EDL, IA, ffmpeg, sha256)
  → callback READY_FOR_HUMAN_REVIEW ou FAILED (com retentativas)
```

`READY_FOR_HUMAN_REVIEW` nunca é aprovação: alguém precisa assistir e ouvir cada variante.

## Variantes

| id | legenda | zoom | velocidade |
| --- | --- | --- | --- |
| `viral_cut` | kinetic | push-in suave 1,00→1,06 | 1,0× |
| `clean_caption` | clean | — | 1,0× |
| `speed_dynamic` | dynamic | push-in suave | 1,08× |

## Rodar

```bash
cp .env.example .env    # preencha; WORKER_API_KEY e CALLBACK_ALLOWED_HOSTS são obrigatórios
npm ci
npm run dev
```

Docker (inclui FFmpeg e a fonte Inter):

```bash
docker build -t syra-worker .
docker run --env-file .env -p 8787:8787 syra-worker
```

No app (secrets da Lovable Cloud): `WORKER_API_URL`, `WORKER_API_KEY` (mesmo valor) e
`APP_PUBLIC_URL` (ex.: `https://syra.lovable.app`).

## Segurança (falha fechado)

- Sem `WORKER_API_KEY` (≥ 24 caracteres) e sem `CALLBACK_ALLOWED_HOSTS`, o worker **não sobe**.
  `ALLOW_INSECURE_DEV=1` libera só para máquina local.
- Bearer comparado em tempo constante; sem CORS (é servidor-para-servidor).
- `job_id` só UUID/slug: ele vira pasta de trabalho (apagada no fim), chave de storage e caminho
  no filtro do FFmpeg.
- Download só de `INPUT_ALLOWED_HOSTS` (padrão: host do `SUPABASE_URL`), via HTTPS, sem redirect.
- Callback só para `CALLBACK_ALLOWED_HOSTS`: ele leva a chave no header.
- Texto da transcrição é dado, não instrução (o prompt da IA diz isso e a legenda é escapada).

## Endpoints

- `POST /process` e `POST /jobs` — enfileira (202; 200 se o mesmo job já está na fila; 429 se a fila está cheia)
- `GET /jobs/:id` — status
- `POST /jobs/:id/retry` — reprocessa um job FAILED
- `GET /health` — `ok` ou `degraded` (sem FFmpeg, storage ou STT nenhum job termina)

## Testes

```bash
npm run typecheck
npm test            # unidade + contrato com o app + render real com FFmpeg
```

`test/contract-app.test.ts` valida o corpo do callback contra uma cópia do schema de
`src/routes/api/public/update-video-job.ts`. Se mudar o schema no app, atualize a cópia.
