"""Testes do squad de funil: estatistica, copy, paginas e promocao governada."""

from __future__ import annotations

import html.parser
import random

import pytest

from syra.funnel.blueprint import FUNIS, por_id as funil_por_id
from syra.funnel.copy import Angulo, gerar_copy_captura, gerar_copy_vendas
from syra.funnel.pages import render_pagina_captura, render_pagina_vendas
from syra.funnel.personas import PERSONAS, dores_por_nivel, por_id as persona_por_id
from syra.funnel.squad import FunnelSquad, StageStore
from syra.funnel.variants import VariantStore, wilson


# ------------------------------------------------------------- estatistica ---

def test_wilson_pune_amostra_pequena():
    assert wilson(1, 2)[0] < wilson(40, 200)[0]


def test_wilson_sem_amostra_e_maximamente_incerto():
    assert wilson(0, 0) == (0.0, 1.0)


def test_wilson_rejeita_entrada_incoerente():
    with pytest.raises(ValueError):
        wilson(5, 2)
    with pytest.raises(ValueError):
        wilson(-1, 10)


def test_intervalo_estreita_com_mais_amostra():
    estreito = wilson(100, 1000)
    largo = wilson(10, 100)
    assert (estreito[1] - estreito[0]) < (largo[1] - largo[0])


# ---------------------------------------------------------------- variantes ---

def test_exploracao_cobre_todas_as_variantes_antes_de_explorar():
    store = VariantStore()
    servidas = set()
    for _ in range(60):
        escolhida = store.escolher("f", "s", ["a", "b", "c"])
        servidas.add(escolhida)
        store.registrar("f", "s", escolhida)
    assert servidas == {"a", "b", "c"}


def test_nao_declara_vencedora_com_amostra_pequena():
    store = VariantStore()
    store.registrar("f", "s", "a", 10, 5)
    store.registrar("f", "s", "b", 10, 1)
    decisao = store.decidir("f", "s")
    assert decisao.confiante is False
    assert "amostra insuficiente" in decisao.motivo


def test_declara_vencedora_quando_intervalos_separam():
    store = VariantStore()
    store.registrar("f", "s", "a", 1000, 200)
    store.registrar("f", "s", "b", 1000, 20)
    decisao = store.decidir("f", "s")
    assert decisao.confiante is True
    assert decisao.vencedora == "a"


def test_nao_declara_vencedora_com_intervalos_sobrepostos():
    store = VariantStore()
    store.registrar("f", "s", "a", 500, 51)
    store.registrar("f", "s", "b", 500, 49)
    assert store.decidir("f", "s").confiante is False


def test_segmentos_mantem_placares_independentes():
    store = VariantStore()
    store.registrar("f", "iniciante", "dor", 100, 20)
    store.registrar("f", "avancado", "dor", 100, 2)
    assert store.placares("f", "iniciante")["dor"].taxa == 0.2
    assert store.placares("f", "avancado")["dor"].taxa == 0.02


def test_conversoes_nao_podem_exceder_exposicoes():
    with pytest.raises(ValueError):
        VariantStore().registrar("f", "s", "a", 1, 5)


def test_motor_converge_para_a_variante_de_maior_taxa_por_segmento():
    random.seed(3)
    store = VariantStore()
    variantes = ["dor", "promessa", "mecanismo"]
    real = {"dor": 0.02, "promessa": 0.04, "mecanismo": 0.12}
    for _ in range(3000):
        escolhida = store.escolher("f", "s", variantes)
        store.registrar("f", "s", escolhida, 1,
                        1 if random.random() < real[escolhida] else 0)
    decisao = store.decidir("f", "s")
    assert decisao.vencedora == "mecanismo"
    assert decisao.confiante is True


# ---------------------------------------------------------------- audiencia ---

def test_dores_ordenadas_por_prioridade():
    dores = dores_por_nivel()
    assert dores == sorted(dores, key=lambda d: -d.prioridade)


