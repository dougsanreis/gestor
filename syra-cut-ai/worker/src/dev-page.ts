/** Página do servidor de teste local (GET /dev). HTML único, sem dependências externas. */
export const DEV_PAGE = /* html */ `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>SYRA · Teste local</title>
<style>
  :root { --bg:#0e0f13; --panel:#171920; --line:#262a35; --text:#eceef4; --muted:#8b91a3; --accent:#ffd400; --ok:#3cff6e; --bad:#ff5b5b; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:15px/1.5 Inter, system-ui, sans-serif; }
  main { max-width:1120px; margin:0 auto; padding:28px 16px 64px; }
  h1 { font-size:22px; margin:0 0 4px; } h1 b { color:var(--accent); }
  .sub { color:var(--muted); margin:0 0 24px; }
  .panel { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:20px; margin-bottom:20px; }
  label { display:block; font-weight:600; margin:14px 0 6px; } label:first-child { margin-top:0; }
  .hint { color:var(--muted); font-weight:400; font-size:13px; }
  input[type=file], input[type=number] { width:100%; padding:10px; background:#0b0c10; color:var(--text); border:1px solid var(--line); border-radius:10px; }
  .row { display:flex; gap:12px; flex-wrap:wrap; }
  .chip { display:flex; align-items:center; gap:8px; margin:0; padding:8px 12px; border:1px solid var(--line); border-radius:999px; cursor:pointer; font-weight:500; }
  button { margin-top:18px; padding:12px 20px; border:0; border-radius:10px; background:var(--accent); color:#111; font-weight:700; font-size:15px; cursor:pointer; }
  button:disabled { opacity:.5; cursor:wait; }
  .bar { height:8px; background:#0b0c10; border-radius:99px; overflow:hidden; margin:10px 0 6px; }
  .bar i { display:block; height:100%; width:0; background:var(--accent); transition:width .4s; }
  .status { font-weight:700; } .status.ok { color:var(--ok); } .status.bad { color:var(--bad); }
  pre { background:#0b0c10; border:1px solid var(--line); border-radius:10px; padding:12px; max-height:260px; overflow:auto; font-size:12px; white-space:pre-wrap; margin:12px 0 0; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:20px; }
  .phone { background:#000; border:1px solid var(--line); border-radius:22px; padding:10px; }
  .phone video { width:100%; aspect-ratio:9/16; border-radius:14px; background:#000; display:block; }
  .phone h3 { margin:10px 4px 2px; font-size:15px; }
  .phone p { margin:0 4px 6px; color:var(--muted); font-size:13px; }
  .phone a { color:var(--accent); margin:0 4px; font-size:13px; }
  .err { color:var(--bad); }
</style>
</head>
<body>
<main>
  <h1><b>SYRA</b> · servidor de teste local</h1>
  <p class="sub">Envie um vídeo, gere os 3 formatos e assista aqui. Nada é publicado; os arquivos ficam na pasta <code>.local-storage</code>.</p>

  <form class="panel" id="form">
    <label>Vídeo <span class="hint">(mp4, mov, webm · com fala)</span></label>
    <input type="file" id="video" accept="video/*" required />
    <label>Legenda .srt/.vtt <span class="hint">(opcional; sem ela o worker usa a transcrição configurada: OpenAI ou STT_COMMAND)</span></label>
    <input type="file" id="subs" accept=".srt,.vtt,text/vtt,application/x-subrip" />
    <label>Formatos</label>
    <div class="row">
      <label class="chip"><input type="checkbox" name="v" value="viral_cut" checked /> Viral Cut</label>
      <label class="chip"><input type="checkbox" name="v" value="clean_caption" checked /> Clean Caption</label>
      <label class="chip"><input type="checkbox" name="v" value="speed_dynamic" checked /> Speed Dynamic</label>
    </div>
    <label>Duração máxima (s)</label>
    <input type="number" id="max" value="60" min="5" max="180" />
    <button id="go">Editar vídeo</button>
    <div class="err" id="formErr"></div>
  </form>

  <section class="panel" id="job" hidden>
    <div><span class="status" id="status">—</span> <span class="hint" id="title"></span></div>
    <div class="bar"><i id="progress"></i></div>
    <pre id="logs"></pre>
  </section>

  <section class="grid" id="results"></section>
</main>
<script>
const $ = (id) => document.getElementById(id);
const LABEL = { viral_cut: "Viral Cut", clean_caption: "Clean Caption", speed_dynamic: "Speed Dynamic 1.1×" };
const DESC = {
  viral_cut: "Gancho no início, jump cuts, punch-in, legenda palavra a palavra, barra de progresso.",
  clean_caption: "Ritmo natural, sem zoom, legenda limpa e pequena.",
  speed_dynamic: "Viral mais rápido (1,1×) e cortes mais secos.",
};
$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("formErr").textContent = "";
  const file = $("video").files[0];
  if (!file) return;
  $("go").disabled = true;
  try {
    const ext = (file.name.split(".").pop() || "mp4").toLowerCase();
    const up = await fetch("/dev/upload?ext=" + encodeURIComponent(ext), { method: "POST", body: file }).then((r) => r.json());
    if (!up.upload) throw new Error(up.error || "upload falhou");
    const subsFile = $("subs").files[0];
    const subtitles = subsFile ? await subsFile.text() : undefined;
    const variants = [...document.querySelectorAll("input[name=v]:checked")].map((i) => i.value);
    const job = await fetch("/dev/jobs", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ upload: up.upload, subtitles, variants, max_duration: Number($("max").value) || 60 }),
    }).then((r) => r.json());
    if (!job.id) throw new Error(job.error || "não foi possível criar o job");
    watch(job.id);
  } catch (err) {
    $("formErr").textContent = err.message;
    $("go").disabled = false;
  }
});
async function watch(id) {
  $("job").hidden = false;
  $("results").innerHTML = "";
  const tick = async () => {
    const j = await fetch("/dev/jobs/" + id).then((r) => r.json());
    $("status").textContent = j.status + (j.error ? " — " + j.error : "");
    $("status").className = "status " + (j.status === "READY" ? "ok" : j.status === "FAILED" ? "bad" : "");
    $("title").textContent = j.title ? "· " + j.title : "";
    $("progress").style.width = (j.progress || 0) + "%";
    $("logs").textContent = (j.logs || []).map((l) => l.replace(/^\\[[^\\]]+\\] /, "")).join("\\n");
    $("logs").scrollTop = 1e9;
    if (j.status === "READY" || j.status === "FAILED") {
      $("go").disabled = false;
      render(j);
      return;
    }
    setTimeout(tick, 1500);
  };
  tick();
}
function render(j) {
  $("results").innerHTML = "";
  for (const v of j.variants) {
    const card = document.createElement("div");
    card.className = "phone";
    if (v.status === "READY") {
      const video = document.createElement("video");
      video.src = v.download_url; video.controls = true; video.playsInline = true; video.preload = "metadata";
      card.append(video);
    }
    const h = document.createElement("h3"); h.textContent = LABEL[v.id] || v.id;
    const p = document.createElement("p");
    p.textContent = v.status === "READY"
      ? DESC[v.id] + " " + (v.duration || 0).toFixed(1) + " s · " + ((v.size || 0) / 1e6).toFixed(1) + " MB"
      : "Falhou: " + (v.error || v.status);
    card.append(h, p);
    if (v.status === "READY") {
      const a = document.createElement("a"); a.href = v.download_url; a.download = v.id + ".mp4"; a.textContent = "Baixar MP4";
      card.append(a);
    }
    $("results").append(card);
  }
  if (j.report_url) {
    const a = document.createElement("a"); a.href = j.report_url; a.textContent = "Relatório do job (JSON)"; a.target = "_blank";
    a.style.color = "var(--accent)";
    $("results").append(a);
  }
}
</script>
</body>
</html>`;
