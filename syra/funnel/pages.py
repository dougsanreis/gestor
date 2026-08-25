"""Renderizador das paginas de venda e de captura.

As paginas sao HTML autocontido: sem CDN, sem framework, sem fonte externa.
Isso nao e limitacao, e requisito de conversao — pagina que depende de terceiro
carrega mais devagar, quebra sozinha e vaza dado do visitante.

O design responde ao tema do visitante (claro ou escuro), funciona em telas
pequenas e nao usa JavaScript para nada estrutural: o acordeao de objecoes e
``<details>`` nativo. Se o script nao carregar, a pagina continua vendendo.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass

from syra.funnel.copy import CopyPaginaCaptura, CopyPaginaVendas

_CSS = """
:root {
  --fundo: #ffffff; --fundo-alt: #f5f6f8; --cartao: #ffffff;
  --texto: #16181d; --texto-suave: #565b66; --borda: #e2e5ea;
  --acento: #1f5fd6; --acento-texto: #ffffff; --destaque: #f0f4fd;
  --sombra: 0 1px 2px rgba(16,18,29,.06), 0 12px 32px rgba(16,18,29,.08);
  --raio: 14px; --largura: 68rem;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --fundo: #0d0f14; --fundo-alt: #12151c; --cartao: #161a22;
    --texto: #eef1f6; --texto-suave: #9aa3b2; --borda: #252b36;
    --acento: #5b8cf5; --acento-texto: #0d0f14; --destaque: #151d2e;
    --sombra: 0 1px 2px rgba(0,0,0,.4), 0 16px 40px rgba(0,0,0,.45);
  }
}
:root[data-theme="dark"] {
  --fundo: #0d0f14; --fundo-alt: #12151c; --cartao: #161a22;
  --texto: #eef1f6; --texto-suave: #9aa3b2; --borda: #252b36;
  --acento: #5b8cf5; --acento-texto: #0d0f14; --destaque: #151d2e;
  --sombra: 0 1px 2px rgba(0,0,0,.4), 0 16px 40px rgba(0,0,0,.45);
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--fundo); color: var(--texto);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;
  font-size: 17px; line-height: 1.65;
  -webkit-font-smoothing: antialiased;
}
.envelope { max-width: var(--largura); margin: 0 auto; padding: 0 1.5rem; }
section { padding: 4.5rem 0; border-bottom: 1px solid var(--borda); }
section:last-of-type { border-bottom: 0; }
h1, h2, h3 { line-height: 1.15; letter-spacing: -0.022em; margin: 0 0 1rem; }
h1 { font-size: clamp(2rem, 5.2vw, 3.4rem); font-weight: 780; }
h2 { font-size: clamp(1.45rem, 3.2vw, 2.1rem); font-weight: 700; }
h3 { font-size: 1.12rem; font-weight: 650; }
p { margin: 0 0 1.1rem; }
.kicker {
  display: inline-block; font-size: .78rem; font-weight: 640;
  letter-spacing: .09em; text-transform: uppercase; color: var(--acento);
  background: var(--destaque); border: 1px solid var(--borda);
  padding: .4rem .8rem; border-radius: 999px; margin-bottom: 1.5rem;
}
.hero { padding: 5.5rem 0 4rem; }
.subhead { font-size: clamp(1.05rem, 2.1vw, 1.28rem); color: var(--texto-suave);
           max-width: 46rem; }
