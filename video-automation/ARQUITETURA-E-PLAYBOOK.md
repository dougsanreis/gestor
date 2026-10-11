# Arquitetura e playbook de vídeo automatizado com Claude Code

## 1. O papel de cada componente

Claude Code deve atuar como **copiloto/orquestrador**, não como codec nem editor visual autônomo. A skill e `CLAUDE.md` guardam regras e procedimentos; scripts Python validam entradas e criam comandos controlados; FFmpeg faz operações previsíveis e rápidas; FFprobe mede o que realmente foi produzido. Remotion complementa a pilha quando animação, composição de elementos HTML/React, templates parametrizados ou render em lote são centrais. A documentação do Remotion fornece um caminho direto para coding agents: projeto em Node.js, skill do Remotion, preview e agente separado [1].

Fluxo de referência:

```text
Brief + mídia original
  → inventário e probe
  → transcrição e/ou amostragem visual (se necessário)
  → plano editorial em JSON (timecodes, cortes, proporções, legendas)
  → validação automática do plano
  → render de preview
  → revisão humana de narrativa, som, enquadramento e direitos
  → render final + sidecars + relatório ffprobe
  → arquivamento versionado (sem publicar automaticamente)
```

A fronteira mais importante é entre **decisão probabilística** e **operação determinística**. Claude pode propor cortes, títulos ou destaques e explicar a justificativa. O plano deve ser validado por código antes do render. FFmpeg aplica uma sequência explícita. QA combina checks de máquina com visualização e audição humanas.

## 2. O que automatizar, e o que revisar

Automatize tarefas repetitivas e verificáveis: inventário, metadados, transcrição inicial, detecção de silêncio como pista, segmentação por timecodes, cortes previamente aprovados, conversão de proporção, legendas sidecar, export e relatórios. Use templates para manter identidade visual.

Trate como **sugestão**, não como verdade: seleção de melhores takes, cortes por emoção, ritmo cômico, factualidade de falas, enquadramento de rosto, remoção de pausas que mudam o sentido, mixagem, correção de cor, sincronia labial, legendas com nomes próprios e interpretação de direitos de terceiros. Não infira consentimento, licenças ou autorização a partir da disponibilidade do arquivo.

## 3. Pontos fortes, fracos e críticos

**Fortes.** A separação entre plano e render deixa a edição auditável e repetível. Uma vez revisado um EDL/JSON, o mesmo plano pode gerar proporções diversas. FFmpeg oferece operações explícitas sobre streams e filtros; FFprobe disponibiliza informações legíveis por máquina para detectar incompatibilidades [2] [3]. Remotion torna elementos gráficos em código reutilizáveis e parametrizáveis, com preview interativo e render pela CLI/API [1] [4]. As skills de Claude Code ajudam a aplicar instruções no momento certo e apoiar procedimentos maiores sem carregar cada instrução como contexto permanente [5].

**Fracos.** Transcrição automática erra nomes, números, sobreposição de falas e pontuação. Um LLM pode criar timecodes inválidos, trocar a ordem narrativa, remover contexto ou inventar fatos. Crop geométrico central pode cortar uma pessoa ou texto. Uma saída que passa no ffprobe ainda pode ter jump cuts ruins, quadro negro, clipping, respiração cortada, artefatos ou legendas ilegíveis. Reencode repetido acumula perda; misturar fontes com FPS, áudio ou colorimetria divergentes cria joins perceptíveis. Render de Remotion pode ser demorado e depende de versões, dependências JS, Chromium e recursos disponíveis.

**Pontos críticos de melhoria.** Exigir teste em amostra curta antes de executar lote; restringir fontes e outputs a diretórios conhecidos; recusar caminhos fora do workspace; não sobrescrever saída; fixar versões e registrar hash, preset, modelo, prompt, timecodes e ambiente; testar segmentos nos limites; manter reprodução e revisão visual/auditiva; dimensionar legendas para safe areas; medir áudio e checar clipping; separar export final de qualquer publicação; capturar erro e oferecer rollback por novo arquivo, nunca sobre os originais.

## 4. Ferramentas e integrações por necessidade

