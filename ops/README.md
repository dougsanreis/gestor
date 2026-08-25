# GOVIO Ops

Ferramental de entrega do GOVIO. É a `DOCTRINE.md` transformada em código
executável: cada garantia da doutrina existe aqui como mecanismo, não como
recomendação.

## Instalação (uma vez, na máquina do operador)

```bash
git clone -b claude/terminal-session-resume-byojf5 https://github.com/dougsanreis/gestor.git ~/.govio-src && ln -sfn ~/.govio-src/ops ~/.govio && bash ~/.govio/bin/govio where
```

Atualizar depois:

```bash
git -C ~/.govio-src pull --ff-only && bash ~/.govio/bin/govio where
```

Se o `git clone` falhar por autenticação, use o payload base64 em
`ops/INSTALL-offline.txt` — ele não depende de rede nem de credenciais.

Atalho opcional:

```bash
echo 'alias govio="bash ~/.govio/bin/govio"' >> ~/.bashrc && . ~/.bashrc
```

## Garantias

| Garantia | Mecanismo |
|---|---|
| Não fecha o seu terminal | gates rodam em processo filho; dispatcher sempre `exit 0`; sem `set -e` no shell pai |
| Não destrói trabalho | zero ocorrências de `git reset/clean/restore/checkout`; rollback só cirúrgico, sobre pré-imagem própria |
| Não trava indefinidamente | `timeout` em toda chamada externa |
| Não inunda o terminal | circuit breaker por bytes; causa raiz extraída em vez de despejo bruto |
| Não corrompe arquivo | `mkstemp` → `fsync` → `os.replace` → `fsync` do diretório |
| Não aplica patch em alvo errado | CAS SHA-256 por arquivo, validado antes de qualquer escrita |
| Não aplica patch parcial | valida os N antes de escrever 1; falha no meio restaura só o que escreveu |
| Não silencia o compilador | recusa patch que introduza `any`, `@ts-ignore`, `@ts-expect-error` |

## Comandos

```bash
govio checkpoint             # preserva trabalho não commitado (commit + tarball)
govio doctor                 # diagnóstico completo read-only, em lote
govio apply patches.json     # aplica N patches em uma transação
govio build [web|team|all]   # build isolado + classificação de causa raiz
govio ship preview [app]     # preview + prova de proveniência da resposta
govio ship production [app]  # promoção para govio.com.br (confirmação digitada)
govio where                  # worktree, HEAD, branch, pendências
govio doctrine               # doutrina completa
```

## Fluxo

```
checkpoint → doctor → apply → doctor → build → ship preview → UAT → ship production
```

Cada volta resolve **todos** os problemas conhecidos, nunca um por rodada.

## Variáveis

| Variável | Efeito |
|---|---|
| `GOVIO_WT_OVERRIDE` | força o worktree alvo |
| `GOVIO_EVIDENCE_ROOT` | onde gravar evidências (padrão `~/.govio/evidence`) |
| `GOVIO_SCOPE` | escopo Vercel (padrão `govio-br`) |
| `GOVIO_MAX_OUTPUT_BYTES` | circuit breaker de saída |

## Formato do manifest de patches

```json
{
  "patches": [
    {
      "path": "apps/web/lib/landing/publish-chain.ts",
      "expectSha256": "<sha256 do arquivo ATUAL>",
      "find": "    validator: LandingPublishValidator,",
      "replace": "    validator: NextValidator,",
      "occurrences": 1
    },
    {
      "path": "packages/db/src/env.ts",
      "expectSha256": "<sha256 do arquivo ATUAL>",
      "contentB64": "<arquivo inteiro em base64>"
    }
  ]
}
```