.cta {
  display: inline-block; background: var(--acento); color: var(--acento-texto);
  font-weight: 660; font-size: 1.05rem; text-decoration: none;
  padding: .95rem 2rem; border-radius: var(--raio); margin-top: 1.6rem;
  box-shadow: var(--sombra); border: 0; cursor: pointer;
}
.cta:hover { filter: brightness(1.08); }
.cta:focus-visible { outline: 3px solid var(--acento); outline-offset: 3px; }
.nota { font-size: .9rem; color: var(--texto-suave); margin-top: .8rem; }
.citacoes { display: grid; gap: 1rem; margin: 2rem 0; }
blockquote {
  margin: 0; padding: 1.25rem 1.5rem; background: var(--fundo-alt);
  border-left: 3px solid var(--acento); border-radius: 0 var(--raio) var(--raio) 0;
  font-size: 1.05rem; color: var(--texto);
}
.custo { font-weight: 620; color: var(--texto); }
.grade { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); }
.cartao {
  background: var(--cartao); border: 1px solid var(--borda);
  border-radius: var(--raio); padding: 1.4rem; box-shadow: var(--sombra);
}
.mecanismo { background: var(--fundo-alt); }
.mecanismo p { font-size: 1.08rem; max-width: 48rem; }
ul.itens { list-style: none; padding: 0; margin: 1.5rem 0; display: grid; gap: .8rem; }
ul.itens li { padding-left: 1.9rem; position: relative; }
ul.itens li::before {
  content: "✓"; position: absolute; left: 0; top: 0;
  color: var(--acento); font-weight: 700;
}
.oferta { background: var(--destaque); }
details {
  border: 1px solid var(--borda); border-radius: var(--raio);
  padding: 1rem 1.25rem; margin-bottom: .8rem; background: var(--cartao);
}
details[open] { box-shadow: var(--sombra); }
summary { cursor: pointer; font-weight: 640; list-style: none; }
summary::-webkit-details-marker { display: none; }
summary::after { content: " +"; color: var(--acento); font-weight: 700; }
details[open] summary::after { content: " −"; }
details p { margin: .9rem 0 0; color: var(--texto-suave); }
.garantia { border: 2px dashed var(--acento); border-radius: var(--raio);
            padding: 1.5rem; background: var(--cartao); }
.transparencia li { color: var(--texto-suave); }
.fechamento { text-align: center; padding: 5rem 0; }
.fechamento h2 { max-width: 40rem; margin-inline: auto; }
form.captura { display: grid; gap: .8rem; max-width: 27rem; margin-top: 1.6rem; }
input[type="email"] {
  padding: .9rem 1rem; border-radius: var(--raio); font-size: 1rem;
  border: 1px solid var(--borda); background: var(--cartao); color: var(--texto);
}
input[type="email"]:focus-visible { outline: 3px solid var(--acento); outline-offset: 1px; }
footer { padding: 2.5rem 0 3.5rem; color: var(--texto-suave); font-size: .88rem; }
.aviso {
  border: 1px solid var(--acento); background: var(--destaque);
  border-radius: var(--raio); padding: 1rem 1.25rem; margin: 1.5rem 0;
  font-size: .92rem;
}
@media (max-width: 640px) { section { padding: 3rem 0; } .hero { padding: 3.5rem 0 2.5rem; } }
"""


def _e(texto: str) -> str:
    """Escapa texto para insercao segura em HTML."""
    return html.escape(str(texto), quote=True)


@dataclass(frozen=True)
class PaginaRenderizada:
    """Uma pagina pronta para publicar."""

    caminho: str
    html: str
    variante: str
    segmento: str


def _cabecalho(titulo: str, variante: str, segmento: str, funil_id: str) -> str:
    contexto = json.dumps({"funil": funil_id, "variante": variante,
                           "segmento": segmento}, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)}</title>
<meta name="description" content="{_e(titulo)}">
<style>{_CSS}</style>
</head>
<body data-funil="{_e(funil_id)}" data-variante="{_e(variante)}"
      data-segmento="{_e(segmento)}">
<script>
  // Exposto para qualquer ferramenta de analitica ler qual variante foi
  // servida. Nao envia nada sozinho: quem decide o destino e voce.
  window.SYRA_FUNNEL = {contexto};
</script>
"""


_RODAPE = """
<footer class="envelope">
  <p>Pagina gerada pela SYRA Funnel Squad. Nenhum dado sai desta pagina sem
     integracao explicita.</p>
</footer>
</body>
</html>
"""