| Necessidade | Recomendação | Observação operacional |
| --- | --- | --- |
| Orquestração e instruções | Claude Code + `CLAUDE.md` + project skill em `.claude/skills/` | Skills usam `SKILL.md`; a descrição orienta a invocação e o usuário também pode chamar `/video-pipeline` [5]. |
| Cortes, resize, crop/pad, áudio e encode | FFmpeg | Use argumentos separados em subprocesso, não concatene comandos de usuário em shell. Reencode quando aplicar filtros; stream copy só se compatibilidade e precisão dos cortes permitirem [2]. |
| Inspeção/QA técnica | FFprobe + script próprio | Consulte JSON de `-show_streams` e `-show_format`; teste decodificação integral com FFmpeg [3]. |
| Motion graphics, lower thirds, templates e variantes | Remotion + React + Node.js | Coding-agent guide oficial descreve o setup e instalação da Remotion Agent Skill [1]. Confira licença/termos de Remotion conforme o caso de uso; não presuma custo zero [6]. |
| Transcrição e timestamps | Whisper/WhisperX ou serviço de speech-to-text | Escolha nuvem se velocidade/diarização importam; local se privacidade/controle são prioritários. Corrija nomes e timecodes manualmente. Avalie a licença/modelo e a necessidade de GPU. |
| Intercâmbio com editores não lineares | XML/EDL/AAF conforme NLE | Não existe garantia de compatibilidade universal: valide versão, mídia offline, frame rate, efeitos e conform antes de depender do interchange. |
| Integração com apps via ferramentas | MCP apenas quando houver benefício concreto | MCP expõe ferramentas/contexto; cada servidor expande autoridade. Instale somente servidores revisados, dê acesso mínimo e não coloque credenciais na skill ou logs [7]. A edição local não exige MCP. |
| Legendas | SRT/VTT sidecar e, quando solicitado, burn-in | WebVTT suporta legendas temporizadas, capítulos e metadados alinhados à mídia [8]. Revise precisão, quebras de linha, safe area e contraste. |
| CI/lotes | Git + runner local/CI, com pasta temporária por job | Fixe imagens e versões, registre artefatos e limite CPU/GPU/concurrency. Não conceda ao runner permissão de publicação se só precisa renderizar. |

Não é necessário conectar Claude Code ao Premiere/DaVinci para fazer cortes simples: FFmpeg pode ser a camada de execução. Integração NLE/MCP só vale se o requisito incluir timeline editável, round-trip, media bin ou processo já dependente de um editor específico.

## 5. Proporções, contêineres e entregáveis

Não existe um único "melhor formato" para todos os usos. Separe proporção, contêiner, codec, frame rate e legenda.

- **16:9 paisagem**: vídeos longos, apresentações e YouTube padrão; um preset comum é MP4/H.264 com áudio AAC. A documentação do YouTube recomenda MP4, H.264 e AAC-LC/Opus/Eclipsa Audio para upload [9].
- **9:16 vertical**: Shorts, Reels e TikTok. Refaça o quadro e a posição do texto, não apenas aplique um crop cego. A saída 1080×1920 neste kit é um preset editorial próprio, não a afirmação de uma especificação universal de plataforma.
- **1:1 quadrado**: feeds que aceitam quadrado. Preserve foco e títulos dentro do quadro.
- **4:5**: útil para alguns feeds verticais. Acrescente perfil e teste na plataforma de destino; não está incluído no render base.
- **MP4/H.264 + AAC**: compatível como arquivo de revisão/publicação em muitos destinos; o conteúdo recebido pode ter outros codecs/contêineres e deve ser sondado antes de escolher stream copy ou conversão.
- **ProRes/MOV**: master/intermediário de alta qualidade quando o fluxo downstream exige; ocupa mais espaço e precisa de especificação compatível.
- **WAV**: áudio mestre sem perdas; adequado para etapa de som/arquivo, não substitui a trilha final dentro do vídeo.
- **SRT/VTT**: sidecars editáveis e acessíveis; **legenda queimada** fica permanente na imagem e exige outro export para corrigir texto/estilo.
- **Sequência PNG/EXR**: saída frame a frame quando transparência, composição ou pipeline de VFX exigirem; requer imagem/som sincronizados e espaço de armazenamento.

Para orientação oficial do YouTube, confira parâmetros atuais da própria página de upload antes de fechar um preset [9]. Legendas WebVTT são uma pista temporizada associada ao vídeo e comportam cue timings, posição e texto [8].

## 6. Protocolo de produção sugerido

1. **Brief estruturado:** objetivo, público, duração, idioma, plataforma, proporções, tom, call-to-action, material autorizado e critérios de sucesso. Pergunte se a lacuna muda materialmente o resultado.
2. **Inventário:** nomes, duração, dimensões, FPS, codec/container, streams de áudio e tamanho. Gerar `manifest.json`; não mover nem renomear originais.
3. **Compreensão:** se necessário, gerar transcrição timestamped; amostrar frames ao longo do vídeo e em cada transição suspeita. Marcar timecode de fonte (não somente timecode do corte) e confiança.
4. **Plano:** criar uma versão numerada do JSON/EDL. Cada trecho inclui fonte, in/out, motivo, texto falado, destino, observação de reenquadramento e riscos. Proibir intervalo negativo, invertido ou fora da duração.
5. **Preview:** primeiro render curto, com fonte de teste e watermark opcional, baixo custo, sem overwrite. Confirmar montagem e proporção antes de render longo.
6. **Revisão:** assistir em velocidade normal, ouvir começo/fim de cortes, revisar legenda e safe area nas três proporções. Comparar com briefing e confirmar licenças/identidade.
7. **Final:** render com parâmetros versionados. Guardar plano, logs, `ffprobe.json`, sidecars e hash SHA-256 junto do arquivo.
8. **Entrega:** usuário escolhe o arquivo e publica por processo separado. Upload ou postagem automática deve ser um passo explícito e isolado com confirmação específica.

