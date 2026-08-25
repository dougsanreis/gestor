"""Os tres funis do nicho de vibe code, escolhidos por prioridade de dor.

A selecao nao e opinativa: cada funil ataca a dor de maior ``prioridade``
(intensidade x frequencia) de uma persona distinta. Isso evita tres funis
disputando a mesma audiencia e cobre o nicho de ponta a ponta, do iniciante
travado ao lider que responde pelo time.

Cada funil declara topo, meio e fundo com objetivo, ativo, gatilho de passagem
e a metrica que decide se aquela etapa esta funcionando.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Etapa:
    """Uma etapa do funil, com criterio objetivo de passagem."""

    estagio: str          # TOFU, MOFU ou BOFU
    objetivo: str
    ativo: str            # o que a pessoa recebe ou consome nesta etapa
    gatilho: str          # o que a faz avancar
    metrica: str          # o numero que diz se a etapa funciona
    meta: float           # valor de referencia da metrica, em fracao
    cta: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Oferta:
    """A oferta do fundo do funil."""

    nome: str
    entregaveis: tuple[str, ...]
    ancora_de_valor: str
    garantia: str
    risco_revertido: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["entregaveis"] = list(self.entregaveis)
        return data


@dataclass(frozen=True)
class Funil:
    """Funil completo: dor, promessa, mecanismo, oferta e jornada."""

    id: str
    nome: str
    persona_id: str
    dor_id: str
    promessa: str
    inimigo: str          # o que a pessoa culpa hoje; a copy concorda com ela
    mecanismo: str        # por que este caminho funciona e o outro nao
    prova: tuple[str, ...]
    oferta: Oferta
    etapas: tuple[Etapa, ...]

    def etapa(self, estagio: str) -> Etapa | None:
        """Busca uma etapa pelo estagio (TOFU, MOFU, BOFU)."""
        return next((e for e in self.etapas if e.estagio == estagio.upper()), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "nome": self.nome, "persona_id": self.persona_id,
            "dor_id": self.dor_id, "promessa": self.promessa,
            "inimigo": self.inimigo, "mecanismo": self.mecanismo,
            "prova": list(self.prova), "oferta": self.oferta.to_dict(),
            "etapas": [e.to_dict() for e in self.etapas],
        }


FUNIL_NO_AR = Funil(
    id="do_prototipo_ao_ar",
    nome="Do prototipo ao ar",
    persona_id="iniciante",
    dor_id="demo_quebra",
    promessa=(
        "Transformar o que voce ja construiu num link que aguenta outras "
        "pessoas usando — sem virar programador para isso."
    ),
    inimigo=(
        "O conteudo que ensina a construir a demo e some exatamente na hora "
        "de colocar no ar."
    ),
    mecanismo=(
        "A demo quebra em producao por um numero pequeno de motivos que se "
        "repetem: entrada que voce nunca testou, chave exposta, estado que so "
        "existia na sua maquina e erro sem tratamento. Fechar essa lista, nessa "
        "ordem, resolve a maior parte dos casos — e da para verificar cada item "
        "com um teste que roda em segundos."
    ),
    prova=(
        "Cada item da lista vira um teste executavel que voce ve passar.",
        "O passo a passo termina em link publico, nao em slide.",
        "Funciona com a ferramenta de IA que voce ja usa hoje.",
    ),
    oferta=Oferta(
        nome="Kit Prototipo ao Ar",
        entregaveis=(
            "Checklist executavel dos 12 motivos que derrubam demo em producao",
            "Suite de testes pronta para colar no seu projeto",
            "Roteiro de publicacao do zero ao link publico",
            "Guia de chaves e segredos para quem nunca configurou nenhum",
        ),
        ancora_de_valor=(
            "Uma unica quebra em producao na frente de um cliente custa mais "
            "que o kit inteiro."
        ),
        garantia="Sete dias. Rodou o checklist e nao saiu do lugar, devolvemos.",
        risco_revertido="Voce testa antes de decidir se vale.",
    ),
    etapas=(
        Etapa(
            estagio="TOFU",
            objetivo="Fazer a pessoa reconhecer a propria situacao em uma frase",
            ativo=("Post e video curto: 'seu app funciona so na sua maquina — "
                   "e tem motivo tecnico para isso'"),
            gatilho="Reconhecimento: ela ja passou por isso ontem",
            metrica="taxa de clique para a pagina de captura",
            meta=0.04,
            cta="Ver os 12 motivos",
        ),
        Etapa(
            estagio="MOFU",
            objetivo="Entregar valor real antes de qualquer venda",
            ativo="Pagina de captura com o checklist dos 12 motivos por e-mail",
            gatilho="Ela roda o checklist e encontra ao menos um problema real",
            metrica="taxa de conversao de visita em lead",
            meta=0.30,
            cta="Receber o checklist",
        ),
        Etapa(
            estagio="BOFU",
            objetivo="Converter quem ja viu o proprio problema com os proprios olhos",
            ativo="Pagina de vendas do Kit Prototipo ao Ar",
            gatilho="Ela achou o problema mas nao sabe corrigir sozinha",
            metrica="taxa de conversao de lead em cliente",
            meta=0.05,
            cta="Colocar meu projeto no ar",
        ),
    ),
)

FUNIL_LOOP = Funil(
    id="fim_do_loop_de_erro",
    nome="Fim do loop de erro",
    persona_id="intermediario",
    dor_id="regressao_silenciosa",
    promessa=(
        "Parar o ciclo em que cada correcao da IA quebra outra coisa — e "
        "recuperar as horas que voce queima girando em falso."
    ),
    inimigo=(
        "A crenca de que basta pedir com mais detalhe. O problema nao e o "
        "prompt: e a ausencia de um criterio que diga quando parar."
    ),
    mecanismo=(
        "O loop acontece porque nada mede se a correcao piorou o resto. Com "
        "uma suite que roda em segundos e um limite de tentativas, a IA para de "
        "girar: ou a correcao passa em tudo que ja funcionava, ou ela e "
        "descartada e voce recebe o motivo. Reparo com teto, nunca infinito."
    ),
    prova=(
        "Limite explicito de tentativas: sem reparo infinito consumindo credito.",
        "Toda falha vira memoria: o mesmo erro nao volta duas vezes do zero.",
        "A suite roda em segundos, entao o ciclo cabe no seu fluxo.",
    ),
    oferta=Oferta(
        nome="Protocolo Anti-Loop",
        entregaveis=(
            "Suite de regressao que roda em segundos no seu projeto",
            "Limite de tentativas de reparo com relatorio do que foi tentado",
            "Memoria de erros: cada falha resolvida vira prevencao permanente",
            "Painel do que ficou mais lento e do que voltou a quebrar",
        ),
        ancora_de_valor=(
            "Duas horas por semana giradas em loop somam mais de cem horas "
            "por ano."
        ),
        garantia="Catorze dias. Se o loop continuar igual, devolvemos.",
        risco_revertido="Voce mede o antes e o depois no seu proprio projeto.",
    ),
    etapas=(
        Etapa(
            estagio="TOFU",
            objetivo="Nomear o padrao que a pessoa vive e ainda nao sabe nomear",
            ativo="Thread e video: 'por que a IA conserta e quebra ao mesmo tempo'",
            gatilho="Ela percebe que o problema tem nome e tem causa",
            metrica="taxa de clique para a pagina de captura",
            meta=0.05,
            cta="Entender o padrao",
        ),
        Etapa(
            estagio="MOFU",
            objetivo="Provar o diagnostico com o projeto dela",
            ativo="Diagnostico de regressao gratuito por e-mail, em 3 passos",
            gatilho="O diagnostico aponta uma regressao real que ela nao tinha visto",
            metrica="taxa de conversao de visita em lead",
            meta=0.28,
            cta="Rodar o diagnostico",
        ),
        Etapa(
            estagio="BOFU",
            objetivo="Vender o criterio de parada, nao mais um prompt",
            ativo="Pagina de vendas do Protocolo Anti-Loop",
            gatilho="Ela viu a regressao e quer que isso pare de acontecer",
            metrica="taxa de conversao de lead em cliente",
            meta=0.06,
            cta="Quebrar o loop agora",
        ),
    ),
)

FUNIL_GOVERNANCA = Funil(
    id="governanca_de_codigo_gerado",
    nome="Governanca de codigo gerado por IA",
    persona_id="avancado",
    dor_id="revisao_nao_escala",
    promessa=(
        "Manter a velocidade que a IA deu ao seu time sem que a revisao humana "
        "vire o gargalo — com criterio de aprovacao explicito e auditavel."
    ),
    inimigo=(
        "A escolha falsa entre travar a entrega ou aceitar codigo que ninguem "
        "revisou."
    ),
    mecanismo=(
        "Revisao humana nao escala com geracao automatica: e uma corrida "
        "perdida por construcao. O que escala e mover o criterio para fora da "
        "cabeca do revisor — portoes executaveis que rodam sempre igual, uma "
        "politica versionada que diz o que aprova, e trilha de auditoria de "
        "cada decisao. O humano passa a revisar o criterio, nao cada diff."
    ),
    prova=(
        "Politica de aprovacao versionada em arquivo, nao em convencao oral.",
        "Trilha de auditoria: cada aprovacao registra evidencia e confianca.",
        "O nucleo de seguranca e imutavel: nem a automacao pode afrouxa-lo.",
    ),
    oferta=Oferta(
        nome="Camada de Governanca para Times de IA",
        entregaveis=(
            "Portoes executaveis: sintaxe, revisao estatica, testes e cobertura",
            "Politica de aprovacao versionada e igual para todo o time",
            "Trilha de auditoria de cada decisao, com evidencia e confianca",
            "Quarentena de comandos destrutivos antes da execucao",
            "Relatorio de regressao e de custo por entrega",
        ),
        ancora_de_valor=(
            "Um incidente em producao causado por codigo nao revisado custa "
            "mais que um trimestre da camada inteira."
        ),
        garantia="Trinta dias. Sem reducao mensuravel de gargalo, devolvemos.",
        risco_revertido="Piloto em um repositorio antes de qualquer decisao de time.",
    ),
    etapas=(
        Etapa(
            estagio="TOFU",
            objetivo="Colocar numero no gargalo que o lider ja sente",
            ativo="Artigo com dados: 'quanto codigo seu time gera vs. quanto voce revisa'",
            gatilho="O numero dele e pior do que ele imaginava",
            metrica="taxa de clique para a pagina de captura",
            meta=0.03,
            cta="Calcular meu gargalo",
        ),
        Etapa(
            estagio="MOFU",
            objetivo="Transformar percepcao em diagnostico defensavel",
            ativo="Diagnostico de governanca do repositorio, em PDF",
            gatilho="Ele recebe um relatorio que consegue levar para a diretoria",
            metrica="taxa de conversao de visita em lead",
            meta=0.22,
            cta="Receber o diagnostico",
        ),
        Etapa(
            estagio="BOFU",
            objetivo="Converter com piloto de baixo risco, nao com contrato grande",
            ativo="Pagina de vendas da Camada de Governanca + piloto guiado",
            gatilho="Ele quer resolver antes que vire incidente",
            metrica="taxa de conversao de lead em cliente",
            meta=0.08,
            cta="Comecar o piloto",
        ),
    ),
)

FUNIS: tuple[Funil, ...] = (FUNIL_NO_AR, FUNIL_LOOP, FUNIL_GOVERNANCA)


def por_id(funil_id: str) -> Funil | None:
    """Busca um funil pelo identificador."""
    return next((f for f in FUNIS if f.id == funil_id), None)
