# SYRA

Fábrica de software governada. Recebe uma missão, gera código Python real,
roda a suíte de testes de verdade e **só entrega quando há evidência**.

A diferença entre gerar artefato e gerar software está nos portões. Aqui eles
são executáveis, não conselhos:

| Portão | O que verifica | Se falhar |
|---|---|---|
| `lei_do_ganho` | a missão declara ao menos um ganho | bloqueia antes de gastar ciclo |
| `sintaxe` | todo arquivo gerado compila (`ast.parse`) | dispara reparo |
| `revisão` | placeholder, chamada insegura, `except:` pelado, default mutável, marcador pendente | bloqueia |
| `testes` | pytest roda de verdade, em subprocesso isolado | dispara reparo |
| `cobertura` | toda função pública é invocada por algum teste | bloqueia |
| `governança` | consolida tudo e calcula confiança | APPROVED / NEEDS_REVIEW / BLOCKED |
| `entrega` | manifesto + zip determinístico com sha256 | — |

## Instalação

```bash
git clone https://github.com/dougsanreis/gestor.git
cd gestor
python -m pip install -e ".[test]"
syra doctor
```

Sem instalar: `python -m syra.cli doctor`.

## Uso

```bash
# constrói, testa e entrega
syra build "biblioteca de validação de cadastro com CPF e email" --gain capability
syra build "API de gestão escolar com alunos, notas e frequência" --kind service --gain product

# avalia um comando antes de executar
syra guard rm -rf /            # BLOCK, com alternativa segura
syra guard pytest -q           # ALLOW

# painel, auto-otimização e diagnóstico
syra report
syra learn
syra doctor
```

Códigos de saída: `0` aprovado · `1` erro de uso · `2` bloqueado · `3` ressalva.
São contrato: dá para usar em CI e em hook de shell sem interpretar texto.

### Squad de funil

```bash
syra funnel list --nivel avancado
syra funnel page --funil fim_do_loop_de_erro --out paginas/
syra funnel serve --funil fim_do_loop_de_erro --segmento intermediario
syra funnel track --funil fim_do_loop_de_erro --segmento intermediario \
                  --angulo dor --exposicoes 1 --conversoes 1
syra funnel optimize
```

Documentação completa em [`docs/FUNIL_VIBE_CODE.md`](docs/FUNIL_VIBE_CODE.md).

## Arquitetura

```
missão
  ↓ Architect          seleciona capacidades por aderência ao objetivo
  ↓ Synthesizer        materializa arquivos (blueprint ou agente externo)
  ↓ Reviewer           regras estáticas sobre AST
  ↓ QAEngine           pytest real, com duração por teste
  ↓ RepairEngine       corrige a causa; nunca enfraquece o teste
  ↓ GovernanceEngine   decide com todas as evidências em mãos
  ↓ Packager           manifesto + artefato .zip com sha256
```

Estado persistente em `$SYRA_HOME` (padrão `./.syra`): memória de erros,
histórico de execuções, tempos por teste, política e trilha de auditoria.

### O sintetizador é intercambiável

`BlueprintSynthesizer` é o piso determinístico: funciona sem rede e sem modelo,
a partir de um catálogo de 15 capacidades reais com testes próprios.
`SubprocessSynthesizer` delega a um agente externo (`claude -p`, por exemplo) e
passa pelos **mesmos** portões.

A fábrica confia na evidência, nunca na origem do código.

## As três travas contra autossabotagem

1. **O reparo nunca enfraquece o teste.** Nenhuma estratégia apaga, pula ou
   afrouxa teste para obter verde. Quando a causa não é corrigível, a
   capacidade defeituosa vai para quarentena e sai da entrega, com registro.

2. **O núcleo de segurança é imutável para a auto-otimização.** Sete campos de
   política (taxa de aprovação de testes, achados bloqueantes, cobertura,
   limiares de quarentena) estão em `CAMPOS_CONGELADOS`. Um agente pode propor
   alterá-los; a proposta é descartada antes de chegar à validação.

3. **Erro repetido é falha sistêmica.** A memória de erros colapsa falhas em
   assinaturas estáveis. Três ocorrências sem correção conhecida bloqueiam a
   entrega em vez de tentar de novo.

## Testes

```bash
python -m pytest        # 185 testes, ~3 s
```

Rápido por decisão de projeto: suíte que demora deixa de ser executada, e
suíte que não roda não protege nada.
