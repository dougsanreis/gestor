# Prompts e operação prática

Os prompts abaixo foram pensados para uso no Claude Code dentro da raiz do projeto inicial. Substitua os campos entre colchetes. Eles não substituem aprovação editorial nem inspeção.

## 1. Briefing inicial

```text
Analise o projeto e a mídia [CAMINHO]. Ainda não renderize.
Objetivo do vídeo: [OBJETIVO]. Público: [PÚBLICO]. Destino/plataforma: [DESTINO].
Idiomas: [IDIOMA]. Duração desejada: [INTERVALO]. Proporções necessárias: [16:9, 9:16, 1:1, 4:5].
Tom/ritmo: [DESCRIÇÃO]. CTA: [CTA OU NENHUM].
Use somente mídia de origem autorizada: [LISTA]. Elementos que devem permanecer ou ser removidos: [DETALHES].
Faça inventário com media_preflight, liste incertezas e riscos (áudio, enquadramento, cortes, legenda).
Proponha uma estrutura em timecodes da fonte e diferencie o que observou do que está inferindo.
Não altere mídia, não crie plano final nem publique. Pergunte apenas escolhas que mudam materialmente o conteúdo.
```

## 2. Plano de edição para aprovação

```text
Com base no briefing aprovado, gere edit-plan.json conforme edit-plan.schema.json.
Use segmentos em segundos da fonte, mantenha a ordem narrativa e explique o motivo de cada trecho.
Não invente transcrição. Caso os timecodes venham de transcrição automática, marque baixa confiança e peça revisão nos nomes próprios, números e frases cortadas.
Não escolha trechos que removam ressalvas ou mudem o sentido. Não inclua efeitos ou texto não solicitado.
Valide com: python3 scripts/render_edl.py edit-plan.json --validate-only
Mostre uma lista humana de in/out e duração total para aprovação antes do render.
```

## 3. Render de três proporções

```text
Leia CLAUDE.md e a skill /video-pipeline. Execute somente o plano aprovado edit-plan.json.
Comece em preview curto se esta combinação de fonte e perfis ainda não foi aprovada.
Explique o efeito cover/contain e gere exports sem sobrescrever arquivos existentes.
Depois faça QA técnico; liste codecs, dimensões, duração e status de decodificação por saída.
Não declare a edição pronta para publicação até que eu tenha assistido e ouvido cada proporção.
```

## 4. Adaptar entrevista longa a cortes curtos

```text
Analise a entrevista [ARQUIVO] para sugerir até [N] cortes de [DURAÇÃO] sobre o tema [TEMA].
Por enquanto, apenas transcrição/segmentos propostos; não renderize.
Para cada corte, traga timecode da fonte, frase exata e contexto antes/depois, justificativa editorial, confiança e risco de retirar nuance.
Não sintetize a fala como se a pessoa tivesse dito algo que não disse. Não invente captions, nomes ou métricas.
Peça autorização para cada corte escolhido. Só depois converta os trechos aprovados para o plano compatível com a base.
```

Esse caso vai além do render incluído: o plano de exemplo suporta uma fonte, mas não grava automaticamente transcrição, não gera várias opções de corte nem faz diarização. Use ferramenta de transcrição revisada e aumente a camada editorial antes de automatizar.

## 5. Legendas e acessibilidade

```text
Crie primeiro uma transcrição timestamped sem queimar a legenda no vídeo.
Entregue SRT/VTT sidecar em [IDIOMA] e sinalize palavras de baixa confiança.
Mantenha quebras legíveis e sincronização por cue; preserve nomes próprios e números após revisão humana.
Recomende estilo e safe area para cada proporção e apresente uma amostra visual antes de um burn-in.
Não afirme conformidade de acessibilidade sem avaliar requisitos do destino e contexto de uso.
```

O pipeline starter não inclui transcrição ou burn-in de legenda. Essa separação evita fixar erro de transcrição no raster e facilita correção independente.

## 6. Motion graphics com Remotion

Para elementos gráficos determinísticos, siga o setup oficial atual: inicializar projeto Remotion, instalar a Remotion Agent Skill com o comando oficial atual, abrir o preview e iniciar Claude Code dentro do projeto. Uma solicitação útil:

```text
Crie um template Remotion parametrizado para uma sequência vertical 1080x1920 a 30 fps.
Inputs: title, subtitle, presenterVideo, brandColor e captions.
Garanta que título e legenda permaneçam em safe area configurável. Use componentes e dados separados do código visual.
Faça o preview da composição e teste pelo menos um caso normal, um título longo, uma legenda longa e um input sem áudio.
Renderize apenas um preview. Não substitua exports existentes. Liste versão do Remotion/Node, props e limitações visuais.
```

O guia oficial Remotion orienta uso com Claude Code e Node.js; a linha de comando de render é documentada com argumentos de composição, props, dimensão, fps, codec e saída [1] [2]. Essa rota é recomendada para texto animado, layout, placares, gráficos e conteúdo gerado em lote. Para footage editorial simples, o render FFmpeg deste pacote é menor e mais fácil de reproduzir.

## 7. Prompt para revisão de qualidade

```text
Faça somente revisão, não altere arquivos. Para cada export, use ffprobe e verifique dimensões, duração, codecs e streams.
Decode o arquivo completo com FFmpeg. Inspecione ao menos frames inicial/final e cada fronteira de corte.
Relate separadamente: checks técnicos objetivos; dúvidas de áudio/visual que precisam de audição humana; riscos editoriais que não podem ser confirmados por metadados.
Não considere silêncio como erro sem contexto, não use heurística de imagem isolada para rejeitar ação e não declare teste visual se não assistiu ao vídeo.
```

## Fluxo de comandos resumido

```bash
cd <pasta-do-projeto>
python3 scripts/media_preflight.py media/source.mp4
cp edit-plan.example.json edit-plan.json
# editar fonte e timecodes no JSON
python3 scripts/render_edl.py edit-plan.json --validate-only
python3 scripts/render_edl.py edit-plan.json
```

O script não sobrescreve os nomes de saída; para renderizar revisão nova, arquive/mova os exports em uma pasta datada e faça a ação manualmente, ou altere o planejamento de versionamento. Não apague outputs automaticamente.

## Referências

[1]: https://www.remotion.dev/docs/ai/coding-agents "Remotion: Prompting videos with coding agents"
[2]: https://www.remotion.dev/docs/cli/render "Remotion: render CLI"