def test_cada_funil_ataca_uma_persona_distinta():
    assert len({f.persona_id for f in FUNIS}) == len(FUNIS)


def test_cada_funil_tem_topo_meio_e_fundo():
    for funil in FUNIS:
        assert {e.estagio for e in funil.etapas} == {"TOFU", "MOFU", "BOFU"}


def test_dor_alvo_do_funil_existe_na_persona():
    for funil in FUNIS:
        persona = persona_por_id(funil.persona_id)
        assert any(d.id == funil.dor_id for d in persona.dores)


# --------------------------------------------------------------------- copy ---

@pytest.mark.parametrize("funil", FUNIS, ids=lambda f: f.id)
@pytest.mark.parametrize("angulo", list(Angulo), ids=lambda a: a.value)
def test_copy_gerada_para_todo_funil_e_angulo(funil, angulo):
    copy = gerar_copy_vendas(funil, persona_por_id(funil.persona_id), angulo)
    assert copy.headline and copy.subhead and copy.cta_principal
    assert copy.objecoes and copy.provas


def test_angulos_produzem_headlines_diferentes():
    funil = FUNIS[0]
    persona = persona_por_id(funil.persona_id)
    headlines = {gerar_copy_vendas(funil, persona, a).headline for a in Angulo}
    assert len(headlines) == len(list(Angulo))


def test_copy_usa_a_fala_literal_do_cliente():
    funil = FUNIS[0]
    persona = persona_por_id(funil.persona_id)
    copy = gerar_copy_vendas(funil, persona)
    assert set(copy.dor_citacoes) == {d.fala_do_cliente for d in persona.dores}


def test_sem_prova_fornecida_a_copy_declara_prova_pendente():
    funil = FUNIS[0]
    copy = gerar_copy_vendas(funil, persona_por_id(funil.persona_id))
    assert copy.provas_pendentes


def test_prova_real_fornecida_substitui_o_aviso():
    funil = FUNIS[0]
    copy = gerar_copy_vendas(funil, persona_por_id(funil.persona_id),
                             provas_reais=("120 alunos concluiram o modulo 1",))
    assert copy.provas_pendentes == ()
    assert "120 alunos" in copy.provas[0]


def test_toda_objecao_da_persona_recebe_resposta():
    for funil in FUNIS:
        persona = persona_por_id(funil.persona_id)
        copy = gerar_copy_vendas(funil, persona)
        assert len(copy.objecoes) == len(persona.objecoes)
        assert all(o.resposta for o in copy.objecoes)


def test_objecao_sobre_teste_nao_cai_na_resposta_sobre_tempo():
    persona = persona_por_id("intermediario")
    funil = funil_por_id("fim_do_loop_de_erro")
    copy = gerar_copy_vendas(funil, persona)
    resposta = next(o.resposta for o in copy.objecoes if "teste" in o.pergunta.lower())
    assert "gerado junto com o codigo" in resposta


# ------------------------------------------------------------------ paginas ---

class _ValidadorHTML(html.parser.HTMLParser):
    """Verifica que as tags abrem e fecham na ordem correta."""

    VAZIAS = {"meta", "br", "hr", "img", "input", "link", "source"}

    def __init__(self) -> None:
        super().__init__()
        self.pilha: list[str] = []
        self.erros: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VAZIAS:
            self.pilha.append(tag)

    def handle_endtag(self, tag):
        if self.pilha and self.pilha[-1] == tag:
            self.pilha.pop()
        elif tag in self.pilha:
            self.erros.append(f"aninhamento incorreto em </{tag}>")


@pytest.mark.parametrize("funil", FUNIS, ids=lambda f: f.id)
def test_pagina_de_vendas_e_html_bem_formado(funil):
    persona = persona_por_id(funil.persona_id)
    pagina = render_pagina_vendas(gerar_copy_vendas(funil, persona), persona.id)
    validador = _ValidadorHTML()
    validador.feed(pagina.html)
    assert not validador.erros
    assert not validador.pilha


