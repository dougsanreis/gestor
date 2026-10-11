# Kit técnico: edição automatizada de vídeo com Claude Code

Este pacote transforma Claude Code em **orquestrador** de um pipeline reproduzível. O agente analisa briefing e arquivos, propõe um plano de cortes estruturado, chama ferramentas determinísticas e verifica o resultado. FFmpeg executa os cortes e exports; Remotion é opcional quando a peça depende de motion graphics, templates ou cenas construídas em React. A decisão final sobre ritmo, contexto, enquadramento e som continua sendo humana.

## O que está incluído

- `PESQUISA-E-RECOMENDACOES.md`: resultados de pesquisa e comparação de vídeos do YouTube, com ressalvas explícitas sobre comentários.
- `ARQUITETURA-E-PLAYBOOK.md`: desenho prático, pontos fortes/fracos, ferramentas, formatos, segurança, testes e plano de implantação.
- `starter-project/`: projeto inicial para copiar para uma pasta de trabalho. Inclui instruções Claude Code, uma skill, plano de edição de exemplo e scripts Python que usam `ffprobe`/`ffmpeg`.

## Começo rápido

1. Instale Claude Code e Node.js se for usar Remotion. Instale FFmpeg/FFprobe e valide com `ffmpeg -version` e `ffprobe -version`. No projeto Remotion, siga a versão atual das instruções oficiais, inclusive `npx remotion skills add`.
2. Copie `starter-project/` para uma pasta nova. Não use a pasta dos originais como destino dos exports.
3. Coloque uma cópia de um vídeo de teste em `media/source.mp4`; preserve os arquivos originais fora da pasta gerada.
4. Ajuste `edit-plan.example.json` e salve-o como `edit-plan.json`. O exemplo mantém dois trechos e gera 16:9, 9:16 e 1:1; confira os timecodes antes de executar.
5. Execute `python3 scripts/media_preflight.py media/source.mp4`.
6. Execute `python3 scripts/render_edl.py edit-plan.json` para gerar três exports em `exports/`. O script recusa sobrescrever saídas existentes.
7. Inspecione duração, dimensão, áudio e decodificação. Veja o checklist em `ARQUITETURA-E-PLAYBOOK.md` e revise visualmente cada export antes de publicar.
8. Abra Claude Code dentro da pasta e use `/video-pipeline` para pedir a análise, a proposta do plano e a execução controlada. No primeiro uso, solicite apenas um preview curto.

> O kit é uma base demonstrativa para projeto local, não uma alegação de edição sem falhas. Teste com arquivos não críticos, confira permissões e valide a saída no seu ambiente e nos destinos de publicação.

## Perfil da base incluída

A implementação renderiza uma fonte de vídeo e uma lista ordenada de intervalos da **mesma fonte**, em H.264/MP4, com AAC quando existe áudio. Ela gera três proporções por padrão: 1920×1080 (paisagem), 1080×1920 (vertical) e 1080×1080 (quadrado). A opção `cover` centraliza e corta para preencher o quadro; `contain` preserva o quadro inteiro e completa as bordas com preto. Não há reenquadramento inteligente por rosto/objeto, nem análise automática de semântica.

A base não tenta publicar, apagar, substituir originais, gerar narração, criar música ou automatizar um projeto nativo de Premiere/DaVinci. Para motion graphics, títulos parametrizados e produção em lote, considere Remotion; para intercâmbio com um NLE, crie uma etapa própria e teste a compatibilidade do formato escolhido.

## Fontes primárias e atualização

As referências e suas aplicações estão no playbook e na pesquisa. A documentação de Claude Code, Remotion e formatos muda; confira as páginas oficiais antes de aplicar em produção. Os tutoriais do YouTube são material complementar, não especificação técnica nem garantia de resultado.