def render_pagina_vendas(copy: CopyPaginaVendas, segmento: str = "geral",
                         acao: str = "#oferta") -> PaginaRenderizada:
    """Renderiza a pagina de vendas completa a partir da copy.

    Args:
        copy: blocos de texto ja gerados.
        segmento: audiencia servida, usado no rastreio de variante.
        acao: destino do botao de acao.

    Returns:
        A pagina pronta, com o identificador de variante embutido.
    """
    partes = [_cabecalho(copy.headline, copy.angulo, segmento, copy.funil_id)]

    partes.append(f"""
<section class="hero envelope">
  <span class="kicker">{_e(copy.kicker)}</span>
  <h1>{_e(copy.headline)}</h1>
  <p class="subhead">{_e(copy.subhead)}</p>
  <a class="cta" href="{_e(acao)}">{_e(copy.cta_principal)}</a>
  <p class="nota">{_e(copy.transparencia[2])}</p>
</section>""")

    citacoes = "\n".join(f"    <blockquote>“{_e(c)}”</blockquote>"
                         for c in copy.dor_citacoes)
    partes.append(f"""
<section class="envelope">
  <h2>{_e(copy.dor_titulo)}</h2>
  <div class="citacoes">
{citacoes}
  </div>
  <p class="custo">{_e(copy.dor_custo)}</p>
  <p>{_e(copy.inimigo)}</p>
</section>""")

    provas = "\n".join(f"    <li>{_e(p)}</li>" for p in copy.provas)
    partes.append(f"""
<section class="mecanismo">
  <div class="envelope">
    <h2>{_e(copy.mecanismo_titulo)}</h2>
    <p>{_e(copy.mecanismo_corpo)}</p>
    <ul class="itens">
{provas}
    </ul>
  </div>
</section>""")

    itens = "\n".join(f"      <li>{_e(i)}</li>" for i in copy.oferta_itens)
    aviso = ""
    if copy.provas_pendentes:
        pend = "".join(f"<p>{_e(p)}</p>" for p in copy.provas_pendentes)
        aviso = f'    <div class="aviso"><strong>Prova pendente.</strong>{pend}</div>'
    partes.append(f"""
<section class="oferta" id="oferta">
  <div class="envelope">
    <h2>{_e(copy.oferta_nome)}</h2>
    <ul class="itens">
{itens}
    </ul>
    <p class="custo">{_e(copy.ancora)}</p>
{aviso}
    <div class="garantia">
      <h3>Garantia</h3>
      <p>{_e(copy.garantia)}</p>
    </div>
    <a class="cta" href="#fechamento">{_e(copy.cta_principal)}</a>
  </div>
</section>""")

    objecoes = "\n".join(
        f"""    <details>
      <summary>{_e(o.pergunta)}</summary>
      <p>{_e(o.resposta)}</p>
    </details>""" for o in copy.objecoes)
    partes.append(f"""
<section class="envelope">
  <h2>Perguntas que voce provavelmente esta fazendo</h2>
{objecoes}
</section>""")

    transparencia = "\n".join(f"    <li>{_e(t)}</li>" for t in copy.transparencia)
    partes.append(f"""
<section class="envelope">
  <h2>Transparencia antes da decisao</h2>
  <ul class="itens transparencia">
{transparencia}
  </ul>
</section>""")

    partes.append(f"""
<section class="fechamento" id="fechamento">
  <div class="envelope">
    <h2>{_e(copy.fechamento)}</h2>
    <a class="cta" href="{_e(acao)}">{_e(copy.cta_final)}</a>
  </div>
</section>""")

    partes.append(_RODAPE)
    return PaginaRenderizada(caminho=f"vendas_{copy.funil_id}_{copy.angulo}.html",
                             html="".join(partes), variante=copy.angulo,
                             segmento=segmento)


def render_pagina_captura(copy: CopyPaginaCaptura, segmento: str = "geral",
                          acao: str = "#") -> PaginaRenderizada:
    """Renderiza a pagina de captura da etapa MOFU."""
    bullets = "\n".join(f"    <li>{_e(b.lstrip('- '))}</li>" for b in copy.bullets)
    corpo = f"""
<section class="hero envelope">
  <span class="kicker">Material gratuito</span>
  <h1>{_e(copy.headline)}</h1>
  <p class="subhead">{_e(copy.subhead)}</p>
  <div class="cartao" style="margin-top:2rem">
    <h3>{_e(copy.entregavel)}</h3>
    <ul class="itens">
{bullets}
    </ul>
    <form class="captura" method="post" action="{_e(acao)}">
      <label for="email" class="nota">Seu melhor e-mail</label>
      <input id="email" type="email" name="email" required
             placeholder="voce@exemplo.com" autocomplete="email">
      <button class="cta" type="submit">{_e(copy.cta)}</button>
    </form>
    <p class="nota">{_e(copy.microcopy)}</p>
  </div>
  <p class="nota">{_e(copy.privacidade)}</p>
</section>
"""
    pagina = (_cabecalho(copy.headline, "captura", segmento, copy.funil_id)
              + corpo + _RODAPE)
    return PaginaRenderizada(caminho=f"captura_{copy.funil_id}.html", html=pagina,
                             variante="captura", segmento=segmento)