def test_pagina_de_captura_tem_formulario_e_aviso_de_privacidade():
    funil = FUNIS[0]
    persona = persona_por_id(funil.persona_id)
    pagina = render_pagina_captura(gerar_copy_captura(funil, persona))
    assert 'type="email"' in pagina.html
    assert "sai da lista" in pagina.html


def test_pagina_nao_referencia_recurso_externo():
    funil = FUNIS[0]
    pagina = render_pagina_vendas(
        gerar_copy_vendas(funil, persona_por_id(funil.persona_id)))
    assert "http://" not in pagina.html
    assert "https://" not in pagina.html


def test_pagina_escapa_conteudo_hostil():
    funil = FUNIS[0]
    copy = gerar_copy_vendas(funil, persona_por_id(funil.persona_id),
                             provas_reais=("<script>alert(1)</script>",))
    pagina = render_pagina_vendas(copy)
    assert "<script>alert(1)</script>" not in pagina.html
    assert "&lt;script&gt;" in pagina.html


def test_pagina_declara_a_variante_servida():
    funil = FUNIS[0]
    pagina = render_pagina_vendas(
        gerar_copy_vendas(funil, persona_por_id(funil.persona_id), Angulo.MECANISMO),
        segmento="avancado")
    assert 'data-variante="mecanismo"' in pagina.html
    assert 'data-segmento="avancado"' in pagina.html


# ------------------------------------------------------------------- squad ---

def test_squad_nao_promove_sem_separacao_estatistica():
    squad = FunnelSquad()
    squad.variants.registrar("do_prototipo_ao_ar", "iniciante", "dor", 50, 5)
    squad.variants.registrar("do_prototipo_ao_ar", "iniciante", "promessa", 50, 4)
    assert squad.cycle(apply=True)["promovidas"] == []


def test_squad_promove_quando_ha_separacao():
    squad = FunnelSquad()
    squad.variants.registrar("do_prototipo_ao_ar", "iniciante", "dor", 1000, 200)
    squad.variants.registrar("do_prototipo_ao_ar", "iniciante", "promessa", 1000, 20)
    squad.variants.registrar("do_prototipo_ao_ar", "iniciante", "mecanismo", 1000, 15)
    promovidas = squad.cycle(apply=True)["promovidas"]
    assert {"funil": "do_prototipo_ao_ar", "segmento": "iniciante",
            "angulo": "dor"} in promovidas
    assert squad.padroes.get("do_prototipo_ao_ar", "iniciante") == "dor"


def test_squad_bloqueia_publicacao_sem_prova_verificada():
    relatorio = FunnelSquad().cycle(apply=False)
    assert len(relatorio["bloqueios_de_publicacao"]) == len(FUNIS)


def test_agente_de_etapa_aponta_metrica_abaixo_da_meta():
    squad = FunnelSquad()
    squad.stages.registrar("do_prototipo_ao_ar", "TOFU", 5000, 50)
    relatorio = squad.cycle(apply=False)
    alvos = [r for r in relatorio["recomendacoes"]
             if r["change"].get("tipo") == "etapa_abaixo_da_meta"]
    assert any(r["target"].endswith("TOFU") for r in alvos)


def test_agente_de_etapa_ignora_amostra_pequena():
    squad = FunnelSquad()
    squad.stages.registrar("do_prototipo_ao_ar", "TOFU", 10, 0)
    relatorio = squad.cycle(apply=False)
    assert not [r for r in relatorio["recomendacoes"]
                if r["change"].get("tipo") == "etapa_abaixo_da_meta"]


def test_placar_de_etapa_rejeita_avanco_maior_que_entrada():
    with pytest.raises(ValueError):
        StageStore().registrar("f", "TOFU", 10, 20)
