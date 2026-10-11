# Registro de pesquisa — Claude Code e edição automatizada de vídeo

Data da pesquisa: 2026-10-11. Escopo pedido: avaliar tutoriais de YouTube e comentários públicos com sinais de aplicação real; validar também arquitetura, integrações, formatos e QA em documentação primária.

## Vídeos candidatos

- [How I Fully Automated My Video Editing (Claude Code)](https://www.youtube.com/watch?v=G0EH0xdy2-E) — resumo de busca: Claude Code + Remotion, automação ponta a ponta.
- [Claude Code Tutorial: Edit Videos with Remotion (Full Workflow)](https://www.youtube.com/watch?v=9uijvrx8yYI) — resumo de busca: fluxo completo com Remotion.
- [How To Fully Automate Video Editing with Claude Code (Setup + Guide)](https://www.youtube.com/watch?v=dX_UtTmZR9E) — capítulos indicados: setup, rough cut, refinamento.
- [I Fully Automated My Video Editing Using Claude Code (Full Workflow)](https://www.youtube.com/watch?v=X1M61eZtYL8) — busca apresenta como fluxo atual para short e long form.
- [I Fully Automated My Video Editing Using Claude Code (Full Walkthrough)](https://www.youtube.com/watch?v=HzXD4GVqXwM) — resultado/custo declarado no título/descrição de busca: cerca de US$ 27 por 5 minutos; tratar como afirmação do autor até validação independente.

As páginas, transcrições e comentários ainda estão em validação; descoberta por busca não é prova de uso profissional nem de comentários positivos.

## Fontes técnicas oficiais descobertas

- Claude Code — Skills: https://code.claude.com/docs/en/skills
- Claude Code — Hooks: https://code.claude.com/docs/en/hooks
- Claude Code — Permissions: https://code.claude.com/docs/en/permissions
- Claude Code — Subagents: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- Remotion — coding agents: https://www.remotion.dev/docs/ai/coding-agents
- Remotion — CLI render: https://www.remotion.dev/docs/cli/render
- Remotion — renderMedia API: https://www.remotion.dev/docs/renderer/render-media
- FFmpeg — main documentation: https://ffmpeg.org/ffmpeg.html
- FFmpeg — filters: https://ffmpeg.org/ffmpeg-filters.html
- FFprobe — documentation: https://ffmpeg.org/ffprobe.html
- Model Context Protocol — specification: https://modelcontextprotocol.io/specification/2026-07-28
- YouTube — recommended upload encoding settings: https://support.google.com/youtube/answer/1722171?hl=en
- W3C WebVTT: https://www.w3.org/TR/webvtt1/

## Hipóteses técnicas para verificar

1. Arquitetura robusta deve separar plano editorial (JSON com timecodes), render determinístico (FFmpeg/Remotion), inspeção de mídia (ffprobe), e checagem visual/auditiva por humano.
2. “Automatizado” não significa “sem aprovação”: fonte original nunca deve ser sobrescrita; scripts devem restringir caminhos, comandos destrutivos e publicação.
3. Comentários positivos podem ser indisponíveis, incompletos ou não verificáveis; se não houver prova pública acessível, registrar explicitamente em vez de inventar validação social.
4. Perfis de entrega para horizontal, vertical e quadrado devem derivar do mesmo projeto com safe areas/legendas reflowed, e não apenas redimensionar o mesmo render.

## Primeira avaliação concluída — G0EH0xdy2-E

A página direta e análise audiovisual verificaram um fluxo híbrido: Descript para rough cut por texto, template e encurtamento de pausas; FFmpeg para extrair áudio; Whisper API para timestamps de palavras; Claude Code + Remotion/React/TypeScript para inserir gráficos, preview e render final. O autor ainda revê precisão e itera estilo/fonte. As alegações de economia de 3–6 horas são do criador, não mensuração independente. A transcrição ficou bloqueada pelo anti-bot do YouTube; o fluxo foi confirmado por capítulos e análise audiovisual, não por transcript literal. Fonte: https://www.youtube.com/watch?v=G0EH0xdy2-E

Comentários acessíveis incluíam reações como “pretty incredible” e opiniões condicionais de um editor; nenhum comprovou um resultado próprio com detalhes. Um comentarista disse ter usado “yesterday”, mas não descreveu aplicação nem resultado. Portanto, para este vídeo, evidência independente positiva de resultado real: não verificada. Comentários, páginas e descrição direta: https://www.youtube.com/watch?v=G0EH0xdy2-E&lc=UgwDW7H4guHw-5W5P994AaABAg ; https://www.youtube.com/watch?v=G0EH0xdy2-E&lc=UgyCbEYSVF4B3V6-6RF4AaABAg ; https://www.youtube.com/watch?v=G0EH0xdy2-E&lc=UgyLrpH2q1Iz20V0cB14AaABAg

## Síntese da avaliação dos cinco vídeos

Classificação final por valor prático + verificabilidade (não popularidade):

1. `dX_UtTmZR9E` — setup e guide: workflow acessível de rough cut, aprovação humana, gráficos, captions, música e export; transcript automático consultável. Demonstra um talking head e reconhece necessidade de segunda passagem.
2. `G0EH0xdy2-E` — fluxo Descript + Whisper API + Claude Code + Remotion para cortes e gráficos; demonstração útil, mas a transcrição integral não ficou disponível e a economia de horas é claim do criador.
3. `9uijvrx8yYI` — fluxo social com Whisper local, Remotion, preview e Blotato/MCP; claims de crescimento/eficiência não são independentes e a conexão para agendamento depende de serviço.
4. `X1M61eZtYL8` — arquitetura ampla de skills/assets/frame analysis/review gates; complexa e dependente de iteração; tempo e volume são autorrelatos.
5. `HzXD4GVqXwM` — página e capítulos revelam foco em papéis, skill, setup e treinamento, mas reprodução/transcript ficaram indisponíveis. É o único com alguns relatos de uso concreto nos comentários, ainda auto-relatados e sem artefatos/métricas auditáveis.

Comentários: nos quatro primeiros não foi verificado caso positivo completo de uso + resultado. Em `HzXD4GVqXwM`, usuários relatam primeiro teste de hook, tentativa em dois estilos, adaptação por agência e treino com B-roll; outro relato aponta limite de créditos. São sinais de adoção, não prova independente. Os permalinks e detalhamento estão em `PESQUISA-E-RECOMENDACOES.md`.

Conclusão cruzada: técnica mais reproduzível é transcrição com timestamps → rough cut sugerido em plano estruturado → aprovação humana → overlays/captions em componentes reutilizáveis → preview → correção → render → revisão completa. Não há, nos vídeos analisados, benchmark independente de qualidade, custo, tempo, precisão ou substituição de editores profissionais. Fontes diretas e capítulos listados no relatório comparativo.
