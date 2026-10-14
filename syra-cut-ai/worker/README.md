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
  → análise de cena (blurdetect): remove giros de câmera, tremidas e foco perdido
  → linha do tempo por formato: gancho (cold open), jump cuts nas pausas, punch-in alternado
  → enquadramento automático: 9:16 parecido → corte central; 16:9 → fundo desfocado
  → legendas ASS só com palavras reais, curtas, palavra a palavra, no terço inferior
  → render das variantes (cada trecho como entrada própria, 30 fps CFR, cor, flash,
    barra de progresso, voz com EQ + compressor + loudnorm -14 LUFS)
  → QA bloqueante: 1080x1920, h264+aac, duração vs plano, decodificação integral
  → upload em rendered-videos/{user_id}/{job_id}/final_<variante>.mp4 (retentativa: _r2, _r3…)
  → mission_report.json em reports/{user_id}/{job_id}/ (EDL, IA, ffmpeg, sha256)
  → callback READY_FOR_HUMAN_REVIEW ou FAILED (com retentativas)
```

`READY_FOR_HUMAN_REVIEW` nunca é aprovação: alguém precisa assistir e ouvir cada variante.

## Formatos (variantes)

| id | para quê | gancho | jump cut (pausa >) | punch-in | legenda | título + barra | velocidade |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `viral_cut` | retenção máxima (TikTok/Reels) | sim | 0,30 s | alterna 1,00×/1,12× | 3 palavras, maiúsculas, palavra falada em amarelo | sim | 1,0× |
| `clean_caption` | autoridade/explicação | — | 0,80 s | — | até 5 palavras, limpa, menor | — | 1,0× |
| `speed_dynamic` | Shorts rápido | sim | 0,22 s | alterna | 2 palavras, destaque verde | sim | 1,1× |

- **Gancho:** a IA escolhe a frase mais forte (1,5–4,5 s); sem IA, uma frase com pergunta ou
  palavra de curiosidade. Só entra se vier de ≥ 6 s adiante (senão o começo já é o gancho) e
  termina com um flash branco de 0,18 s antes do vídeo.
- **Corte de cena ruim:** borrão medido quadro a quadro; trecho ≥ 0,6 s bem acima do normal do
  próprio vídeo (giro de câmera, tremida) sai do corte.
- **Legenda:** nunca atravessa um corte; nunca vem de texto da IA.
- Presets em `src/presets.ts`.

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

## Servidor de teste local (ver o vídeo editado)

```bash
cd syra-cut-ai/worker
npm ci
npm run dev:local          # http://localhost:8787/dev
```

Na página, envie o vídeo e, se quiser, a legenda `.srt`/`.vtt` (CapCut, YouTube…). Os 3 formatos
aparecem lado a lado para assistir e baixar; os arquivos ficam em `.local-storage/`.

Transcrição sem `.srt` (escolha uma):

- `OPENAI_API_KEY=...` (Whisper da OpenAI, padrão);
- local e grátis: `pip install faster-whisper` e
  `STT_PROVIDER=command STT_COMMAND="python3 scripts/transcribe_local.py" npm run dev:local`
  (baixa o modelo na 1ª vez; `WHISPER_LOCAL_MODEL=small` por padrão).

IA editorial (`ANTHROPIC_API_KEY`) é opcional no teste: sem ela, a heurística local escolhe
trechos e gancho. O modo local só sobe com `ALLOW_INSECURE_DEV=1` e escuta em `127.0.0.1`.

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