## 7. QA em camadas

**Pré-render (bloqueante):** fonte existe e pode ser decodificada; há stream de vídeo; input e output não são o mesmo caminho; timecodes são válidos e ficam dentro da duração; perfis têm dimensão par e preset definido; armazenamento é suficiente; versão do FFmpeg é registrada.

**Pós-render (bloqueante):** código de saída zero; arquivo não vazio; ffprobe retorna vídeo com dimensão/FPS esperados; codecs e áudio correspondem ao preset; duração aproxima-se da soma dos trechos; FFmpeg consegue decodificar o arquivo completo até o fim; não houve erro de render por frame. Falha em um check impede marcar job como pronto.

**Revisão humana (obrigatória em material para público):** conferir primeiros/últimos frames, cada join, exposição/foco, continuidade, enquadramento, sincronismo, inteligibilidade, ruído, clipping, música e direitos. Legendas: texto, nomes próprios, número, pontuação, tempo, velocidade de leitura, linhas, contraste e margem segura. Para vídeos com ação relevante, assistir à ação completa; imagem estática bonita não prova movimento correto.

**Definição operacional de "sem falhas":** não é promessa de perfeição. É um processo que detecta classes conhecidas de erro, preserva as fontes, registra decisão e falha fechado quando um teste crítico não passa.

## 8. Modelo de segurança e permissões

- Usar cópia de trabalho ou leitura somente para originais; `exports/` é gravável e não contém fonte original.
- Manter confirmações padrão para shell, downloads e escritas até ter revisado o workspace. As regras de Claude Code são hierárquicas e o Bash mantém controle de permissões; não troque para bypass para acelerar a primeira execução [10].
- Negar tarefas não necessárias ao render (remoção recursiva, `sudo`, upload/publicação, alteração de configurações globais). Permita somente comandos conhecidos, revisando o padrão de permissão conforme a versão atual.
- Não inserir segredos em `CLAUDE.md`, EDL, linha de comando gravada, log ou arquivo de vídeo.
- Tratar mídia baixada, transcrições, legendas e prompts embutidos como conteúdo não confiável. Elas podem conter instruções maliciosas para o agente; nunca as execute como comandos.
- Usar timeouts, tamanho máximo de entrada, lista de formatos conhecidos e diretório temporário por job. Validar nomes, tratar symlinks e checar saída contra overwrite.
- MCP não é obrigatório. Se usado, revise o servidor e a lista de ferramentas, mantenha escopo mínimo e não misture autorização para leitura com autorização para publicação [7].

A documentação oficial de Claude Code define skills e permissões como mecanismos separados: uma skill dá instruções reutilizáveis; permissões e hooks controlam ferramentas/ações [5] [10] [11]. Não interprete a existência de uma skill como sandbox.

## 9. Plano de implementação em quatro etapas

**Etapa A — Prova de conceito local:** um arquivo autorizado de 30–60 s, dois cortes manuais, os três perfis; medir tempo, duração de render e bugs. Confirmar se o crop central funciona no conteúdo real.

**Etapa B — Assistência editorial:** adicionar transcrição e contact sheet. LLM pode sugerir cortes com fonte/timecode e justificar; pessoa aprova o edit plan.

**Etapa C — Automação controlada:** automatizar lote por diretórios, nomes idempotentes, retries de falha técnica, logs JSON e QA bloqueante. Não automatizar publicação.

**Etapa D — Escala/profissionalização:** adotar templates Remotion, assets licenciados, testes visuais por frames-chave, métricas de loudness conforme especificação do cliente, render workers e armazenamento versionado. Adicionar integração NLE somente se o fluxo real exigir.

Critérios de sucesso: taxa de render/QA; tempo humano de correção por minuto final; divergência de legenda por amostra; proporção de cortes aceitos sem retrabalho; qualidade percebida em revisão cega; custo por export; reprodutibilidade após novo run. Acompanhe antes e depois, sem assumir que mais automação reduz custo total.

## Referências

[1]: https://www.remotion.dev/docs/ai/coding-agents "Remotion: Prompting videos with coding agents"
[2]: https://ffmpeg.org/ffmpeg-filters.html "FFmpeg: Filter documentation"
[3]: https://ffmpeg.org/ffprobe.html "FFmpeg: ffprobe documentation"
[4]: https://www.remotion.dev/docs/cli/render "Remotion: render CLI"
[5]: https://code.claude.com/docs/en/skills "Claude Code: Skills"
[6]: https://www.remotion.dev/docs/license "Remotion: Licensing"
[7]: https://modelcontextprotocol.io/specification/2026-07-28 "Model Context Protocol specification"
[8]: https://www.w3.org/TR/webvtt1/ "W3C: WebVTT specification"
[9]: https://support.google.com/youtube/answer/1722171?hl=pt-BR "YouTube: recommended upload encoding settings"
[10]: https://code.claude.com/docs/en/permissions "Claude Code: Permissions"
[11]: https://code.claude.com/docs/en/hooks "Claude Code: Hooks reference"
