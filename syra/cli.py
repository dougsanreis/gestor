"""Interface de linha de comando da SYRA.

Toda operacao do sistema tem um comando com codigo de saida definido, para
poder entrar em script, hook de shell e CI sem interpretacao ambigua:

    0  operacao concluida / aprovado / comando liberado
    1  erro de uso
    2  bloqueado pela governanca ou pela quarentena
    3  aprovado com ressalva (revisao humana recomendada)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from syra import __version__
from syra.contracts import Gain, Mission, RiskLevel, Verdict
from syra.factory.pipeline import Factory
from syra.factory.synthesis import BlueprintSynthesizer, SubprocessSynthesizer
from syra.governance.policy import Policy
from syra.governance.quarantine import CommandQuarantine
from syra.intelligence.optimizer import Optimizer
from syra.intelligence.test_selector import TestIntelligence
from syra.memory.error_memory import ErrorMemory
from syra.memory.run_store import RunStore
from syra.funnel.blueprint import FUNIS, por_id as funil_por_id
from syra.funnel.copy import Angulo, gerar_copy_captura, gerar_copy_vendas
from syra.funnel.pages import render_pagina_captura, render_pagina_vendas
from syra.funnel.personas import PERSONAS, dores_por_nivel, por_id as persona_por_id
from syra.funnel.squad import FunnelSquad
from syra.paths import syra_home

CODIGO_OK = 0
CODIGO_USO = 1
CODIGO_BLOQUEADO = 2
CODIGO_RESSALVA = 3

_SIMBOLO = {True: "OK   ", False: "FALHA"}


def _emitir(dados: dict, como_json: bool, texto: list[str]) -> None:
    """Imprime em JSON ou em texto legivel, conforme a flag."""
    if como_json:
        print(json.dumps(dados, indent=2, ensure_ascii=False, default=str))
    else:
        print("\n".join(texto))


def cmd_build(args: argparse.Namespace) -> int:
    """Executa uma missao de ponta a ponta e reporta o veredito."""
    try:
        ganhos = tuple(Gain(g) for g in args.gain)
    except ValueError as erro:
        print(f"ganho invalido: {erro}", file=sys.stderr)
        return CODIGO_USO

    synthesizer = (SubprocessSynthesizer(args.synthesizer_cmd)
                   if args.synthesizer_cmd else BlueprintSynthesizer())
    fabrica = Factory(policy=Policy.load(), synthesizer=synthesizer)
    resultado = fabrica.build(Mission(objective=args.objetivo, kind=args.kind,
                                      gains=ganhos))

    if resultado.qa is not None:
        TestIntelligence().record(resultado.qa)

    linhas = [f"missao   : {resultado.mission.mission_id}",
              f"objetivo : {resultado.mission.objective}", ""]
    for portao in resultado.gates:
        linhas.append(f"  {_SIMBOLO[portao.passed]} {portao.name:14} "
                      f"{portao.detail[:64]}")
    linhas += ["",
               f"veredito : {resultado.decision.verdict.value} "
               f"(confianca {resultado.decision.confidence:.2f})"]
    linhas += [f"  - {motivo}" for motivo in resultado.decision.reasons]
    if resultado.decision.recommendations:
        linhas.append("recomendacoes:")
        linhas += [f"  - {r}" for r in resultado.decision.recommendations]
    if resultado.build_dir:
        linhas.append(f"codigo   : {resultado.build_dir}")
    if resultado.artifact_path:
        linhas.append(f"artefato : {resultado.artifact_path}")
        linhas.append(f"sha256   : {resultado.manifest.artifact_sha256}")
    linhas.append(f"duracao  : {resultado.duration:.2f}s")

    _emitir(resultado.to_dict(), args.json, linhas)

    if resultado.decision.verdict is Verdict.APPROVED:
        return CODIGO_OK
    if resultado.decision.verdict is Verdict.NEEDS_REVIEW:
        return CODIGO_RESSALVA
    return CODIGO_BLOQUEADO


def cmd_guard(args: argparse.Namespace) -> int:
    """Avalia o risco de um comando antes de qualquer execucao."""
    bruto = " ".join(args.comando).strip()
    if not bruto:
        print("informe o comando a avaliar", file=sys.stderr)
        return CODIGO_USO
    avaliacao = CommandQuarantine(Policy.load()).assess(bruto)
    linhas = [f"comando  : {avaliacao.command}",
              f"nivel    : {avaliacao.level.value} (score {avaliacao.score}/100)",
              f"motivo   : {avaliacao.reason}"]
    if avaliacao.matched_rules:
        linhas.append(f"regras   : {', '.join(avaliacao.matched_rules)}")
    if avaliacao.safe_alternative:
        linhas.append(f"seguro   : {avaliacao.safe_alternative}")
    _emitir(avaliacao.to_dict(), args.json, linhas)

    if avaliacao.level is RiskLevel.BLOCK:
        return CODIGO_BLOQUEADO
    if avaliacao.level is RiskLevel.REVIEW:
        return CODIGO_RESSALVA
    return CODIGO_OK


def cmd_learn(args: argparse.Namespace) -> int:
    """Roda um ciclo de auto-otimizacao governada."""
    relatorio = Optimizer(Policy.load()).cycle(apply=not args.dry_run)
    linhas = [f"execucoes analisadas : {relatorio['runs_analisadas']}",
              f"propostas            : {relatorio['propostas']}",
              f"promovidas           : {relatorio['promovidas']}",
              f"aplicado             : {relatorio['aplicado']}", ""]
    for validacao in relatorio["validacoes"]:
        rec = validacao["recommendation"]
        marca = "PROMOVIDA" if validacao["promoted"] else "REJEITADA"
        linhas.append(f"  [{marca}] {rec['agent']}: {rec['target']} -> "
                      f"{rec['change']['value']} (delta {validacao['delta']:+.4f})")
        linhas.append(f"      {validacao['reason']}")
    if not relatorio["validacoes"]:
        linhas.append("  nenhuma proposta: sinais insuficientes ou sistema ja ajustado")
    _emitir(relatorio, args.json, linhas)
    return CODIGO_OK


def cmd_report(args: argparse.Namespace) -> int:
    """Mostra o painel consolidado do sistema."""
    politica = Policy.load()
    store = RunStore()
    memoria = ErrorMemory()
    timing = TestIntelligence()

    stats = store.stats()
    resumo = timing.summary(politica.slow_test_threshold,
                            politica.speed_regression_factor)
    sistemicos = memoria.systemic_failures(politica.recurrence_threshold)

    dados = {"home": str(syra_home()), "policy": politica.to_dict(),
             "runs": stats, "tests": resumo,
             "errors": {"conhecidos": len(memoria),
                        "sistemicos": [e.to_dict() for e in sistemicos]}}

    linhas = [f"SYRA {__version__} — {syra_home()}", "",
              f"execucoes            : {stats['runs']}",
              f"taxa de entrega      : {stats['delivery_rate']:.0%}",
              f"taxa de suite verde  : {stats['green_rate']:.0%}",
              f"duracao mediana      : {stats['median_duration']:.2f}s",
              f"reparos por execucao : {stats['avg_repairs']:.2f}", ""]
    if stats["top_gate_failures"]:
        linhas.append("portoes que mais bloquearam:")
        linhas += [f"  {nome:14} {qtd}x"
                   for nome, qtd in list(stats["top_gate_failures"].items())[:5]]
        linhas.append("")
    linhas += [f"testes rastreados    : {resumo['tests_tracked']}",
               f"suite completa (est.): {resumo['estimated_full_run']:.2f}s"]
    if resumo["slowest"]:
        linhas.append("testes mais lentos:")
        linhas += [f"  {t['median']:6.2f}s ({t['share']:.0%} da suite)  {t['nodeid']}"
                   for t in resumo["slowest"][:5]]
    if resumo["regressions"]:
        linhas.append("regressoes de velocidade:")
        linhas += [f"  {r['factor']}x mais lento  {r['nodeid']}"
                   for r in resumo["regressions"][:5]]
    linhas.append("")
    linhas.append(f"erros conhecidos     : {len(memoria)}")
    if sistemicos:
        linhas.append("falhas sistemicas (recorrentes e sem correcao):")
        linhas += [f"  {e.occurrences}x  {e.kind:16} {e.message[:52]}"
                   for e in sistemicos[:5]]
    _emitir(dados, args.json, linhas)
    return CODIGO_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    """Verifica se o ambiente atende ao que a fabrica precisa."""
    import shutil

    checagens = []

    versao_ok = sys.version_info >= (3, 9)
    checagens.append(("python >= 3.9", versao_ok,
                      ".".join(map(str, sys.version_info[:3]))))

    try:
        import pytest  # noqa: F401
        pytest_ok, detalhe = True, "importavel"
    except ImportError:
        pytest_ok = bool(shutil.which("pytest"))
        detalhe = "no PATH" if pytest_ok else "ausente: sera usado unittest"
    checagens.append(("pytest", pytest_ok, detalhe))

    home = syra_home()
    try:
        sonda = home / ".escrita"
        sonda.write_text("ok", encoding="utf-8")
        sonda.unlink()
        escrita_ok, detalhe_home = True, str(home)
    except OSError as erro:
        escrita_ok, detalhe_home = False, str(erro)
    checagens.append(("estado gravavel", escrita_ok, detalhe_home))

    politica = Policy.load()
    checagens.append(("politica carregada", True,
                      f"{len(politica.to_dict())} parametros"))
    checagens.append(("nucleo de seguranca", politica.min_test_pass_rate >= 1.0
                      and politica.max_blocking_findings == 0,
                      f"pass_rate={politica.min_test_pass_rate} "
                      f"blocking={politica.max_blocking_findings}"))

    dados = {"checks": [{"nome": n, "ok": o, "detalhe": d} for n, o, d in checagens]}
    linhas = [f"  {_SIMBOLO[ok]} {nome:22} {detalhe}" for nome, ok, detalhe in checagens]
    _emitir(dados, args.json, linhas)
    return CODIGO_OK if all(ok for _, ok, _ in checagens) else CODIGO_BLOQUEADO


def cmd_funnel_list(args: argparse.Namespace) -> int:
    """Lista dores mapeadas, funis e etapas do nicho."""
    dores = dores_por_nivel(args.nivel)
    dados = {
        "dores": [d.to_dict() for d in dores],
        "funis": [f.to_dict() for f in FUNIS],
        "personas": [p.id for p in PERSONAS],
    }
    linhas = ["DORES MAPEADAS (prioridade = intensidade x frequencia)"]
    for dor in dores[:10]:
        nivel = next((p.nivel for p in PERSONAS if dor in p.dores), "?")
        linhas.append(f"  {dor.prioridade:3}  {nivel:14} {dor.titulo}")
    linhas.append("")
    linhas.append("FUNIS")
    for funil in FUNIS:
        linhas.append(f"  {funil.id}")
        linhas.append(f"    persona : {funil.persona_id}")
        linhas.append(f"    promessa: {funil.promessa[:66]}")
        for etapa in funil.etapas:
            linhas.append(f"    {etapa.estagio:5} meta {etapa.meta:5.0%}  "
                          f"{etapa.metrica[:38]:40} -> {etapa.cta}")
    _emitir(dados, args.json, linhas)
    return CODIGO_OK


def cmd_funnel_page(args: argparse.Namespace) -> int:
    """Gera as paginas de venda e de captura de um funil."""
    funil = funil_por_id(args.funil)
    if funil is None:
        print(f"funil desconhecido: {args.funil}", file=sys.stderr)
        print(f"disponiveis: {', '.join(f.id for f in FUNIS)}", file=sys.stderr)
        return CODIGO_USO

    persona = persona_por_id(funil.persona_id)
    destino = Path(args.out)
    destino.mkdir(parents=True, exist_ok=True)

    angulos = [Angulo(args.angulo)] if args.angulo else list(Angulo)
    gerados = []
    for angulo in angulos:
        copy = gerar_copy_vendas(funil, persona, angulo)
        pagina = render_pagina_vendas(copy, segmento=persona.id)
        (destino / pagina.caminho).write_text(pagina.html, encoding="utf-8")
        gerados.append({"arquivo": str(destino / pagina.caminho),
                        "tipo": "vendas", "angulo": angulo.value,
                        "provas_pendentes": list(copy.provas_pendentes)})

    captura = render_pagina_captura(gerar_copy_captura(funil, persona),
                                    segmento=persona.id)
    (destino / captura.caminho).write_text(captura.html, encoding="utf-8")
    gerados.append({"arquivo": str(destino / captura.caminho), "tipo": "captura"})

    pendentes = [g for g in gerados if g.get("provas_pendentes")]
    linhas = [f"funil    : {funil.nome}", f"persona  : {persona.nome}", ""]
    linhas += [f"  {g['tipo']:8} {g.get('angulo', '-'):10} {g['arquivo']}"
               for g in gerados]
    if pendentes:
        linhas += ["", "ATENCAO: prova pendente. As paginas declaram que nenhum",
                   "depoimento ou numero de resultado foi verificado. Forneca",
                   "provas reais antes de publicar."]
    _emitir({"funil": funil.id, "paginas": gerados}, args.json, linhas)
    return CODIGO_RESSALVA if pendentes else CODIGO_OK


def cmd_funnel_serve(args: argparse.Namespace) -> int:
    """Informa qual angulo servir agora para um segmento."""
    squad = FunnelSquad()
    angulo = squad.servir(args.funil, args.segmento)
    dados = {"funil": args.funil, "segmento": args.segmento, "angulo": angulo,
             "padrao_promovido": squad.padroes.get(args.funil, args.segmento)}
    _emitir(dados, args.json,
            [f"servir angulo '{angulo}' para '{args.segmento}' em {args.funil}",
             f"padrao promovido: {dados['padrao_promovido']}"])
    return CODIGO_OK


def cmd_funnel_track(args: argparse.Namespace) -> int:
    """Registra exposicoes e conversoes de uma variante ou etapa."""
    squad = FunnelSquad()
    try:
        if args.estagio:
            contagem = squad.stages.registrar(args.funil, args.estagio,
                                              args.exposicoes, args.conversoes)
            dados = {"funil": args.funil, "estagio": args.estagio.upper(),
                     **contagem.to_dict()}
        else:
            if not args.angulo:
                print("informe --angulo ou --estagio", file=sys.stderr)
                return CODIGO_USO
            placar = squad.variants.registrar(args.funil, args.segmento, args.angulo,
                                              args.exposicoes, args.conversoes)
            dados = {"funil": args.funil, "segmento": args.segmento,
                     "angulo": args.angulo, **placar.to_dict()}
    except ValueError as erro:
        print(str(erro), file=sys.stderr)
        return CODIGO_USO

    _emitir(dados, args.json,
            [f"{k:16}: {v}" for k, v in dados.items()])
    return CODIGO_OK


def cmd_funnel_optimize(args: argparse.Namespace) -> int:
    """Roda um ciclo do squad de funil."""
    relatorio = FunnelSquad().cycle(apply=not args.dry_run)
    linhas = [f"funis avaliados : {relatorio['funis_avaliados']}",
              f"recomendacoes   : {len(relatorio['recomendacoes'])}",
              f"promovidas      : {len(relatorio['promovidas'])}",
              f"bloqueios       : {len(relatorio['bloqueios_de_publicacao'])}", ""]
    for promocao in relatorio["promovidas"]:
        linhas.append(f"  PROMOVIDA  {promocao['funil']}:{promocao['segmento']} "
                      f"-> angulo '{promocao['angulo']}'")
    for rec in relatorio["recomendacoes"]:
        if rec["change"].get("tipo") == "angulo_padrao":
            continue
        linhas.append(f"  [{rec['agent']:12}] {rec['target']}")
        linhas.append(f"      {rec['expected_gain']}")
        for evidencia in rec["evidence"][:2]:
            linhas.append(f"      - {evidencia[:78]}")
    _emitir(relatorio, args.json, linhas)
    return CODIGO_BLOQUEADO if relatorio["bloqueios_de_publicacao"] else CODIGO_OK


def build_parser() -> argparse.ArgumentParser:
    """Monta o parser completo da CLI."""
    parser = argparse.ArgumentParser(
        prog="syra",
        description="SYRA — fabrica de software governada.",
    )
    parser.add_argument("--version", action="version", version=f"syra {__version__}")
    sub = parser.add_subparsers(dest="comando", required=True)

    def com_json(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--json", action="store_true", help="saida em JSON")
        return p

    build = com_json(sub.add_parser("build", help="executa uma missao de construcao"))
    build.add_argument("objetivo", help="o que deve ser construido")
    build.add_argument("--kind", default="library",
                       choices=["library", "cli", "service"],
                       help="formato do projeto gerado")
    build.add_argument("--gain", nargs="+", default=["capability"],
                       choices=[g.value for g in Gain],
                       help="ganhos que justificam a missao")
    build.add_argument("--synthesizer-cmd", default=None,
                       help="comando de agente externo que gera o codigo")
    build.set_defaults(func=cmd_build)

    guard = com_json(sub.add_parser("guard", help="avalia o risco de um comando"))
    # REMAINDER: o comando avaliado costuma ter flags proprias (-rf, --force)
    # que o argparse tentaria interpretar como flags da propria SYRA.
    guard.add_argument("comando", nargs=argparse.REMAINDER,
                       help="o comando a avaliar, cru ou entre aspas")
    guard.set_defaults(func=cmd_guard)

    learn = com_json(sub.add_parser("learn", help="ciclo de auto-otimizacao"))
    learn.add_argument("--dry-run", action="store_true",
                       help="avalia sem gravar a nova politica")
    learn.set_defaults(func=cmd_learn)

    funnel = sub.add_parser("funnel", help="squad de funil de vendas")
    fsub = funnel.add_subparsers(dest="acao", required=True)

    com_json(fsub.add_parser("list", help="dores, funis e etapas")).add_argument(
        "--nivel", choices=["iniciante", "intermediario", "avancado"], default=None)
    fsub.choices["list"].set_defaults(func=cmd_funnel_list)

    page = com_json(fsub.add_parser("page", help="gera as paginas do funil"))
    page.add_argument("--funil", required=True,
                      help=f"um de: {', '.join(f.id for f in FUNIS)}")
    page.add_argument("--angulo", choices=[a.value for a in Angulo], default=None,
                      help="gera so este angulo; por padrao gera os tres")
    page.add_argument("--out", default="funil_paginas", help="diretorio de saida")
    page.set_defaults(func=cmd_funnel_page)

    serve = com_json(fsub.add_parser("serve", help="qual angulo servir agora"))
    serve.add_argument("--funil", required=True)
    serve.add_argument("--segmento", required=True)
    serve.set_defaults(func=cmd_funnel_serve)

    track = com_json(fsub.add_parser("track", help="registra exposicao e conversao"))
    track.add_argument("--funil", required=True)
    track.add_argument("--segmento", default="geral")
    track.add_argument("--angulo", default=None)
    track.add_argument("--estagio", default=None, choices=["TOFU", "MOFU", "BOFU"])
    track.add_argument("--exposicoes", type=int, default=1)
    track.add_argument("--conversoes", type=int, default=0)
    track.set_defaults(func=cmd_funnel_track)

    otimizar = com_json(fsub.add_parser("optimize", help="ciclo do squad de funil"))
    otimizar.add_argument("--dry-run", action="store_true")
    otimizar.set_defaults(func=cmd_funnel_optimize)

    com_json(sub.add_parser("report", help="painel do sistema")).set_defaults(
        func=cmd_report)
    com_json(sub.add_parser("doctor", help="diagnostico do ambiente")).set_defaults(
        func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da CLI."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
