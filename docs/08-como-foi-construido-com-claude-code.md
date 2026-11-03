# 8. Como este sistema foi construído com o Claude Code

Este projeto partiu de um repositório **vazio** e foi construído em uma única sessão do Claude Code a partir de um pedido em linguagem natural:

> "Vamos criar um sistema funcional de teste para mostrar aos alunos como funciona um sistema completo criado no Claude Code, com interface local. Traga toda a documentação técnica de implementação e em seguida aplique a execução do sistema."

## 8.1 Etapas que o agente executou
1. **Inspeção do ambiente** — verificou o repositório (vazio) e as versões de Node.js/Python disponíveis; confirmou que o `node:sqlite` nativo funcionava.
2. **Decisão de arquitetura** — escolheu Node.js sem dependências para que a turma rode com um único comando.
3. **Backend em camadas** — banco (`db.js`) → utilitários HTTP → autenticação → validação → regras de KPIs → rotas → servidor.
4. **Dados de demonstração** determinísticos e relativos à data atual.
5. **Frontend SPA** com gráficos em SVG e CSP restritiva.
6. **Testes** unitários e de integração; corrigiu o script de teste quando o primeiro run falhou.
7. **Execução real** — subiu o servidor, dirigiu a interface com um navegador automatizado, capturou telas e erros de console.
8. **Revisão visual** — analisou as capturas, encontrou valores cortados nos cards de KPI e corrigiu o CSS.
9. **Documentação** (esta pasta) e commit no Git.

## 8.2 Lições para os alunos
- **Seja específico no pedido**: público, objetivo, restrições ("interface local") orientam todas as decisões.
- **Peça verificação**: o agente não só escreve código, mas executa, testa e olha o resultado.
- **Itere**: depois da primeira versão, peça melhorias pontuais ("adicione filtro por data", "exporte PDF").
- **Revise o diff**: tudo está versionado no Git; leia o que foi gerado.

## 8.3 Ideias de exercícios / próximos passos
| Nível | Exercício |
|---|---|
| Fácil | Adicionar a plataforma "Pinterest" (CHECK do banco, `PLATFORMS`, rótulo e cor no front) |
| Fácil | Novo KPI: "ticket médio" = receita ÷ conversões |
| Médio | Alerta visual quando o investimento do dia passar do orçamento diário |
| Médio | Importar métricas a partir de um arquivo CSV |
| Médio | Comparar período atual com período anterior (variação %) |
| Avançado | Limite de tentativas de login e cookie `HttpOnly` |
| Avançado | Multi-tenant: cada gestor vê apenas seus clientes |
| Avançado | Integração real com a API de Marketing do Meta |

Sugestão de prompt para praticar no Claude Code:
```
Adicione a plataforma Pinterest ao Gestor de Anúncios em todas as camadas
(banco, validação, interface e seed), atualize a documentação e rode os testes.
```
