"""Gerador de copy humanizada a partir de dor real.

Copy humanizada aqui tem definicao operacional, nao estetica:

1. abre com a frase que a propria pessoa usa (``fala_do_cliente``), nao com
   adjetivo sobre o produto;
2. concorda com quem ela culpa hoje antes de propor outro caminho;
3. explica o mecanismo — por que funciona — em vez de prometer resultado;
4. responde a objecao dela com o custo honesto, incluindo o que o produto
   nao faz;
5. nunca usa numero de prova que nao tenha sido fornecido.

O ultimo item e o mais importante: o gerador se recusa a inventar depoimento,
faturamento ou quantidade de alunos. Onde nao ha prova, ele emite um marcador
explicito de prova pendente, para que ninguem publique numero inventado.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from syra.funnel.blueprint import Funil
from syra.funnel.personas import Persona


class Angulo(str, Enum):
    """Angulo de abertura da pagina. Cada um e uma variante testavel."""

    DOR = "dor"
    PROMESSA = "promessa"
    MECANISMO = "mecanismo"


@dataclass(frozen=True)
class BlocoObjecao:
    """Uma objecao e a resposta honesta a ela."""

    pergunta: str
    resposta: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CopyPaginaVendas:
    """Todos os blocos de texto de uma pagina de vendas."""

    funil_id: str
    persona_id: str
    angulo: str
    kicker: str
    headline: str
    subhead: str
    cta_principal: str
    dor_titulo: str
    dor_citacoes: tuple[str, ...]
    dor_custo: str
    inimigo: str
    mecanismo_titulo: str
    mecanismo_corpo: str
    provas: tuple[str, ...]
    oferta_nome: str
    oferta_itens: tuple[str, ...]
    ancora: str
    garantia: str
    objecoes: tuple[BlocoObjecao, ...]
    transparencia: tuple[str, ...]
    fechamento: str
    cta_final: str
    provas_pendentes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for chave in ("dor_citacoes", "provas", "oferta_itens", "transparencia",
                      "provas_pendentes"):
            data[chave] = list(data[chave])
        data["objecoes"] = [o.to_dict() for o in self.objecoes]
        return data


@dataclass(frozen=True)
class CopyPaginaCaptura:
    """Blocos de texto de uma pagina de captura."""

    funil_id: str
    persona_id: str
    headline: str
    subhead: str
    entregavel: str
    bullets: tuple[str, ...]
    cta: str
    microcopy: str
    privacidade: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["bullets"] = list(data["bullets"])
        return data


# Respostas por tipo de objecao. Cada uma admite um limite real do produto:
# objecao respondida sem custo declarado soa como venda, nao como resposta.
_RESPOSTAS = {
    "aprender": (
        "Nao. O material assume que voce vai continuar construindo com IA. "
        "O que muda e que voce passa a ter como verificar o que ela entregou. "
        "Se o seu objetivo e virar engenheiro de software, isto aqui e pouco."
    ),
    "diferenca": (
        "A diferenca e o formato: nada aqui termina em teoria. Cada passo "
        "termina em algo que roda na sua maquina e mostra verde ou vermelho. "
        "Se voce nao rodar, nao serve para nada."
    ),
    "travar": (
        "Voce vai travar em algum momento — todo mundo trava. O que existe e um "
        "caminho de diagnostico para transformar 'quebrou' em 'quebrou aqui, "
        "por isso'. Isso e o que destrava sozinho na maior parte das vezes."
    ),
    "tempo": (
        "O ciclo completo cabe em sessoes curtas, porque a verificacao roda em "
        "segundos. O tempo que isso toma sai do tempo que hoje voce gasta "
        "girando em loop."
    ),
    "atrasar": (
        "Nos primeiros dias, sim: montar a verificacao custa tempo. A conta vira "
        "quando a primeira regressao e pega antes de chegar no cliente."
    ),
    "ferramenta": (
        "Funciona com a que voce ja usa. O criterio de aprovacao roda fora da "
        "ferramenta de IA, entao nao importa qual delas gerou o codigo."
    ),
    "teste": (
        "Escrever teste manualmente dobraria mesmo. Por isso o teste e gerado "
        "junto com o codigo e roda em segundos — se levar minutos, ninguem roda."
    ),
    "processo": (
        "Vira, se depender de disciplina. Por isso o criterio e executavel: ele "
        "roda no CI e bloqueia sozinho. Ninguem precisa lembrar de aplicar."
    ),
    "integra": (
        "Roda como comando com codigo de saida definido. Entra em CI, hook de "
        "commit ou script sem adaptacao."
    ),
    "custo": (
        "O piloto e em um repositorio, com o resultado medido antes e depois. "
        "Se o gargalo nao cair no piloto, nao ha motivo para levar ao time."
    ),
    "afrouxar": (
        "O nucleo de seguranca e imutavel por construcao: a camada de "
        "auto-otimizacao nao consegue alterar taxa de aprovacao de testes nem "
        "limite de achados bloqueantes. Ela so ajusta orcamento e limites "
        "operacionais."
    ),
    "generico": (
        "Depende do seu caso. O caminho honesto e rodar o diagnostico gratuito "
        "antes de decidir: ele mostra o seu numero, nao a media de mercado."
    ),
}

# A ordem importa: gatilhos especificos vem antes dos genericos, senao
# "dobrar meu tempo de entrega" cai na resposta sobre tempo em vez da
# resposta sobre teste.
_PALAVRAS_CHAVE = (
    ("teste", "teste"), ("dobrar", "teste"),
    ("afrouxar", "afrouxar"),
    ("integra", "integra"), (" ci ", "integra"), ("fluxo de revisao", "integra"),
    ("processo", "processo"), ("ignorar", "processo"),
    ("ferramenta", "ferramenta"), ("trocar", "ferramenta"),
    ("atrasar", "atrasar"), ("jeito de trabalhar", "atrasar"),
    ("custo real", "custo"), ("adocao", "custo"),
    ("programar", "aprender"), ("aprender", "aprender"),
    ("curso", "diferenca"), ("teoria", "diferenca"), ("diferente", "diferenca"),
    ("travar", "travar"), ("sozinho", "travar"),
    ("tempo", "tempo"), ("por dia", "tempo"),
)


def _responder(objecao: str) -> str:
    """Escolhe a resposta cujo tema mais se aproxima da objecao."""
    texto = objecao.lower()
    for gatilho, chave in _PALAVRAS_CHAVE:
        if gatilho in texto:
            return _RESPOSTAS[chave]
    return _RESPOSTAS["generico"]


def _headline(funil: Funil, persona: Persona, angulo: Angulo) -> tuple[str, str, str]:
    """Monta kicker, headline e subhead conforme o angulo escolhido."""
    dor = next((d for d in persona.dores if d.id == funil.dor_id), persona.dores[0])

    if angulo is Angulo.DOR:
        return (
            f"Para quem {persona.contexto.split('.')[0].lower()}",
            dor.titulo,
            f"{dor.custo} {funil.promessa}",
        )
    if angulo is Angulo.PROMESSA:
        return (
            funil.oferta.nome,
            funil.promessa,
            f"Sem rodeio: {dor.fala_do_cliente} Esta pagina e sobre resolver isso.",
        )
    return (
        "Como isto funciona",
        funil.mecanismo.split(".")[0].strip() + ".",
        f"{funil.promessa} O metodo esta descrito abaixo, inteiro, antes de "
        "qualquer preco.",
    )


def gerar_copy_vendas(funil: Funil, persona: Persona,
                      angulo: Angulo = Angulo.DOR,
                      provas_reais: tuple[str, ...] = ()) -> CopyPaginaVendas:
    """Gera a copy completa de uma pagina de vendas.

    Args:
        funil: funil de origem, com promessa, mecanismo e oferta.
        persona: audiencia alvo, com dores e objecoes.
        angulo: abertura da pagina; cada angulo e uma variante testavel.
        provas_reais: depoimentos ou numeros verificados fornecidos por voce.
            O gerador nunca inventa prova: sem esta lista, a pagina declara
            explicitamente que a prova esta pendente.

    Returns:
        Todos os blocos de texto da pagina.
    """
    kicker, headline, subhead = _headline(funil, persona, angulo)
    dor = next((d for d in persona.dores if d.id == funil.dor_id), persona.dores[0])
    cta = funil.etapa("BOFU").cta if funil.etapa("BOFU") else "Quero comecar"

    pendentes: list[str] = []
    if not provas_reais:
        pendentes.append(
            "Nenhum depoimento ou numero de resultado foi fornecido. A pagina "
            "usa apenas provas de mecanismo (o que o produto faz), nunca "
            "resultado de terceiros."
        )

    return CopyPaginaVendas(
        funil_id=funil.id,
        persona_id=persona.id,
        angulo=angulo.value,
        kicker=kicker,
        headline=headline,
        subhead=subhead,
        cta_principal=cta,
        dor_titulo="Se alguma destas frases e sua, esta pagina e para voce",
        dor_citacoes=tuple(d.fala_do_cliente for d in persona.dores),
        dor_custo=dor.custo,
        inimigo=funil.inimigo,
        mecanismo_titulo="Por que isto funciona",
        mecanismo_corpo=funil.mecanismo,
        provas=tuple(provas_reais) or funil.prova,
        oferta_nome=funil.oferta.nome,
        oferta_itens=funil.oferta.entregaveis,
        ancora=funil.oferta.ancora_de_valor,
        garantia=funil.oferta.garantia,
        objecoes=tuple(BlocoObjecao(pergunta=o, resposta=_responder(o))
                       for o in persona.objecoes),
        transparencia=(
            f"Para quem e: {persona.resultado_desejado}",
            "Para quem nao e: quem procura resultado sem rodar nada no proprio "
            "projeto.",
            funil.oferta.risco_revertido,
        ),
        fechamento=(
            f"{dor.custo} Continuar do jeito atual tem um custo tambem — ele so "
            "nao aparece na fatura."
        ),
        cta_final=cta,
        provas_pendentes=tuple(pendentes),
    )


def gerar_copy_captura(funil: Funil, persona: Persona) -> CopyPaginaCaptura:
    """Gera a copy da pagina de captura (etapa MOFU do funil)."""
    etapa = funil.etapa("MOFU")
    dor = next((d for d in persona.dores if d.id == funil.dor_id), persona.dores[0])
    entregavel = etapa.ativo if etapa else "Material de diagnostico"

    return CopyPaginaCaptura(
        funil_id=funil.id,
        persona_id=persona.id,
        headline=dor.titulo,
        subhead=f"{dor.fala_do_cliente} Se voce se reconheceu, o material abaixo "
                "mostra onde esta o problema no seu projeto.",
        entregavel=entregavel,
        bullets=tuple(f"- {p}" for p in funil.prova),
        cta=etapa.cta if etapa else "Quero receber",
        microcopy="Chega no seu e-mail em minutos. Sem cadastro longo.",
        privacidade="Seu e-mail e usado para enviar este material e nada mais. "
                    "Voce sai da lista em um clique.",
    )
