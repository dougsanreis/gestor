import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowRight,
  Brain,
  Fingerprint,
  Sparkles,
  Activity,
  Zap,
  Share2,
} from "lucide-react";
import heroImage from "@/assets/hero.jpg";
import { Button } from "@/components/ui/button";
import { CapabilityMatrix } from "@/components/capability-matrix";
import { ARCH_FLOW, INTELLIGENCE_LAYERS, INTELLIGENCE_MATRIX } from "@/lib/syra";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "SYRA VideoOS — Cortes verticais editados com IA" },
      {
        name: "description",
        content:
          "Transforme vídeos curtos em cortes verticais 9:16 com transcrição real, legendas sincronizadas e título viral. Pipeline assíncrono com status em tempo real.",
      },
      { property: "og:title", content: "SYRA VideoOS" },
      {
        property: "og:description",
        content: "Transforme vídeos curtos em cortes verticais editados com IA.",
      },
    ],
  }),
  component: Landing,
});

const FEATURES = [
  { icon: Brain, title: "Narrative Intelligence", desc: "Herói, problema, decisão, transformação e lenda — a estrutura por trás do viral." },
  { icon: Activity, title: "Emotion Graph", desc: "Curiosidade → tensão → escalada → admiração → identidade, mapeada no tempo." },
  { icon: Zap, title: "Viral Moments", desc: "Mudança de status, quebra de expectativa e frases replicáveis detectadas." },
  { icon: Fingerprint, title: "Identity Engine", desc: "Quem o espectador deseja se tornar após assistir." },
  { icon: Share2, title: "Share & Retention", desc: "Por que alguém compartilharia e quais segundos prendem a atenção." },
  { icon: Sparkles, title: "Viral Score V2", desc: "Curiosity, tension, transformation, identity, share e replay." },
];

function Landing() {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-4 py-5 sm:px-6">
        <span className="font-display text-lg font-semibold">
          SYRA <span className="text-gradient">VideoOS</span>
        </span>
        <Button asChild variant="ghost" size="sm">
          <Link to="/auth">Entrar</Link>
        </Button>
      </header>

      <section className="relative overflow-hidden">
        <img
          src={heroImage}
          alt=""
          width={1920}
          height={1080}
          className="pointer-events-none absolute inset-0 size-full object-cover opacity-40"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-background/40 via-background/70 to-background" />
        <div className="relative mx-auto max-w-3xl px-4 py-24 text-center sm:px-6 sm:py-32">
          <span className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-card/50 px-3 py-1 text-xs text-muted-foreground backdrop-blur">
            <Brain className="size-3.5 text-accent" /> Viral Intelligence Operating System
          </span>
          <h1 className="mt-6 font-display text-4xl font-bold leading-tight sm:text-6xl">
            Os virais não editam vídeo.{" "}
            <span className="text-gradient">Editam emoção.</span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-base text-muted-foreground sm:text-lg">
            O SYRA transforma cada vídeo em narrativa → emoção → identidade → retenção
            <strong className="text-foreground/90"> antes</strong> de qualquer corte. A edição é
            quase o último passo, não o primeiro.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild size="lg" className="glow-border">
              <Link to="/upload">
                Enviar vídeo <ArrowRight className="size-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link to="/dashboard">Ver dashboard</Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 pt-10 sm:px-6">
        <div className="glass-panel rounded-2xl p-6 text-center">
          <p className="text-xs uppercase tracking-widest text-muted-foreground">
            Arquitetura narrativa-first
          </p>
          <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-sm">
            {ARCH_FLOW.map((step, i) => (
              <span key={step} className="flex items-center gap-2">
                <span className="rounded-lg bg-muted px-3 py-1.5 font-medium">{step}</span>
                {i < ARCH_FLOW.length - 1 && <span className="text-accent">→</span>}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
        <h2 className="font-display text-2xl font-semibold">As camadas de inteligência</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Quatro motores criam o significado. Sem eles, o resto é só renderização.
        </p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {INTELLIGENCE_LAYERS.map((l) => (
            <div key={l.n} className="glass-panel rounded-2xl p-5">
              <span className="font-display text-sm font-semibold text-accent">{l.n}</span>
              <h3 className="mt-1 font-display text-lg font-semibold">{l.name}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{l.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 pb-10 sm:px-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="glass-panel rounded-2xl p-5">
              <span className="flex size-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
                <f.icon className="size-5" />
              </span>
              <h3 className="mt-4 font-display text-lg font-semibold">{f.title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl space-y-6 px-4 pb-24 sm:px-6">
        <CapabilityMatrix
          title="Viral Intelligence Engines"
          subtitle="O core estratégico — análise de significado sobre transcrição real, antes da edição."
          rows={INTELLIGENCE_MATRIX}
        />
        <CapabilityMatrix
          title="Infraestrutura & Render"
          subtitle="Upload, jobs, storage e o render delegado ao worker externo."
        />
      </section>
    </div>
  );
}
