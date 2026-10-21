"use strict";
/* Gestão de Contratos - Demo (interface) */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const SIT = {
  ATIVA: { rot: "Nossa (ativa)", cor: "var(--verde)" },
  SUSPENSA: { rot: "Nossa (suspensa)", cor: "var(--amarelo)" },
  ENCERRADA: { rot: "Encerrada no Contask", cor: "var(--laranja)" },
  NAO_CLIENTE: { rot: "Não é nossa", cor: "var(--vermelho)" },
  REVISAR: { rot: "Revisar", cor: "var(--roxo)" },
  SEM_IDENTIFICACAO: { rot: "Sem identificação", cor: "var(--cinza)" },
  MODELO: { rot: "Modelo", cor: "var(--azul)" },
  MANTER: { rot: "Mantido (manual)", cor: "var(--primaria)" },
  RESTAURAR: { rot: "Restaurar", cor: "var(--amarelo)" },
  ARQUIVADO: { rot: "Já encerrado", cor: "var(--texto-3)" },
};
const ORDEM_SIT = Object.keys(SIT);

const st = {
  estado: null,
  analise: null,
  empresas: [],
  movs: [],
  aba: "painel",
  filtro: { sit: "", busca: "", pasta: "", acao: "", de: "", ate: "", ocultarEnc: false, empresa: "" },
  ordem: { campo: "situacao", dir: 1 },
  ordemEmp: { campo: "nome", dir: 1 },
  sel: new Set(),
  empFiltro: { busca: "", status: "", tipo: "" },
  gavetaRel: null,
  ultimoGerado: null,
};

/* ------------------------------------------------------------ utilidades */
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function dataBR(iso, comHora = false) {
  if (!iso) return "—";
  const [d, h] = String(iso).split("T");
  const [a, m, dia] = d.split("-");
  if (!dia) return esc(iso);
  return `${dia}/${m}/${a}` + (comHora && h ? ` ${h.slice(0, 5)}` : "");
}
function tamanho(b) {
  if (b == null) return "—";
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(0) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}
function sitTag(s) { return `<span class="tag s-${s}">${esc(SIT[s]?.rot || s)}</span>`; }
function stTag(s) { return s ? `<span class="st st-${esc(s)}">${esc(s)}</span>` : ""; }
function confBarra(c) {
  if (!c) return '<span class="mini">—</span>';
  const cor = c >= 90 ? "var(--verde)" : c >= 75 ? "var(--amarelo)" : "var(--laranja)";
  return `<span class="conf"><i><b style="width:${c}%;background:${cor}"></b></i>${c}</span>`;
}
function norm(s) { return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }

function toast(msg, tipo = "") {
  const t = document.createElement("div");
  t.className = "toast " + tipo;
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), tipo === "erro" ? 8000 : 4500);
}

function nomeUsuario() {
  try { return localStorage.getItem("contratos_usuario") || ""; } catch { return ""; }
}

async function api(rota, opcoes = {}) {
  opcoes.headers = { ...(opcoes.headers || {}), "X-Usuario": encodeURIComponent(nomeUsuario()) };
  const r = await fetch(rota, opcoes);
  let dados = null;
  try { dados = await r.json(); } catch { /* sem corpo */ }
  if (!r.ok) throw new Error(dados?.erro || `Erro ${r.status}`);
  return dados;
}
const post = (rota, corpo) => api(rota, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo || {}) });

/* abre arquivo/pasta: no computador do servidor abre direto; nos outros, abre no navegador
   ou mostra o caminho de rede da pasta para colar no Explorador de Arquivos */
async function abrirItem(rel, pasta = false) {
  try {
    const r = await post("/api/abrir", { rel, pasta });
    if (r.url) window.open(r.url, "_blank");
    else if (r.caminho) {
      try { await navigator.clipboard.writeText(r.caminho); } catch { /* sem permissão de cópia */ }
      await confirmar("Caminho da pasta",
        `<p>Cole este caminho na barra de endereço do <b>Explorador de Arquivos</b> (Windows + E):</p>
         <div class="trecho" style="user-select:all">${esc(r.caminho)}</div>
         <p class="mini">O caminho já foi copiado, se o navegador permitiu.</p>`, "OK");
    }
  } catch (e) { toast(e.message, "erro"); }
}

function perguntarNome() {
  return new Promise(res => {
    $("#mTitulo").textContent = "Quem está usando?";
    $("#mCorpo").innerHTML = `<p>Você está acessando o sistema de outro computador. Informe seu nome — ele fica registrado no histórico de movimentações.</p>
      <input type="text" id="mNome" style="width:100%" maxlength="60" value="${esc(nomeUsuario())}" placeholder="Seu nome">`;
    const ok = $("#mOk");
    ok.textContent = "Entrar"; ok.className = "btn pri";
    $("#mCancelar").style.display = "none";
    const fim = () => {
      const n = $("#mNome").value.trim();
      if (!n) { $("#mNome").focus(); return; }
      try { localStorage.setItem("contratos_usuario", n); } catch { /* navegador sem armazenamento */ }
      $("#modal").classList.remove("on"); $("#mCancelar").style.display = ""; ok.onclick = null; res(n);
    };
    ok.onclick = fim;
    $("#modal").classList.add("on");
    setTimeout(() => { $("#mNome").focus(); $("#mNome").onkeydown = e => { if (e.key === "Enter") fim(); }; }, 50);
  });
}

function confirmar(titulo, html, textoOk = "Confirmar", perigo = false) {
  return new Promise(res => {
    $("#mTitulo").textContent = titulo;
    $("#mCorpo").innerHTML = html;
    const ok = $("#mOk");
    ok.textContent = textoOk;
    ok.className = "btn " + (perigo ? "perigo" : "pri");
    const fim = v => { $("#modal").classList.remove("on"); ok.onclick = null; $("#mCancelar").onclick = null; res(v); };
    ok.onclick = () => fim(true);
    $("#mCancelar").onclick = () => fim(false);
    $("#modal").classList.add("on");
    ok.focus();
  });
}

/* ------------------------------------------------------------ carga */
async function carregarEstado() {
  st.estado = await api("/api/estado");
  const e = st.estado;
  const emp = e.empresas;
  const chipE = $("#chipEmpresas");
  if (emp.total) {
    chipE.innerHTML = `Empresas: <b>${emp.total}</b> · ${esc(emp.fonte?.startsWith("Contask") ? "Contask" : "Planilha")} em ${dataBR(emp.atualizado_em, true)}`;
    chipE.className = "info-chip";
  } else {
    chipE.innerHTML = "Empresas: <b>não carregadas</b>";
    chipE.className = "info-chip alerta";
  }
  const a = e.analise;
  $("#chipAnalise").innerHTML = a.rodando ? "Análise: <b>em andamento…</b>" : `Análise: <b>${dataBR(a.gerado_em, true)}</b>`;
  const prog = $("#progresso"), txt = $("#progressoTexto");
  prog.classList.toggle("on", a.rodando);
  txt.classList.toggle("on", a.rodando);
  $("#btnReanalisar").disabled = a.rodando;
  if (a.rodando) {
    const p = a.progresso;
    const pct = p.total ? Math.round((p.atual / p.total) * 100) : 5;
    $("div", prog).style.width = pct + "%";
    txt.textContent = `${p.mensagem || "Analisando..."} ${p.total ? `(${p.atual} de ${p.total})` : ""}`;
  }
  if (a.erro) toast("Erro na análise: " + a.erro, "erro");
  return e;
}

async function carregarTudo() {
  await carregarEstado();
  const [an, emp, movs] = await Promise.all([api("/api/analise"), api("/api/empresas"), api("/api/movimentacoes")]);
  st.analise = an && an.arquivos ? an : null;
  st.empresas = emp.empresas || [];
  st.movs = movs || [];
  st.ultimoGerado = st.analise?.gerado_em || null;
  const existentes = new Set((st.analise?.arquivos || []).map(a => a.rel));
  st.sel = new Set([...st.sel].filter(r => existentes.has(r)));
  renderTudo();
  carregarModelos();  // histórico de contratos novos (abas Antigos/Novos)
}

let timerPoll = null;
async function acompanhar() {
  clearTimeout(timerPoll);
  const e = await carregarEstado();
  if (e.analise.rodando) {
    timerPoll = setTimeout(acompanhar, 900);
  } else if (e.analise.gerado_em !== st.ultimoGerado) {
    await carregarTudo();
  }
}

async function reanalisar() {
  try {
    await post("/api/analisar");
    toast("Análise iniciada.");
    setTimeout(acompanhar, 300);
  } catch (e) { toast(e.message, "erro"); }
}

/* ------------------------------------------------------------ render */
function renderTudo() {
  renderPainel();
  renderFiltrosContratos();
  renderContratos();
  renderPastas();
  renderEmpresas();
  renderAutentique();
  renderAntigos();
  renderNovos();
  renderAditivos();
  renderCobranca();
  renderMovs();
  renderConfig();
  if (st.gavetaRel) abrirGaveta(st.gavetaRel, true);
}

function irPara(aba) {
  st.aba = aba;
  if (["modelos", "aditivos", "cobranca", "encerramento", "propostas"].includes(aba) && !mod.lista.length) carregarModelos();
  $$(".aba").forEach(b => b.classList.toggle("ativa", b.dataset.aba === aba));
  $$(".secao").forEach(s => s.classList.toggle("ativa", s.id === "sec-" + aba));
  window.scrollTo({ top: 0 });
}

function filtrarContratosPor(f) {
  Object.assign(st.filtro, { sit: "", busca: "", pasta: "", acao: "", de: "", ate: "", ocultarEnc: false, empresa: "" }, f);
  renderFiltrosContratos();
  renderContratos();
  irPara("contratos");
}

/* ---------- painel ---------- */
function renderPainel() {
  const an = st.analise;
  const emp = st.estado?.empresas;
  const aviso = $("#avisoSemEmpresas");
  aviso.innerHTML = !emp?.total
    ? `<div class="aviso atencao"><b>Nenhuma empresa carregada.</b> Vá em <a href="#" data-ir="config">Configurações</a> e conecte ao Contask (ou importe a planilha) para o sistema saber quais empresas são nossas.</div>`
    : emp.fonte && !emp.fonte.startsWith("Contask")
      ? `<div class="aviso info">As empresas vieram de uma <b>planilha</b> (${esc(emp.fonte)}). Se ela só tiver empresas ativas, as encerradas aparecem como “Não é nossa”. Para ver BAIXADA/DISTRATO com datas, <a href="#" data-ir="config">conecte ao Contask</a>.</div>`
      : "";
  if (!an) {
    $("#kpis").innerHTML = `<div class="cartao vazio">${st.estado?.analise?.rodando ? "Analisando as pastas pela primeira vez… isso pode levar alguns minutos." : "Nenhuma análise ainda. Clique em Reanalisar."}</div>`;
    return;
  }
  const r = an.resumo, ps = r.por_situacao || {};
  $("#painelSub").textContent = `Pasta analisada: ${an.pasta_raiz} · ${r.total_arquivos} arquivos em ${r.total_pastas} pastas · análise de ${dataBR(an.gerado_em, true)} (${an.duracao_s}s)`;
  const nossas = (ps.ATIVA || 0) + (ps.SUSPENSA || 0);
  const kpis = [
    { rot: "Arquivos analisados", num: r.total_arquivos, det: `${r.total_pastas} pastas`, cor: "var(--texto-3)", f: {} },
    { rot: "Contratos de empresas nossas", num: nossas, det: `${ps.SUSPENSA || 0} de empresas suspensas`, cor: "var(--verde)", f: { sit: "ATIVA" } },
    { rot: "Sugeridos para mover", num: r.a_mover, det: `${ps.ENCERRADA || 0} encerradas · ${ps.NAO_CLIENTE || 0} não são nossas`, cor: "var(--laranja)", f: { acao: "MOVER" } },
    { rot: "Para revisar", num: r.a_revisar, det: `${ps.REVISAR || 0} incertos · ${ps.SEM_IDENTIFICACAO || 0} sem identificação`, cor: "var(--roxo)", f: { acao: "REVISAR" } },
    { rot: "Modelos / mantidos", num: (ps.MODELO || 0) + (ps.MANTER || 0), det: "não serão movidos", cor: "var(--azul)", f: { acao: "MANTER" } },
    { rot: "Já em Contrato Encerrado", num: (ps.ARQUIVADO || 0) + (ps.RESTAURAR || 0), det: `${r.a_restaurar} deveriam voltar`, cor: "var(--texto-3)", f: { acao: r.a_restaurar ? "RESTAURAR" : "NENHUMA" } },
    { rot: "Empresas nossas (Contask)", num: r.empresas_ativas, det: `de ${r.empresas_total} cadastradas`, cor: "var(--primaria)", ir: "empresas" },
    { rot: "Nossas sem contrato localizado", num: r.ativas_sem_contrato.length, det: "nenhum arquivo nas pastas", cor: "var(--amarelo)", emp: "sem" },
  ];
  $("#kpis").innerHTML = kpis.map((k, i) => `
    <div class="cartao kpi clicavel" data-kpi="${i}" style="--cor:${k.cor}">
      <div class="rot">${k.rot}</div><div class="num">${k.num}</div><div class="det">${esc(k.det)}</div>
    </div>`).join("");
  $$("#kpis [data-kpi]").forEach(el => el.onclick = () => {
    const k = kpis[+el.dataset.kpi];
    if (k.emp) { st.empFiltro.tipo = k.emp; $("#eFiltro").value = k.emp; renderEmpresas(); irPara("empresas"); }
    else if (k.ir) irPara(k.ir);
    else filtrarContratosPor(k.f);
  });

  const total = r.total_arquivos || 1;
  $("#distBarra").innerHTML = ORDEM_SIT.filter(s => ps[s]).map(s =>
    `<span title="${SIT[s].rot}: ${ps[s]}" style="width:${(ps[s] / total) * 100}%;background:${SIT[s].cor}"></span>`).join("");
  $("#distLegenda").innerHTML = ORDEM_SIT.filter(s => ps[s]).map(s =>
    `<button data-sit="${s}"><i style="background:${SIT[s].cor}"></i>${SIT[s].rot} <b>${ps[s]}</b></button>`).join("");
  $$("#distLegenda [data-sit]").forEach(b => b.onclick = () => filtrarContratosPor({ sit: b.dataset.sit }));

  const fonteContask = emp?.fonte?.startsWith("Contask");
  const passos = [
    { ok: fonteContask, t: "Carregar a carteira do Contask", d: fonteContask ? `Sincronizado em ${dataBR(emp.atualizado_em, true)} (${emp.total} empresas)` : "Conecte ao Contask para ter todas as empresas com status e datas.", a: "config" },
    { ok: !r.a_revisar, t: `Revisar ${r.a_revisar} contratos incertos`, d: "Confirme a empresa certa ou marque como modelo / não é nossa.", f: { acao: "REVISAR" } },
    { ok: !r.a_mover, t: `Mover ${r.a_mover} contratos para “${an.pasta_encerrados}”`, d: "Empresas encerradas no Contask ou que não são nossas.", f: { acao: "MOVER" } },
    { ok: !r.a_restaurar, t: `Restaurar ${r.a_restaurar} contratos de empresas que voltaram a ser nossas`, d: "Estão na pasta de encerrados, mas a empresa está ativa.", f: { acao: "RESTAURAR" } },
  ];
  $("#passos").innerHTML = passos.map((p, i) => `
    <li class="${p.ok ? "ok" : "pend"}"><span class="n">${p.ok ? "✓" : i + 1}</span>
      <div class="t">${esc(p.t)}<small>${esc(p.d)}</small></div>
      ${p.ok ? "" : `<button class="btn peq" data-passo="${i}">Abrir</button>`}</li>`).join("");
  $$("#passos [data-passo]").forEach(b => b.onclick = () => {
    const p = passos[+b.dataset.passo];
    p.a ? irPara(p.a) : filtrarContratosPor(p.f);
  });

  const porId = Object.fromEntries(st.empresas.map(e => [e.id, e]));
  const enc = r.encerradas_com_contrato.map(id => porId[id]).filter(Boolean);
  $("#encQtd").textContent = enc.length ? `${enc.length} empresas` : "";
  $("#encLista").innerHTML = enc.length ? `<div class="tabela-wrap" style="max-height:320px;box-shadow:none"><table><thead><tr>
      <th class="sem-ord">Empresa</th><th class="sem-ord">Status</th><th class="sem-ord">Desde</th><th class="sem-ord num">Contratos</th></tr></thead><tbody>
      ${enc.map(e => `<tr data-emp="${esc(e.id)}"><td>${esc(e.nome)}<div class="mini">${esc(e.num ? "Nº " + e.num + " · " : "")}${esc(e.cnpj_fmt || "")}</div></td>
        <td>${stTag(e.status)}</td><td class="data">${dataBR(e.data_status)}</td>
        <td class="num">${an.contratos_por_empresa[e.id]?.ativos || 0}</td></tr>`).join("")}
      </tbody></table></div>`
    : `<p class="mini">${fonteContask ? "Nenhuma — ótimo!" : "Disponível ao conectar o Contask (a planilha não traz empresas encerradas)."}</p>`;
  $$("#encLista [data-emp]").forEach(tr => tr.onclick = () => filtrarContratosPor({ empresa: tr.dataset.emp }));

  const topo = an.pastas.filter(p => p.nivel === 1 && p.arquivos_total);
  $("#pastasResumo").innerHTML = `<div class="tabela-wrap" style="max-height:320px;box-shadow:none"><table><thead><tr>
    <th class="sem-ord">Pasta</th><th class="sem-ord">Modificada</th><th class="sem-ord num">Arquivos</th><th class="sem-ord num">A mover</th></tr></thead><tbody>
    ${topo.map(p => {
      const s = p.situacoes;
      return `<tr data-pasta="${esc(p.rel)}"><td>${esc(p.nome)}</td><td class="data">${dataBR(p.modificada)}</td>
        <td class="num">${p.arquivos_total}</td><td class="num">${(s.ENCERRADA || 0) + (s.NAO_CLIENTE || 0)}</td></tr>`;
    }).join("")}</tbody></table></div>`;
  $$("#pastasResumo [data-pasta]").forEach(tr => tr.onclick = () => filtrarContratosPor({ pasta: tr.dataset.pasta }));
}

/* ---------- contratos ---------- */
function arquivosFiltrados() {
  const an = st.analise;
  if (!an) return [];
  const f = st.filtro;
  const termos = norm(f.busca).split(/\s+/).filter(Boolean);
  const pastaN = f.pasta.toLowerCase();
  let lista = an.arquivos.filter(a => {
    if (f.sit && a.situacao !== f.sit) return false;
    if (f.acao && a.acao !== f.acao) return false;
    if (f.empresa && a.empresa?.id !== f.empresa) return false;
    if (f.ocultarEnc && a.em_encerrados) return false;
    if (pastaN && pastaN !== "(raiz)" && !(a.pasta.toLowerCase() === pastaN || a.pasta.toLowerCase().startsWith(pastaN + "\\"))) return false;
    if (pastaN === "(raiz)" && a.pasta) return false;
    const mod = (a.modificado || "").slice(0, 10);
    if (f.de && mod < f.de) return false;
    if (f.ate && mod > f.ate) return false;
    if (termos.length) {
      const alvo = norm([a.nome, a.pasta, a.empresa?.nome, a.empresa?.fantasia, a.empresa?.num, a.empresa?.cnpj,
        a.contratante, (a.cnpjs_cliente || []).join(" "), (a.cnpjs_cliente || []).join(" ").replace(/\D/g, "")].join(" "));
      if (!termos.every(t => alvo.includes(t))) return false;
    }
    return true;
  });
  const { campo, dir } = st.ordem;
  const chave = {
    situacao: a => ORDEM_SIT.indexOf(a.situacao) * 1000 + (100 - (a.confianca || 0)),
    nome: a => norm(a.nome),
    empresa: a => norm(a.empresa?.nome || "~"),
    confianca: a => a.confianca || 0,
    data_texto: a => a.data_texto || "",
    criado: a => a.criado || "",
    modificado: a => a.modificado || "",
    inicio: a => a.empresa?.inicio_contrato || "",
    status_data: a => a.empresa?.data_status || "",
  }[campo] || (a => a[campo]);
  lista.sort((x, y) => { const a = chave(x), b = chave(y); return (a < b ? -1 : a > b ? 1 : 0) * dir; });
  return lista;
}

function renderFiltrosContratos() {
  const an = st.analise;
  const f = st.filtro;
  const ps = an?.resumo?.por_situacao || {};
  $("#contContratos").textContent = an ? an.resumo.a_mover + an.resumo.a_revisar || "" : "";
  $("#contContratos").className = "cont" + (an && an.resumo.a_mover ? " quente" : "");
  $("#chipsSituacao").innerHTML = `<button class="chip ${f.sit ? "" : "on"}" data-sit="">Todas <span class="q">${an?.resumo.total_arquivos || 0}</span></button>` +
    ORDEM_SIT.filter(s => ps[s]).map(s => `<button class="chip ${f.sit === s ? "on" : ""}" data-sit="${s}">
      <i style="width:8px;height:8px;border-radius:50%;background:${SIT[s].cor};display:inline-block"></i>${SIT[s].rot} <span class="q">${ps[s]}</span></button>`).join("");
  $$("#chipsSituacao [data-sit]").forEach(b => b.onclick = () => { st.filtro.sit = b.dataset.sit; renderFiltrosContratos(); renderContratos(); });
  const pastas = (an?.pastas || []).filter(p => p.rel && p.arquivos_total);
  $("#fPasta").innerHTML = `<option value="">Todas as pastas</option><option value="(raiz)">(arquivos soltos na raiz)</option>` +
    pastas.map(p => `<option value="${esc(p.rel)}">${"  ".repeat(p.nivel - 1)}${esc(p.nome)} (${p.arquivos_total})</option>`).join("");
  $("#fPasta").value = f.pasta;
  $("#fBusca").value = f.busca;
  $("#fAcao").value = f.acao;
  $("#fDataDe").value = f.de;
  $("#fDataAte").value = f.ate;
  $("#fOcultarEnc").checked = f.ocultarEnc;
}

const COLS = [
  { c: "sel", t: "", sem: true },
  { c: "situacao", t: "Situação" },
  { c: "nome", t: "Arquivo / pasta" },
  { c: "empresa", t: "Empresa identificada" },
  { c: "confianca", t: "Confiança", num: true },
  { c: "data_texto", t: "Data no contrato" },
  { c: "criado", t: "Criado" },
  { c: "modificado", t: "Modificado" },
  { c: "inicio", t: "Início (Contask)" },
  { c: "status_data", t: "Data do status" },
];

function renderContratos() {
  const lista = arquivosFiltrados();
  const corpo = $("#corpoContratos");
  const visiveis = new Set(lista.map(a => a.rel));
  const todosSel = lista.length && lista.every(a => st.sel.has(a.rel));
  $("#cabContratos").innerHTML = COLS.map(col => col.c === "sel"
    ? `<th class="sem-ord"><input type="checkbox" id="selTodos" ${todosSel ? "checked" : ""} title="Selecionar todos visíveis"></th>`
    : `<th data-ord="${col.c}" class="${col.num ? "num" : ""}">${col.t} ${st.ordem.campo === col.c ? `<span class="seta">${st.ordem.dir > 0 ? "▲" : "▼"}</span>` : ""}</th>`).join("");
  $("#selTodos").onchange = e => { lista.forEach(a => e.target.checked ? st.sel.add(a.rel) : st.sel.delete(a.rel)); renderContratos(); };
  $$("#cabContratos [data-ord]").forEach(th => th.onclick = () => {
    const c = th.dataset.ord;
    st.ordem = { campo: c, dir: st.ordem.campo === c ? -st.ordem.dir : (["confianca", "criado", "modificado", "data_texto", "inicio", "status_data"].includes(c) ? -1 : 1) };
    renderContratos();
  });
  if (!st.analise) { corpo.innerHTML = `<tr><td colspan="10" class="vazio">Sem análise ainda.</td></tr>`; return; }
  if (!lista.length) { corpo.innerHTML = `<tr><td colspan="10" class="vazio">Nenhum arquivo com esses filtros.</td></tr>`; }
  const LIM = 1500;
  corpo.innerHTML = lista.slice(0, LIM).map(a => {
    const e = a.empresa;
    return `<tr data-rel="${esc(a.rel)}" class="${st.sel.has(a.rel) ? "sel" : ""}">
      <td onclick="event.stopPropagation()"><input type="checkbox" data-sel="${esc(a.rel)}" ${st.sel.has(a.rel) ? "checked" : ""}></td>
      <td>${sitTag(a.situacao)}${a.acao === "MOVER" && a.prova === "nome" ? '<div class="mini" title="Concluído só pelo nome do arquivo">pelo nome</div>' : ""}
        ${(a.autentique || []).length ? `<div style="margin-top:4px" title="Documento(s) no Autentique">${autTag(a.autentique[0].status)}</div>` : ""}</td>
      <td><div class="nome-arq">${esc(a.nome)}</div><div class="caminho">${esc(a.pasta || "(raiz)")}</div></td>
      <td>${e ? `${esc(e.nome)} ${stTag(e.status)}<div class="mini">${e.num ? "Nº " + esc(e.num) + " · " : ""}${esc(e.cnpj_fmt || "")}</div>`
        : a.contratante ? `<span class="mini">Contratante: ${esc(a.contratante)}</span>` : '<span class="mini">—</span>'}</td>
      <td class="num">${confBarra(e ? a.confianca : 0)}</td>
      <td class="data">${dataBR(a.data_texto)}</td>
      <td class="data">${dataBR(a.criado)}</td>
      <td class="data">${dataBR(a.modificado)}</td>
      <td class="data">${dataBR(e?.inicio_contrato)}</td>
      <td class="data">${e && e.status !== "ATIVA" ? dataBR(e.data_status) : "—"}</td>
    </tr>`;
  }).join("");
  const nSelVis = lista.filter(a => st.sel.has(a.rel)).length;
  $("#rodapeContratos").textContent = `${lista.length} arquivos exibidos${lista.length > LIM ? ` (mostrando os primeiros ${LIM})` : ""}` +
    (st.sel.size ? ` · ${st.sel.size} selecionados${st.sel.size !== nSelVis ? ` (${st.sel.size - nSelVis} fora do filtro atual)` : ""}` : "");
  $$("#corpoContratos tr[data-rel]").forEach(tr => tr.onclick = () => abrirGaveta(tr.dataset.rel));
  $$("#corpoContratos [data-sel]").forEach(cb => cb.onchange = () => {
    cb.checked ? st.sel.add(cb.dataset.sel) : st.sel.delete(cb.dataset.sel);
    cb.closest("tr").classList.toggle("sel", cb.checked);
    atualizarBarraLote();
  });
  void visiveis;
  atualizarBarraLote();
}

function atualizarBarraLote() {
  const n = st.sel.size;
  $("#barraLote").classList.toggle("on", n > 0);
  $("#loteQtd").textContent = `${n} selecionado${n === 1 ? "" : "s"}`;
}

function itensSelecionados() {
  const idx = Object.fromEntries((st.analise?.arquivos || []).map(a => [a.rel, a]));
  return [...st.sel].map(r => idx[r]).filter(Boolean);
}

async function moverItens(itens) {
  const enc = st.analise.pasta_encerrados;
  const validos = itens.filter(a => !a.em_encerrados);
  if (!validos.length) return toast("Os arquivos selecionados já estão na pasta de encerrados.");
  const nossos = validos.filter(a => ["ATIVA", "SUSPENSA", "MANTER", "MODELO"].includes(a.situacao));
  const html = `
    <p>Os <b>${validos.length}</b> arquivos abaixo serão movidos para <b>${esc(enc)}</b>, mantendo a mesma estrutura de pastas.
      A operação fica registrada em <i>Movimentações</i> e pode ser desfeita.</p>
    ${nossos.length ? `<div class="aviso ruim"><b>Atenção:</b> ${nossos.length} deles estão marcados como empresa nossa, modelo ou “manter”. Confira antes de confirmar.</div>` : ""}
    <div class="lista-mov">${validos.map(a => `<div>${sitTag(a.situacao)} <b>${esc(a.nome)}</b><br><span class="mini">${esc(a.pasta || "(raiz)")} → ${esc(enc)}\\${esc(a.pasta)}</span>
      ${a.empresa ? `<br><span class="mini">${esc(a.empresa.nome)} — ${esc(a.empresa.status)}</span>` : ""}</div>`).join("")}</div>`;
  if (!(await confirmar("Mover para Contrato Encerrado", html, `Mover ${validos.length} arquivo(s)`, true))) return;
  try {
    const r = await post("/api/mover", { rels: validos.map(a => a.rel) });
    relatarResultados(r.resultados, "movido(s)");
    st.sel.clear();
    fecharGaveta();
    acompanhar();
  } catch (e) { toast(e.message, "erro"); }
}

async function restaurarItens(itens) {
  const validos = itens.filter(a => a.em_encerrados);
  if (!validos.length) return toast("Nenhum dos selecionados está na pasta de encerrados.");
  const html = `<p>Os <b>${validos.length}</b> arquivos voltarão para a pasta original:</p>
    <div class="lista-mov">${validos.map(a => `<div><b>${esc(a.nome)}</b><br><span class="mini">${esc(a.pasta)} → ${esc(a.pasta.split("\\").slice(1).join("\\") || "(raiz)")}</span></div>`).join("")}</div>`;
  if (!(await confirmar("Restaurar contratos", html, `Restaurar ${validos.length}`))) return;
  try {
    const r = await post("/api/restaurar", { rels: validos.map(a => a.rel) });
    relatarResultados(r.resultados, "restaurado(s)");
    st.sel.clear();
    fecharGaveta();
    acompanhar();
  } catch (e) { toast(e.message, "erro"); }
}

function relatarResultados(res, verbo) {
  const ok = res.filter(x => x.ok).length, falhas = res.filter(x => !x.ok);
  if (ok) toast(`${ok} arquivo(s) ${verbo}.`, "ok");
  falhas.slice(0, 5).forEach(f => toast(`${f.rel || f.id}: ${f.erro}`, "erro"));
  if (falhas.length > 5) toast(`… e mais ${falhas.length - 5} erros.`, "erro");
}

async function ajustar(itens, dados) {
  if (!itens.length) return;
  try {
    await post("/api/ajuste", { chaves: itens.map(a => a.chave), ...dados });
    toast(dados.limpar ? "Marcações removidas." : "Marcação salva. Reanalisando…", "ok");
    acompanhar();
  } catch (e) { toast(e.message, "erro"); }
}

/* ---------- gaveta ---------- */
function abrirGaveta(rel, silencioso = false) {
  const a = st.analise?.arquivos.find(x => x.rel === rel);
  if (!a) { if (!silencioso) toast("Arquivo não encontrado na análise atual."); fecharGaveta(); return; }
  st.gavetaRel = rel;
  $("#gTitulo").textContent = a.nome;
  const e = a.empresa;
  const alternativas = (a.alternativas || []).filter(x => x.id !== e?.id && x.pontos >= 40);
  const avisoCls = { ATIVA: "ok", SUSPENSA: "atencao", ENCERRADA: "ruim", NAO_CLIENTE: "ruim", REVISAR: "atencao", RESTAURAR: "atencao" }[a.situacao] || "info";
  const acaoTxt = { MOVER: "Sugestão: mover para Contrato Encerrado", MANTER: "Sugestão: manter onde está", REVISAR: "Sugestão: revisar manualmente", RESTAURAR: "Sugestão: restaurar para a pasta original", NENHUMA: "Nenhuma ação necessária" }[a.acao];
  $("#gCorpo").innerHTML = `
    <div class="aviso ${avisoCls}">${sitTag(a.situacao)} <b>${esc(acaoTxt)}</b><br>${esc(a.motivo)}</div>
    <div class="bloco"><h4>Arquivo</h4><dl class="kv">
      <dt>Pasta</dt><dd>${esc(a.pasta || "(raiz)")}</dd>
      <dt>Tipo / tamanho</dt><dd>${esc(a.ext || "—")} · ${tamanho(a.tamanho)}</dd>
      <dt>Criado em</dt><dd>${dataBR(a.criado, true)}</dd>
      <dt>Modificado em</dt><dd>${dataBR(a.modificado, true)}</dd>
      <dt>Data escrita no contrato</dt><dd>${a.data_texto ? dataBR(a.data_texto) : '<span class="mini">não encontrada</span>'}</dd>
    </dl>
    <div style="display:flex;gap:8px;margin-top:10px"><button class="btn peq" id="gAbrir">Abrir arquivo</button><button class="btn peq" id="gAbrirPasta">Mostrar na pasta</button></div></div>

    <div class="bloco"><h4>Como foi identificado</h4><dl class="kv">
      <dt>Método</dt><dd>${esc(a.metodo || "Nenhuma correspondência na carteira")}</dd>
      ${a.metodo ? `<dt>Confiança</dt><dd>${confBarra(a.confianca)}</dd>
      <dt>Evidência</dt><dd>${esc(a.evidencia || "—")}</dd>` : ""}
      <dt>Contratante (texto)</dt><dd>${esc(a.contratante || "—")}</dd>
      <dt>CNPJ no documento</dt><dd>${esc((a.cnpjs_cliente || []).join(", ") || "—")}</dd>
    </dl>
    ${a.trecho ? `<div class="trecho" style="margin-top:8px">${esc(a.trecho)}…</div>` : ""}
    ${!a.tem_texto && [".doc", ".docx", ".pdf"].includes(a.ext) ? `<p class="mini">Não foi possível ler o texto deste arquivo${a.erro_leitura ? ` (${esc(a.erro_leitura)})` : " (pode ser PDF digitalizado)"}; a identificação usou só o nome.</p>` : ""}
    </div>

    <div class="bloco"><h4>Empresa no Contask</h4>${e ? `<dl class="kv">
      <dt>Razão social</dt><dd><b>${esc(e.nome)}</b>${e.fantasia ? `<br><span class="mini">${esc(e.fantasia)}</span>` : ""}</dd>
      <dt>Nº / CNPJ</dt><dd>${esc(e.num || "—")} · ${esc(e.cnpj_fmt || "—")}</dd>
      <dt>Status</dt><dd>${stTag(e.status)} ${e.data_status ? `desde ${dataBR(e.data_status)}` : ""}</dd>
      <dt>Início do contrato</dt><dd>${dataBR(e.inicio_contrato)}</dd>
      <dt>Regime / UF</dt><dd>${esc(e.regime || "—")} · ${esc(e.uf || "—")}</dd>
      <dt>Responsáveis</dt><dd>Contábil: ${esc(e.resp_contabil || "—")}<br>Fiscal: ${esc(e.resp_fiscal || "—")}<br>DP: ${esc(e.resp_dp || "—")}</dd>
    </dl>` : '<p class="mini">Nenhuma empresa da carteira foi associada a este arquivo.</p>'}</div>

    ${e ? `<div class="bloco"><h4>Autentique</h4>${(a.autentique || []).length
      ? `<div class="alt-lista">${a.autentique.map(d => `<div><span>${esc(d.nome)}<br><span class="mini">Enviado ${dataBR(d.criado_em)}${d.assinado_em ? " · assinado " + dataBR(d.assinado_em) : ""}</span></span>${autTag(d.status)}
          <a class="btn peq" href="https://painel.autentique.com.br/documentos/${encodeURIComponent(d.id)}" target="_blank" rel="noopener">Abrir</a></div>`).join("")}</div>`
      : `<p class="mini">${st.estado?.autentique?.total ? "Nenhum documento desta empresa no Autentique." : "Autentique não sincronizado."}</p>`}</div>` : ""}

    ${alternativas.length ? `<div class="bloco"><h4>Outras possibilidades</h4><div class="alt-lista">
      ${alternativas.map(x => `<div><span>${esc(x.nome)} ${stTag(x.status)}<br><span class="mini">${x.pontos} pts${x.num ? " · Nº " + esc(x.num) : ""}</span></span>
        <button class="btn peq" data-vinc="${esc(x.id)}">Vincular</button></div>`).join("")}</div></div>` : ""}

    <div class="bloco"><h4>Novo modelo de contrato</h4>
      <p class="mini" style="margin-top:0">Gera o contrato desta empresa no modelo atual (Trivium), com os dados já preenchidos.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn peq pri" data-novo="aditivo">📝 Termo aditivo</button>
        <button class="btn peq" data-novo="locacao">🏢 Contrato de aluguel</button>
      </div></div>

    <div class="bloco"><h4>Vincular a uma empresa</h4>
      <div class="busca-emp"><input type="search" id="gBuscaEmp" placeholder="Digite nome, nº ou CNPJ da empresa..."><div class="sugestoes" id="gSug"></div></div>
      <label class="mini" style="display:block;margin-top:10px" for="gObs">Observação (opcional, fica registrada)</label>
      <input type="text" id="gObs" style="width:100%" value="${esc(a.ajuste?.obs || "")}">
      ${a.ajuste ? `<p class="mini">Ajuste manual feito por ${esc(a.ajuste.por || "?")} em ${dataBR(a.ajuste.em, true)}.</p>` : ""}
    </div>`;
  const rod = $("#gRodape");
  rod.innerHTML = `
    ${!a.em_encerrados ? `<button class="btn perigo" id="gMover">→ Mover para Contrato Encerrado</button>` : `<button class="btn pri" id="gRestaurar">← Restaurar</button>`}
    ${!a.em_encerrados ? `<button class="btn" data-marca="MANTER">Manter</button><button class="btn" data-marca="MODELO">É modelo</button><button class="btn" data-marca="NAO_CLIENTE">Não é nossa</button>` : ""}
    ${a.ajuste ? `<button class="btn" id="gLimpar">Desfazer marcação</button>` : ""}`;
  $$("#gCorpo [data-novo]").forEach(b => b.onclick = () => { fecharGaveta(); abrirGerar(b.dataset.novo, { rel: a.rel }); });
  $("#gAbrir").onclick = () => abrirItem(a.rel);
  $("#gAbrirPasta").onclick = () => abrirItem(a.rel, true);
  $("#gMover") && ($("#gMover").onclick = () => moverItens([a]));
  $("#gRestaurar") && ($("#gRestaurar").onclick = () => restaurarItens([a]));
  $("#gLimpar") && ($("#gLimpar").onclick = () => ajustar([a], { limpar: true }));
  $$("#gRodape [data-marca]").forEach(b => b.onclick = () => ajustar([a], { situacao: b.dataset.marca, obs: $("#gObs").value }));
  $$("#gCorpo [data-vinc]").forEach(b => b.onclick = () => ajustar([a], { empresa_id: b.dataset.vinc, obs: $("#gObs").value }));
  const busca = $("#gBuscaEmp"), sug = $("#gSug");
  busca.oninput = () => {
    const t = norm(busca.value).trim();
    const dig = busca.value.replace(/\D/g, "");
    if (t.length < 2) { sug.classList.remove("on"); return; }
    const res = st.empresas.filter(x => norm(x.nome + " " + x.fantasia + " " + x.num).includes(t) || (dig.length >= 4 && (x.cnpj || "").includes(dig))).slice(0, 30);
    sug.innerHTML = res.length ? res.map(x => `<button data-id="${esc(x.id)}">${esc(x.nome)} ${stTag(x.status)}<br><span class="mini">${x.num ? "Nº " + esc(x.num) + " · " : ""}${esc(x.cnpj_fmt || "")}</span></button>`).join("")
      : `<div class="mini" style="padding:8px">Nenhuma empresa encontrada.</div>`;
    sug.classList.add("on");
    $$("button", sug).forEach(b => b.onclick = () => { sug.classList.remove("on"); ajustar([a], { empresa_id: b.dataset.id, obs: $("#gObs").value }); });
  };
  $("#gaveta").classList.add("on");
  $("#gaveta").setAttribute("aria-hidden", "false");
  $("#fundo").classList.add("on");
}
function fecharGaveta() {
  st.gavetaRel = null;
  $("#gaveta").classList.remove("on");
  $("#gaveta").setAttribute("aria-hidden", "true");
  $("#fundo").classList.remove("on");
}

/* ---------- pastas ---------- */
function renderPastas() {
  const an = st.analise;
  const corpo = $("#corpoPastas");
  if (!an) { corpo.innerHTML = `<tr><td colspan="11" class="vazio">Sem análise ainda.</td></tr>`; return; }
  const t = norm($("#pBusca").value);
  const soCom = $("#pSoComArquivos").checked;
  const lista = an.pastas.filter(p => (!soCom || p.arquivos_total) && (!t || norm(p.rel).includes(t)));
  corpo.innerHTML = lista.map(p => {
    const s = p.situacoes || {};
    const nossas = (s.ATIVA || 0) + (s.SUSPENSA || 0);
    const mover = (s.ENCERRADA || 0) + (s.NAO_CLIENTE || 0);
    const rev = (s.REVISAR || 0) + (s.SEM_IDENTIFICACAO || 0);
    return `<tr data-pasta="${esc(p.rel || "(raiz)")}">
      <td style="padding-left:${10 + p.nivel * 18}px"><b>${p.nivel ? "📁 " : "🗄 "}${esc(p.nome)}</b>${p.em_encerrados ? ' <span class="tag s-ARQUIVADO">encerrados</span>' : ""}
        <div class="caminho">${esc(p.rel || an.pasta_raiz)}</div></td>
      <td class="data">${dataBR(p.criada, true)}</td><td class="data">${dataBR(p.modificada, true)}</td>
      <td class="num">${p.arquivos_diretos}${p.arquivos_total !== p.arquivos_diretos ? `<div class="mini">${p.arquivos_total} no total</div>` : ""}</td>
      <td class="data">${dataBR(p.mais_antigo)}</td><td class="data">${dataBR(p.mais_recente)}</td>
      <td class="num">${nossas || ""}</td><td class="num">${mover ? `<b style="color:var(--laranja)">${mover}</b>` : ""}</td><td class="num">${rev || ""}</td>
      <td class="num">${tamanho(p.tamanho)}</td>
      <td><button class="btn peq" data-ver="${esc(p.rel || "(raiz)")}">Ver contratos</button></td></tr>`;
  }).join("") || `<tr><td colspan="11" class="vazio">Nenhuma pasta.</td></tr>`;
  $$("#corpoPastas [data-ver]").forEach(b => b.onclick = ev => { ev.stopPropagation(); filtrarContratosPor({ pasta: b.dataset.ver === "(raiz)" ? "" : b.dataset.ver }); });
  $$("#corpoPastas tr[data-pasta]").forEach(tr => tr.onclick = () => abrirItem(tr.dataset.pasta === "(raiz)" ? "" : tr.dataset.pasta, true));
}

/* ---------- empresas ---------- */
function renderEmpresas() {
  const an = st.analise;
  const por = an?.contratos_por_empresa || {};
  const nossos = new Set(st.estado?.config?.status_nossos || []);
  const f = st.empFiltro;
  const cont = {};
  st.empresas.forEach(e => cont[e.status] = (cont[e.status] || 0) + 1);
  $("#chipsEmpStatus").innerHTML = `<button class="chip ${f.status ? "" : "on"}" data-st="">Todas <span class="q">${st.empresas.length}</span></button>` +
    Object.entries(cont).sort().map(([s, q]) => `<button class="chip ${f.status === s ? "on" : ""}" data-st="${esc(s)}">${esc(s)} <span class="q">${q}</span></button>`).join("");
  $$("#chipsEmpStatus [data-st]").forEach(b => b.onclick = () => { f.status = b.dataset.st; renderEmpresas(); });
  $("#empSub").textContent = st.estado?.empresas?.total
    ? `Fonte: ${st.estado.empresas.fonte} · atualizado em ${dataBR(st.estado.empresas.atualizado_em, true)}`
    : "Nenhuma empresa carregada — use Configurações para conectar ao Contask ou importar a planilha.";
  const t = norm(f.busca).split(/\s+/).filter(Boolean);
  const dig = f.busca.replace(/\D/g, "");
  let lista = st.empresas.filter(e => {
    if (f.status && e.status !== f.status) return false;
    const d = por[e.id] || {};
    const nossa = nossos.has(e.status) && !e.arquivada;
    if (f.tipo === "sem" && (!nossa || d.ativos)) return false;
    if (f.tipo === "com" && !d.qtd && !d.autentique) return false;
    if (f.tipo === "enc" && (nossa || !d.ativos)) return false;
    if (t.length) {
      const alvo = norm([e.nome, e.fantasia, e.num, e.cnpj, e.resp_contabil, e.resp_fiscal, e.resp_dp, e.regime, e.uf].join(" "));
      if (!t.every(x => alvo.includes(x)) && !(dig.length >= 4 && (e.cnpj || "").includes(dig))) return false;
    }
    return true;
  });
  const { campo, dir } = st.ordemEmp;
  const k = {
    num: e => +e.num || 0, nome: e => norm(e.nome), status: e => e.status, inicio: e => e.inicio_contrato || "",
    data_status: e => e.data_status || "", regime: e => e.regime || "", resp: e => norm(e.resp_contabil),
    contratos: e => por[e.id]?.ativos || 0,
  }[campo];
  lista.sort((x, y) => { const a = k(x), b = k(y); return (a < b ? -1 : a > b ? 1 : 0) * dir; });
  const cols = [["num", "Nº"], ["nome", "Razão social / CNPJ"], ["status", "Status"], ["inicio", "Início do contrato"], ["data_status", "Data do status"],
    ["regime", "Regime / UF"], ["resp", "Resp. contábil"], ["contratos", "Contratos localizados"]];
  $("#cabEmpresas").innerHTML = cols.map(([c, tt]) => `<th data-ord="${c}" class="${c === "contratos" || c === "num" ? "num" : ""}">${tt} ${st.ordemEmp.campo === c ? `<span class="seta">${dir > 0 ? "▲" : "▼"}</span>` : ""}</th>`).join("");
  $$("#cabEmpresas [data-ord]").forEach(th => th.onclick = () => {
    const c = th.dataset.ord;
    st.ordemEmp = { campo: c, dir: st.ordemEmp.campo === c ? -st.ordemEmp.dir : 1 };
    renderEmpresas();
  });
  $("#corpoEmpresas").innerHTML = lista.map(e => {
    const d = por[e.id] || {};
    const nossa = nossos.has(e.status) && !e.arquivada;
    const alerta = nossa && !d.ativos ? ' <span class="tag s-SUSPENSA" title="Nenhum contrato localizado nas pastas">sem contrato</span>'
      : !nossa && d.ativos ? ' <span class="tag s-ENCERRADA" title="Ainda há contrato fora da pasta de encerrados">mover</span>' : "";
    return `<tr data-emp="${esc(e.id)}">
      <td class="num">${esc(e.num)}</td>
      <td><b>${esc(e.nome)}</b>${alerta}<div class="mini">${esc(e.cnpj_fmt || "")}${e.fantasia ? " · " + esc(e.fantasia) : ""}</div></td>
      <td>${stTag(e.status)}</td><td class="data">${dataBR(e.inicio_contrato)}</td>
      <td class="data">${dataBR(e.data_status)}</td><td>${esc(e.regime || "—")} <span class="mini">${esc(e.uf || "")}</span></td>
      <td>${esc(e.resp_contabil || "—")}</td>
      <td class="num">${d.qtd ? `${d.ativos} <span class="mini">ativos</span>${d.encerrados ? `<div class="mini">${d.encerrados} em encerrado</div>` : ""}` : '<span class="mini">0</span>'}${d.autentique ? `<div class="mini">${d.autentique} no Autentique</div>` : ""}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="8" class="vazio">Nenhuma empresa com esses filtros.</td></tr>`;
  $("#rodapeEmpresas").textContent = `${lista.length} empresas exibidas`;
  $$("#corpoEmpresas tr[data-emp]").forEach(tr => tr.onclick = () => {
    if (!por[tr.dataset.emp]?.qtd) return toast("Nenhum contrato desta empresa foi localizado nas pastas.");
    filtrarContratosPor({ empresa: tr.dataset.emp });
  });
}

/* ---------- autentique ---------- */
const AUT = {
  ASSINADO: { rot: "Assinado", cls: "s-ATIVA" },
  PARCIAL: { rot: "Assinatura parcial", cls: "s-SUSPENSA" },
  PENDENTE: { rot: "Aguardando assinatura", cls: "s-REVISAR" },
  RECUSADO: { rot: "Recusado", cls: "s-NAO_CLIENTE" },
};
const autTag = s => `<span class="tag ${AUT[s]?.cls || ""}">${esc(AUT[s]?.rot || s)}</span>`;
const autFiltro = { status: "", busca: "", tipo: "" };

function renderAutentique() {
  const info = st.estado?.autentique || {};
  const docs = st.analise?.autentique || [];
  const nossos = new Set(st.estado?.config?.status_nossos || []);
  $("#contAut").textContent = docs.length || "";
  const soNossas = st.estado?.config?.autentique_somente_nossas !== false;
  $("#autSub").textContent = info.total
    ? `Pasta: ${info.pasta_nome || "—"} · ${soNossas ? `${docs.length} documentos de empresas nossas (de ${info.total} no Autentique)` : `${info.total} documentos`} · sincronizado em ${dataBR(info.atualizado_em, true)}`
    : "Contratos enviados para assinatura eletrônica, com status, datas e signatários.";
  $("#autAviso").innerHTML = !info.tem_chave
    ? `<div class="aviso atencao"><b>Autentique não conectado.</b> Em <a href="#" data-ir="config">Configurações</a>, cole a chave de API do Autentique (gerada em painel.autentique.com.br/perfil/api).</div>` : "";
  $("#btnAutSync").disabled = !info.tem_chave;
  const cont = {};
  docs.forEach(d => cont[d.status] = (cont[d.status] || 0) + 1);
  $("#chipsAut").innerHTML = `<button class="chip ${autFiltro.status ? "" : "on"}" data-st="">Todos <span class="q">${docs.length}</span></button>` +
    Object.keys(AUT).filter(s => cont[s]).map(s => `<button class="chip ${autFiltro.status === s ? "on" : ""}" data-st="${s}">${AUT[s].rot} <span class="q">${cont[s]}</span></button>`).join("");
  $$("#chipsAut [data-st]").forEach(b => b.onclick = () => { autFiltro.status = b.dataset.st; renderAutentique(); });
  const t = norm(autFiltro.busca).split(/\s+/).filter(Boolean);
  const lista = docs.filter(d => {
    if (autFiltro.status && d.status !== autFiltro.status) return false;
    const e = d.empresa;
    if (autFiltro.tipo === "sem_local" && d.arquivos_locais.length) return false;
    if (autFiltro.tipo === "enc" && (!e || nossos.has(e.status))) return false;
    if (autFiltro.tipo === "sem_emp" && e) return false;
    if (t.length) {
      const alvo = norm([d.nome, e?.nome, e?.num, ...d.assinaturas.map(s => s.nome + " " + s.email)].join(" "));
      if (!t.every(x => alvo.includes(x))) return false;
    }
    return true;
  }).sort((a, b) => (b.criado_em || "").localeCompare(a.criado_em || ""));
  $("#corpoAut").innerHTML = lista.map(d => {
    const e = d.empresa;
    const certo = e && d.confianca >= (st.estado?.config?.limite_confianca || 80);
    return `<tr>
      <td><div class="nome-arq">${esc(d.nome)}</div></td>
      <td>${e ? `${esc(e.nome)} ${stTag(e.status)}<div class="mini">${e.num ? "Nº " + esc(e.num) + " · " : ""}${certo ? "" : "possível (" + d.confianca + " pts)"}</div>` : `<span class="mini">${d.na_pasta_ativa ? "não está no Contask (tem PDF na pasta)" : "não identificada"}</span>`}</td>
      <td>${autTag(d.status)}<div class="mini">${d.qtd_assinaram}/${d.qtd_signatarios} assinaram</div></td>
      <td class="data">${dataBR(d.criado_em, true)}</td>
      <td class="data">${dataBR(d.assinado_em, true)}</td>
      <td>${d.assinaturas.map(s => `<div class="mini" title="${esc(s.email || "")}">${s.assinado_em ? "✔" : s.recusado_em ? "✖" : s.visto_em ? "👁" : "…"} ${esc(s.nome || s.email || "?")}${s.assinado_em ? " · " + dataBR(s.assinado_em) : ""}</div>`).join("")}</td>
      <td>${d.arquivos_locais.length ? d.arquivos_locais.map(l => `<button class="btn link" data-rel="${esc(l.rel)}" title="${esc(l.rel)}">${esc(l.rel.split("\\").pop())}</button>${l.em_encerrados ? ' <span class="mini">(em Encerrados)</span>' : ""}${l.pelo_nome ? "" : ' <span class="mini">(mesma empresa)</span>'}`).join("<br>") : '<span class="tag s-SUSPENSA">não está na pasta</span>'}</td>
      <td style="white-space:nowrap">
        <a class="btn peq" href="https://painel.autentique.com.br/documentos/${encodeURIComponent(d.id)}" target="_blank" rel="noopener">Abrir no Autentique</a>
        ${(d.url_assinado || d.url_original) ? `<button class="btn peq" data-baixar="${esc(d.id)}" title="Salva o PDF na pasta de contratos">⬇ Salvar na pasta</button>` : ""}
      </td></tr>`;
  }).join("") || `<tr><td colspan="8" class="vazio">${info.total ? "Nenhum documento com esses filtros." : "Nenhum documento sincronizado ainda."}</td></tr>`;
  $("#rodapeAut").textContent = `${lista.length} documentos exibidos`;
  $$("#corpoAut [data-rel]").forEach(b => b.onclick = () => { filtrarContratosPor({}); abrirGaveta(b.dataset.rel); });
  $$("#corpoAut [data-baixar]").forEach(b => b.onclick = async () => {
    const d = docs.find(x => x.id === b.dataset.baixar);
    if (!(await confirmar("Salvar PDF na pasta", `<p>O PDF${d.status === "ASSINADO" ? " assinado" : ""} de <b>${esc(d.nome)}</b> será salvo em <b>${esc(st.estado.config.pasta_raiz)}</b>. Nenhum arquivo existente é substituído.</p>`, "Salvar"))) return;
    try { const r = await post("/api/autentique/baixar", { id: d.id }); toast(`Salvo: ${r.arquivo}`, "ok"); acompanhar(); }
    catch (e) { toast(e.message, "erro"); }
  });
}

async function sincronizarAutentique() {
  const b = $("#btnAutSync");
  b.disabled = true;
  try { const r = await post("/api/autentique/sincronizar"); toast(`${r.total} documentos do Autentique sincronizados.`, "ok"); setTimeout(acompanhar, 300); }
  catch (e) { toast(e.message, "erro"); }
  finally { b.disabled = false; }
}

/* ---------- modelos de contrato ---------- */
const mod = { lista: [], id: null, modo: null, valores: {}, origem: null, empresaId: null, previa: null, ed: null, hist: [] };
const ICONE_MOD = { contabil: "🧾", aditivo: "📝", locacao: "🏢", cobranca: "💰", suspensao: "⛔", notificacao: "⚖️", acordo: "🤝",
  rescisao: "📨", distrato: "📄", prop_auditoria: "🔍", prop_presumido: "📊", prop_diagnostico: "🩺", prop_simples: "📋" };
const ROTULO_MOD = { contabil: "🧾 Contábil", aditivo: "📝 Termo Aditivo", locacao: "🏢 Aluguel",
  cobranca: "💰 Cobrança", suspensao: "⛔ Suspensão", notificacao: "⚖️ Notificação Extrajudicial", acordo: "🤝 Termo de Acordo",
  rescisao: "📨 Notificação de Rescisão", distrato: "📄 Distrato",
  prop_auditoria: "🔍 Auditoria", prop_presumido: "📊 Lucro Presumido mensal", prop_diagnostico: "🩺 Diagnóstico Fiscal",
  prop_simples: "📋 Simples Nacional mensal" };
const COB = ["cobranca", "suspensao", "notificacao", "acordo"];  // sub-aba "Cobrança e acordo"
const ENC = ["rescisao", "distrato"];  // sub-aba "Rescisão / Distrato"
const PROP = ["prop_auditoria", "prop_presumido", "prop_diagnostico", "prop_simples"];  // aba "Propostas"
const ehCob = id => COB.includes(id) || ENC.includes(id);  // modelos da aba "Cobrança / Termos de Acordo"
const ehProp = id => PROP.includes(id);
const ehAvulso = id => ehCob(id) || ehProp(id);  // documentos que não são contratos (têm aba própria)
const ROTULO_AUTO = /^((?:\d+(?:\.\d+)*\.?\s*-\s*)|(?:\d+(?:\.\d+)+\.)|(?:\d+\.\s)|(?:CONTRATADA:|CONTRATANTE:|CL[ÁA]USULA [A-ZÁÉÍÓÚÂÊÔÃÕÇ ]+:|Par[áa]grafo [A-Za-zÁÉÍÓÚáéíóúçã ]+?\s*[-:]))/;

const modeloAtual = () => mod.lista.find(m => m.id === mod.id);
const hojeISO = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

async function carregarModelos() {
  try {
    const [r, h] = await Promise.all([api("/api/modelos"), api("/api/modelos/historico")]);
    mod.lista = r.modelos; mod.hist = h;
    renderCartoesModelos(); renderGerados(); renderAntigos(); renderNovos(); renderAditivos(); renderCobranca(); renderPropostas();
  } catch (e) { toast(e.message, "erro"); }
}

/* Os modelos de contrato (inclusive o Termo Aditivo) ficam em "Modelos de Contrato"; o Termo Aditivo também
   aparece na aba "Termos Aditivos". O formulário abre na aba em que o botão foi clicado.
   Cobrança, suspensão e acordo ficam só na aba "Cobrança / Termos de Acordo". */
const abaDoModelo = id => (mod.editando && ["novos", "aditivos"].includes(st.aba) ? st.aba  // edição abre onde foi clicada
  : ehProp(id) ? "propostas" : ENC.includes(id) ? "encerramento" : ehCob(id) ? "cobranca"
  : id === "aditivo" && st.aba !== "modelos" ? "aditivos" : "modelos");

function colocarPaineis(id) {
  const slot = $({ aditivos: "#slotAditivo", cobranca: "#slotCobranca", encerramento: "#slotEnc", novos: "#slotNovos",
    propostas: "#slotProp" }[abaDoModelo(id)] || "#slotModelos");
  if ($("#painelGerar").parentElement !== slot) slot.append($("#painelGerar"), $("#painelEditar"));
}

function renderCartoesModelos() {
  cartoesEm("#cartoesModelos", mod.lista.filter(m => !ehAvulso(m.id)));
  cartoesEm("#cartoesAditivo", mod.lista.filter(m => m.id === "aditivo"));
  cartoesEm("#cartoesEnc", mod.lista.filter(m => ENC.includes(m.id)));  // mesmo padrão de Modelos de Contrato
  cartoesEm("#cartoesProp", PROP.map(id => mod.lista.find(m => m.id === id)).filter(Boolean));
}

function cartoesEm(sel, lista) {
  $(sel).innerHTML = lista.map(m => `
    <div class="cartao mod-cartao">
      <div style="display:flex;gap:12px;align-items:flex-start">
        <div class="mod-icone">${ICONE_MOD[m.id] || "📄"}</div>
        <div style="flex:1"><h3>${esc(m.nome)}</h3>
          <div class="mini">${esc(m.descricao || "")}</div>
          <div class="mini" style="margin-top:4px">${m.campos.length} campos ·
            ${m.editado ? `editado por ${esc(m.alterado_por || "?")} em ${dataBR(m.alterado_em, true)}`
              : m.id === "aditivo" ? "texto original (Departamento Processual)"
              : ehCob(m.id) ? "texto original (Departamento de Cobrança)"
              : ehProp(m.id) ? "texto original (Propostas 2026)" : "texto original da Trivium"}</div></div>
      </div>
      <div class="acoes">
        <button class="btn pri" data-gerar="${m.id}">${mod.editando ? "📄 Gerar" : textoBtnGerar(m.id)}</button>
        <button class="btn" data-editar="${m.id}">✏️ Editar modelo</button>
      </div>
    </div>`).join("");
  $$(sel + " [data-gerar]").forEach(b => b.onclick = () => abrirGerar(b.dataset.gerar));
  $$(sel + " [data-editar]").forEach(b => b.onclick = () => abrirEditar(b.dataset.editar));
}

function renderGerados() {
  $("#corpoGerados").innerHTML = mod.hist.map(h => `<tr>
    <td class="data">${dataBR(h.data, true)}</td><td>${esc(h.usuario)}</td><td>${esc(h.modelo)}</td>
    <td>${esc(h.empresa || "—")}<div class="mini">${esc(h.cnpj || "")}</div></td>
    <td><button class="btn link" data-abrir="${esc(h.arquivo)}">${esc(h.arquivo)}</button>
      <div>${h.arquivo_pdf ? `<button class="btn peq" data-abrir="${esc(h.arquivo_pdf)}">📕 Abrir PDF</button>` : ""}
        ${h.valores ? `<button class="btn peq" data-pdfh="${esc(h.id)}">⬇ Baixar PDF</button>` : ""}</div></td>
    <td class="mini">${h.substituiu ? `Substituiu: ${esc(h.substituiu)} (movido para Encerrados)<br>` : ""}${h.faltando?.length ? `<span style="color:var(--amarelo)">Faltou: ${esc(h.faltando.join(", "))}</span>` : ""}</td>
  </tr>`).join("") || `<tr><td colspan="6" class="vazio">Nenhum contrato gerado ainda.</td></tr>`;
  $$("#corpoGerados [data-abrir]").forEach(b => b.onclick = () => abrirItem(b.dataset.abrir));
  $$("#corpoGerados [data-pdfh]").forEach(b => b.onclick = () => {
    const h = mod.hist.find(x => x.id === b.dataset.pdfh);
    baixarPdf(h.modelo_id, h.valores, b);
  });
}

/* prévia em HTML do contrato (mesmas regras do .docx) */
function inlinePapel(txt, vals, exemplo) {
  const m = txt.match(ROTULO_AUTO);
  if (m && !txt.startsWith("**")) txt = `**${m[1]}**` + txt.slice(m[0].length);
  return esc(txt)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\{\{(\w+)\}\}/g, (_, k) => {
      const v = vals[k];
      return v ? `<span class="pv-campo">${esc(v)}</span>` : `<span class="pv-falta">________</span>`;
    });
}
function renderPapel(m, texto, vals) {
  const topo = `<div class="pv-topo"><img src="/api/modelos/logo" alt="Alfa">
    <div>${m.mostrar_numero !== false ? `<b>${esc(m.rotulo_numero || "CONTRATO Nº.")} ${esc(vals[m.campo_numero || "NUMERO_CONTRATO"] || "")}</b><br><br>` : ""}Telefone (61) 4000-0000<br>www.alfacontabil.example</div></div>`;
  // assinaturas no fim (o Word/PDF põe sozinho quando o texto não tem [[ASSINATURAS]])
  const assin = () => {
    if (vals.SEM_ASSINATURAS) return "";
    const partes = (m.assinaturas || []).map(([n, p]) => `<div><b>${inlinePapel(n, vals)}</b><br>${esc(p)}</div>`).join("");
    const test = m.testemunhas === false ? "" : "<div>Testemunha 1<br>Nome / CPF</div><div>Testemunha 2<br>Nome / CPF</div>";
    return `<div class="pv-assin" ${m.testemunhas === false && (m.assinaturas || []).length === 1 ? 'style="grid-template-columns:60%;justify-content:center"' : ""}>${partes}${test}</div>`;
  };
  const corpo = texto.trim().split(/\n\s*\n/).map(b => {
    if (b.trim() === "[[PARCELAS]]") b = vals.PARCELAS_TABELA || "(o cronograma de parcelas aparece aqui quando o valor, a quantidade e o 1º vencimento estiverem preenchidos)";
    if (b.trim() === "[[PRECO]]") b = vals.PRECO_TABELA || "(o quadro de horas e preço aparece aqui)";
    if (b.trim().startsWith("?? ")) {  // parágrafo opcional: some se algum campo dele estiver vazio
      b = b.trim().slice(3);
      if ([...b.matchAll(/\{\{(\w+)\}\}/g)].some(x => !vals[x[1]])) return "";
    }
    const linhas = b.split("\n").map(l => l.trim()).filter(Boolean);
    if (linhas.length && linhas.every(l => l.startsWith("|"))) {  // quadro: | célula | célula |
      const largo = Math.max(...linhas.map(l => l.replace(/^\||\|$/g, "").split("|").length)) >= 4;
      return `<table class="quadro${largo ? " largo" : ""}">${linhas.map(l => `<tr>${l.replace(/^\||\|$/g, "").split("|")
        .map((c, i) => `<td class="${i ? "c" : ""}">${inlinePapel(c.trim(), vals)}</td>`).join("")}</tr>`).join("")}</table>`;
    }
    b = linhas.join(" ").trim();
    if (!b) return "";
    if (b === "[[ASSINATURAS]]") return assin();
    if (b.startsWith(">> ")) return `<p class="dir">${inlinePapel(b.slice(3), vals)}</p>`;
    if (b.startsWith("# ")) return `<h1>${inlinePapel(b.slice(2), vals)}</h1>`;
    if (b.startsWith("## ")) return `<h2>${inlinePapel(b.slice(3), vals)}</h2>`;
    return `<p>${inlinePapel(b, vals)}</p>`;
  }).join("");
  return topo + corpo + (texto.includes("[[ASSINATURAS]]") ? "" : assin());
}

/* ----- gerar ----- */
/* valores: dados de um documento anterior (ex.: a cobrança ao abrir a suspensão do mesmo cliente) */
async function abrirGerar(id, { rel = null, empresaId = null, valores = null, editar = null } = {}) {
  if (!mod.lista.length) await carregarModelos();
  mod.id = id; mod.modo = "gerar"; mod.origem = null; mod.empresaId = empresaId; mod.valores = {};
  mod.editando = editar || null;
  const aba = abaDoModelo(id);
  colocarPaineis(id);
  irPara(aba);
  $("#painelEditar").style.display = "none";
  $("#painelGerar").style.display = "";
  const m = modeloAtual();
  $("#gerTitulo").textContent = editar ? `Editar contrato: ${editar.empresa || ""}` : "Gerar: " + m.nome;
  $("#btnGerar").textContent = textoBtnGerar(id);
  if (!editar) {  // na edição os dados vêm só do contrato salvo (nada de Contask ou Receita por cima)
    try {
      const q = new URLSearchParams({ id });
      if (rel) q.set("rel", rel);
      if (empresaId) q.set("empresa_id", empresaId);
      const s = await api("/api/modelos/sugestao?" + q);
      mod.valores = s.valores || {};
      mod.origem = s.origem;
      if (s.empresa) mod.empresaId = s.empresa.id;
    } catch (e) { toast(e.message, "erro"); }
  }
  if (valores) {
    const campos = new Set(m.campos.map(c => c.chave));
    Object.entries(valores).forEach(([k, v]) => {
      if (!campos.has(k) || !v || (k === "DATA_ASSINATURA" && !editar)) return;  // documento novo: data de hoje
      const c = m.campos.find(x => x.chave === k);
      mod.valores[k] = c.tipo === "numero" ? (String(v).match(/\d+/) || [""])[0]  // "03 (três)" -> "03"
        : c.tipo === "data_extenso" ? extensoParaISO(v) : v;
    });
    if (editar && valores.SEM_ASSINATURAS) mod.valores.SEM_ASSINATURAS = "1";
    // "A/C" das notificações <-> representante legal do distrato/acordo
    if (campos.has("REPRESENTANTE") && !mod.valores.REPRESENTANTE && valores.AOS_CUIDADOS) mod.valores.REPRESENTANTE = valores.AOS_CUIDADOS;
    if (campos.has("AOS_CUIDADOS") && !mod.valores.AOS_CUIDADOS && valores.REPRESENTANTE) mod.valores.AOS_CUIDADOS = valores.REPRESENTANTE;
    // acordo aberto a partir da cobrança/suspensão: o débito se refere às mensalidades cobradas
    if (campos.has("PERIODO_DEBITO") && valores.VENCIMENTOS && !valores.PERIODO_DEBITO)
      mod.valores.PERIODO_DEBITO = "honorários contábeis com vencimento em " + valores.VENCIMENTOS;
    if (campos.has("DATA_ATUALIZACAO") && !mod.valores.DATA_ATUALIZACAO) mod.valores.DATA_ATUALIZACAO = hojeISO();
  }
  m.campos.forEach(c => { if (c.tipo === "data_extenso" && !mod.valores[c.chave]) mod.valores[c.chave] = hojeISO(); });
  mod.cnpjStatus = ""; mod.mover = false;
  renderFormGerar();
  atualizarPrevia();
  if (!editar && (mod.valores.CNPJ || "").replace(/\D/g, "").length === 14) buscarCnpj(false);  // nome completo + endereço
  $("#painelGerar").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* abre um contrato já gerado para alterar: salvar regrava o mesmo Word/PDF */
function editarGerado(h) {
  if (!h?.valores) return toast("Este contrato foi gerado sem os dados salvos; não dá para editar por aqui.", "erro");
  abrirGerar(h.modelo_id, { empresaId: h.empresa_id || null, valores: h.valores, editar: h });
}

/* "09 de outubro de 2026" -> "2026-10-09" (campo de data do formulário) */
function extensoParaISO(v) {
  const m = String(v || "").match(/^(\d{1,2}) de ([a-zç]+) de (\d{4})$/i);
  const mes = m ? ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
    "novembro", "dezembro"].indexOf(m[2].toLowerCase()) + 1 : 0;
  return mes ? `${m[3]}-${String(mes).padStart(2, "0")}-${m[1].padStart(2, "0")}` : v;
}

const textoBtnGerar = id => mod.editando ? "💾 Salvar alterações" : ehProp(id) ? "📄 Gerar proposta" : ({ aditivo: "📝 Gerar termo aditivo", cobranca: "💰 Gerar notificação de débito",
  suspensao: "⛔ Gerar notificação de suspensão", notificacao: "⚖️ Gerar notificação extrajudicial", acordo: "🤝 Gerar termo de acordo",
  rescisao: "📨 Gerar notificação de rescisão", distrato: "📄 Gerar distrato" }[id] || "📄 Gerar contrato");

function renderFormGerar() {
  const m = modeloAtual();
  const o = mod.origem, ed = mod.editando;
  $("#gerOrigem").innerHTML = ed ? `<div class="aviso info">
      Alterando o contrato gerado em <b>${dataBR(ed.data, true)}</b> por ${esc(ed.usuario || "")}.<br>
      <span class="mini">Ao salvar, o mesmo arquivo Word${ed.arquivo_pdf ? " e o PDF" : ""} são regravados com as alterações.
      A versão anterior fica guardada em <b>dados\\versoes_contratos</b>.</span></div>`
    : o ? `<div class="aviso atencao">
      Novo contrato para substituir: <b>${esc(o.nome)}</b><br><span class="mini">${esc(o.pasta || "(pasta principal)")}</span>
      <label class="check" style="margin-top:6px"><input type="checkbox" id="gerMover" ${mod.mover ? "checked" : ""} onchange="mod.mover = this.checked"> <span>Mover o contrato antigo para <b>${esc(st.analise?.pasta_encerrados || "Contratos Encerrados")}</b></span></label>
    </div>` : "";
  $("#gerCampos").innerHTML = m.campos.map(c => {
    const v = mod.valores[c.chave] || "";
    const tipo = c.tipo === "data" || c.tipo === "data_extenso" ? "date" : c.tipo === "numero" ? "number" : "text";
    const valInput = tipo === "date" ? paraISO(v) : tipo === "number" ? (String(v).match(/\d+/) || [""])[0] : v;
    const extra = c.chave === "CNPJ"
      ? `<div style="display:flex;gap:6px;align-items:center;margin-top:4px">
           <button type="button" class="btn peq" id="btnBuscarCnpj">🔎 Buscar na Receita</button>
           <span class="mini" id="cnpjStatus">${esc(mod.cnpjStatus || "Preenche nome completo, endereço e sócio-administrador.")}</span></div>`
      : c.chave === "NUMERO_CONTRATO" ? '<span class="auto">vem do Nº da empresa no Contask</span>' : "";
    const longo = ["ENDERECO", "RAZAO_SOCIAL", "VENCIMENTOS", "PERIODO_DEBITO"].includes(c.chave);
    return `<div class="campo"><label for="gc_${c.chave}">${esc(c.rotulo)} ${c.obrigatorio ? '<span class="obr">*</span>' : ""}
        ${c.chave === "VALOR_PARCELA" ? '<span class="auto">(vazio = divide o restante em parcelas iguais)</span>'
          : c.tipo === "dinheiro" ? '<span class="auto">(o valor por extenso é automático)</span>'
          : c.tipo === "numero" ? '<span class="auto">(sai como “03 (três)”)</span>' : ""}</label>
      ${longo ? `<textarea id="gc_${c.chave}" data-campo="${c.chave}" rows="2" style="min-height:56px" placeholder="${esc(c.padrao || "")}">${esc(valInput)}</textarea>`
              : `<input type="${tipo}" id="gc_${c.chave}" data-campo="${c.chave}" value="${esc(valInput)}" placeholder="${esc(c.padrao || "")}"${tipo === "number" ? ' min="1" step="1"' : ""}>`}
      ${extra}</div>`;
  }).join("");
  $$("#gerCampos [data-campo]").forEach(i => i.oninput = () => {
    mod.valores[i.dataset.campo] = i.value; atualizarPreviaDepois();
    if (i.dataset.campo === "CNPJ") empresaPorCnpjDigitado();
  });
  $("#gerSemAssin").checked = !!mod.valores.SEM_ASSINATURAS;
  $("#gerSemAssin").onchange = ev => { mod.valores.SEM_ASSINATURAS = ev.target.checked ? "1" : ""; atualizarPrevia(); };
  const bc = $("#btnBuscarCnpj");
  if (bc) {
    bc.onclick = () => buscarCnpj(true);
    $("#gc_CNPJ").onblur = () => {
      if ((mod.valores.CNPJ || "").replace(/\D/g, "").length !== 14) return;
      if (empresaPorCnpjDigitado()) return;  // achou no Contask: já completa tudo (inclusive Receita)
      if (!mod.valores.ENDERECO) buscarCnpj(false);
    };
  }
}

/* CNPJ digitado no formulário -> empresa da carteira do Contask (se for outra que a atual, carrega os dados dela) */
function empresaPorCnpjDigitado() {
  const c = (mod.valores.CNPJ || "").replace(/\D/g, "");
  if (c.length !== 14 || mod.editando) return false;
  const e = st.empresas.find(x => String(x.cnpj || "").replace(/\D/g, "") === c);
  if (!e) return false;
  if (String(e.id) !== String(mod.empresaId)) escolherEmpresaGerar(e.id);
  return true;
}

/* escolhe a empresa do Contask no formulário de geração */
async function escolherEmpresaGerar(empresaId) {
  try {
    const s = await api("/api/modelos/sugestao?" + new URLSearchParams({ id: mod.id, empresa_id: empresaId }));
    mod.empresaId = empresaId;
    // empresa trocada: mantém só as datas digitadas; o resto vem da nova empresa (Contask, dados guardados e Receita)
    mod.valores = { DATA_INICIO: mod.valores.DATA_INICIO, DATA_ASSINATURA: mod.valores.DATA_ASSINATURA, ...s.valores };
    mod.cnpjStatus = "";
    renderFormGerar(); atualizarPrevia();
    buscarCnpj(false);
  } catch (e) { toast(e.message, "erro"); }
}

/* consulta o CNPJ na Receita (via servidor) e completa o formulário.
   sobrescrever=true (botão): troca razão social, endereço e representante pelos da Receita.
   sobrescrever=false (automático): troca a razão social (nome completo) e só preenche o que está vazio. */
async function buscarCnpj(sobrescrever) {
  const c = (mod.valores.CNPJ || "").replace(/\D/g, "");
  if (c.length !== 14) { if (sobrescrever) toast("Informe o CNPJ completo (14 números).", "erro"); return; }
  const st_ = $("#cnpjStatus"), b = $("#btnBuscarCnpj");
  if (st_) st_.textContent = "Consultando a Receita…";
  if (b) b.disabled = true;
  try {
    const r = await api("/api/cnpj?cnpj=" + c);
    const campos = new Set(modeloAtual().campos.map(x => x.chave));
    if (r.razao_social && campos.has("RAZAO_SOCIAL")) mod.valores.RAZAO_SOCIAL = r.razao_social;
    if (r.endereco && campos.has("ENDERECO") && (sobrescrever || !mod.valores.ENDERECO)) mod.valores.ENDERECO = r.endereco;
    if (r.socio_administrador && campos.has("REPRESENTANTE") && (sobrescrever || !mod.valores.REPRESENTANTE)) mod.valores.REPRESENTANTE = r.socio_administrador;
    mod.cnpjStatus = `✔ Dados da Receita Federal (${r.fonte}, ${dataBR(r.consultado_em)})${r.fantasia ? " · fantasia: " + r.fantasia : ""}`;
    renderFormGerar();
    atualizarPrevia();
  } catch (e) {
    mod.cnpjStatus = "Não foi possível consultar agora — preencha à mão.";
    if (st_) st_.textContent = mod.cnpjStatus;
    if (sobrescrever) toast(e.message, "erro");
  } finally { if ($("#btnBuscarCnpj")) $("#btnBuscarCnpj").disabled = false; }
}

function paraISO(v) {
  const m = String(v || "").match(/^(\d{2})[./](\d{2})[./](\d{4})$/);
  return m ? `${m[3]}-${m[2]}-${m[1]}` : v;
}

let tPrevia;
function atualizarPreviaDepois() { clearTimeout(tPrevia); tPrevia = setTimeout(atualizarPrevia, 250); }
async function atualizarPrevia() {
  const m = modeloAtual();
  try {
    const r = await post("/api/modelos/previa", { id: m.id, valores: mod.valores });
    mod.previa = r;
    $("#gerPrevia").innerHTML = renderPapel(m, m.texto, r.valores);
    const v = r.valores;
    // termo de acordo: resumo das contas para conferir antes de gerar
    const resumo = m.id === "acordo" && v.PARCELAS_TABELA
      ? `<div class="aviso ok" style="margin-top:12px"><b>Conferência do acordo</b><br>
          Débito: <b>R$ ${esc(v.VALOR_DEBITO)}</b>${v.VALOR_ENTRADA ? ` · Entrada: <b>R$ ${esc(v.VALOR_ENTRADA)}</b>` : ""}
          · ${esc((v.QTD_PARCELAS || "").replace(/\s*\(.*\)/, ""))} parcela(s) de <b>R$ ${esc(v.VALOR_PARCELA)}</b>
          <div class="mini" style="margin-top:4px">${esc(v.FORMA_PAGAMENTO)}.</div></div>`
      : m.id === "acordo" && v.VALOR_DEBITO && v.QTD_PARCELAS
        ? `<div class="aviso ruim" style="margin-top:12px">Não foi possível montar as parcelas: confira se a entrada é menor que o débito.</div>` : "";
    $("#gerFaltando").innerHTML = resumo + (r.faltando.length
      ? `<div class="aviso atencao" style="margin-top:12px">Faltam: <b>${esc(r.faltando.join(", "))}</b>. Se gerar assim, esses pontos saem em amarelo no Word para completar depois.</div>` : "");
    const cfgP = st.estado?.config || {};
    const pastaDestino = ehCob(m.id) ? "Cobranças e Acordos" : ehProp(m.id) ? "Propostas" : cfgP.pasta_novos_contratos;
    $("#gerNomeArq").innerHTML = mod.editando
      ? `Arquivo que será regravado: <b>${esc(mod.editando.arquivo)}</b>`
      : `Arquivo: <b>${esc(r.nome_arquivo)}</b> — salvo em <b>${esc(cfgP.pasta_raiz || "")}${pastaDestino ? "\\" + esc(pastaDestino) : ""}</b>`;
  } catch (e) { toast(e.message, "erro"); }
}

async function baixarPdf(id, valores, botao) {
  const texto = botao?.textContent;
  if (botao) { botao.disabled = true; botao.textContent = "Gerando PDF…"; }
  try {
    const r = await fetch("/api/modelos/pdf", { method: "POST",
      headers: { "Content-Type": "application/json", "X-Usuario": encodeURIComponent(nomeUsuario()) },
      body: JSON.stringify({ id, valores }) });
    if (!r.ok) { let m = `Erro ${r.status}`; try { m = (await r.json()).erro || m; } catch { /* sem corpo */ } throw new Error(m); }
    const blob = await r.blob();
    const nome = decodeURIComponent((r.headers.get("Content-Disposition") || "").split("''")[1] || "contrato.pdf");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = nome;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    toast(`PDF baixado: ${nome}`, "ok");
  } catch (e) { toast(e.message, "erro"); }
  finally { if (botao) { botao.disabled = false; botao.textContent = texto; } }
}

async function gerarContrato() {
  if (mod.editando) return salvarEdicao();
  const m = modeloAtual();
  await atualizarPrevia();
  const falt = mod.previa?.faltando || [];
  const mover = $("#gerMover")?.checked;
  const html = `<p>Será criado o arquivo <b>${esc(mod.previa?.nome_arquivo || "")}</b> no modelo <b>${esc(m.nome)}</b>.</p>
    ${falt.length ? `<div class="aviso atencao">Campos em branco: <b>${esc(falt.join(", "))}</b> — sairão em amarelo no documento.</div>` : ""}
    ${mover ? `<div class="aviso ruim">O contrato antigo <b>${esc(mod.origem.nome)}</b> será movido para Contratos Encerrados (pode ser desfeito em Movimentações).</div>` : ""}`;
  const cob = ehCob(m.id), prop = ehProp(m.id);
  if (!(await confirmar(prop ? "Gerar proposta" : cob ? "Gerar documento" : "Gerar contrato", html, "Gerar"))) return;
  try {
    const b = $("#btnGerar"); b.disabled = true; b.textContent = "Gerando…";
    let r;
    try {
      r = await post("/api/modelos/gerar", { id: m.id, valores: mod.valores, empresa_id: mod.empresaId,
        origem_rel: mod.origem?.rel || null, mover_antigo: !!mover, com_pdf: $("#gerComPdf").checked });
    } finally { b.disabled = false; b.textContent = textoBtnGerar(m.id); }
    if (r.movido && !r.movido.ok) toast("Contrato gerado, mas o antigo não foi movido: " + r.movido.erro, "erro");
    if (r.erro_pdf) toast("O Word foi gerado, mas o PDF não: " + r.erro_pdf, "erro");
    $("#mTitulo").textContent = prop ? "Proposta gerada ✔" : cob ? "Documento gerado ✔" : "Contrato gerado ✔";
    $("#mCorpo").innerHTML = `<p>Arquivos criados na pasta ${prop ? "<b>Propostas</b>" : cob ? "<b>Cobranças e Acordos</b>" : "de contratos"}:</p>
      <div class="trecho">${esc(r.arquivo)}${r.arquivo_pdf ? "<br>" + esc(r.arquivo_pdf) : ""}</div>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
        <button class="btn" id="mAbrirDocx">Abrir no Word</button>
        ${r.arquivo_pdf ? '<button class="btn" id="mAbrirPdf">Abrir PDF</button>' : ""}</div>
      <p class="mini">${["cobranca", "suspensao", "notificacao", "rescisao"].includes(m.id)
        ? "Envie o PDF ao cliente por e-mail (com confirmação de leitura) ou entregue impresso com protocolo de recebimento."
        : prop ? "Envie o PDF ao cliente. Com o aceite, gere o contrato em Modelos de Contrato."
        : "Para assinar eletronicamente, envie o PDF pelo Autentique."}</p>`;
    $("#mOk").textContent = "OK"; $("#mOk").className = "btn pri"; $("#mCancelar").style.display = "none";
    $("#mOk").onclick = () => { $("#modal").classList.remove("on"); $("#mCancelar").style.display = ""; };
    $("#mAbrirDocx").onclick = () => abrirItem(r.arquivo);
    if (r.arquivo_pdf) $("#mAbrirPdf").onclick = () => abrirItem(r.arquivo_pdf);
    $("#modal").classList.add("on");
    carregarModelos();
    acompanhar();
  } catch (e) { toast(e.message, "erro"); }
}

/* salva a edição de um contrato já gerado (regrava o mesmo Word/PDF) */
async function salvarEdicao() {
  const ed = mod.editando;
  await atualizarPrevia();
  const falt = mod.previa?.faltando || [];
  const porRel = Object.fromEntries((st.analise?.arquivos || []).map(a => [a.rel, a]));
  const aut = (porRel[ed.arquivo]?.autentique || porRel[ed.arquivo_pdf]?.autentique || [])[0];
  const html = `<p>O contrato <b>${esc(ed.arquivo)}</b> será regravado com as alterações${ed.arquivo_pdf ? " (Word e PDF)" : ""}.</p>
    <p class="mini">A versão anterior fica guardada em dados\\versoes_contratos.</p>
    ${falt.length ? `<div class="aviso atencao">Campos em branco: <b>${esc(falt.join(", "))}</b> — sairão em amarelo no documento.</div>` : ""}
    ${aut ? `<div class="aviso ruim">Este contrato já foi enviado ao Autentique (${esc(aut.status || "")}). A alteração vale só para o arquivo da pasta;
      o documento no Autentique continua como estava — se precisar, envie de novo.</div>` : ""}`;
  if (!(await confirmar("Salvar alterações no contrato", html, "Salvar alterações"))) return;
  const b = $("#btnGerar"); b.disabled = true; b.textContent = "Salvando…";
  try {
    const r = await post("/api/modelos/editar", { hist_id: ed.id, valores: mod.valores, com_pdf: $("#gerComPdf").checked });
    if (r.erro_pdf) toast("O Word foi salvo, mas o PDF não: " + r.erro_pdf, "erro");
    toast("Contrato alterado ✔ " + r.arquivo, "ok");
    mod.editando = null;
    $("#painelGerar").style.display = "none";
    await carregarModelos();
    acompanhar();
  } catch (e) { toast(e.message, "erro"); }
  finally { b.disabled = false; b.textContent = textoBtnGerar(mod.id); }
}

/* ----- editar ----- */
function abrirEditar(id) {
  mod.id = id; mod.modo = "editar";
  const m = modeloAtual();
  mod.ed = { texto: m.texto, campos: JSON.parse(JSON.stringify(m.campos)) };
  const aba = abaDoModelo(id);
  colocarPaineis(id);
  irPara(aba);
  $("#painelGerar").style.display = "none";
  $("#painelEditar").style.display = "";
  $("#edTitulo").textContent = "Editar: " + m.nome;
  $("#edTexto").value = mod.ed.texto;
  renderEdCampos();
  previaEdicao();
  $("#painelEditar").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderEdCampos() {
  const TIPOS = [["", "Texto"], ["dinheiro", "Dinheiro (R$)"], ["data", "Data (dd.mm.aaaa)"], ["data_extenso", "Data por extenso"],
    ["numero", "Número (03 (três))"]];
  $("#edCampos").innerHTML = mod.ed.campos.map((c, i) => `<tr>
    <td><input data-i="${i}" data-k="chave" value="${esc(c.chave)}"></td>
    <td><input data-i="${i}" data-k="rotulo" value="${esc(c.rotulo)}"></td>
    <td><input data-i="${i}" data-k="padrao" value="${esc(c.padrao || "")}"></td>
    <td><select data-i="${i}" data-k="tipo">${TIPOS.map(([v, t]) => `<option value="${v}" ${(c.tipo || "") === v ? "selected" : ""}>${t}</option>`).join("")}</select></td>
    <td><input type="checkbox" data-i="${i}" data-k="obrigatorio" ${c.obrigatorio ? "checked" : ""} style="width:auto"></td>
    <td><button class="btn peq" data-rem="${i}" title="Remover campo">✕</button></td></tr>`).join("");
  $$("#edCampos [data-k]").forEach(el => el.oninput = el.onchange = () => {
    const c = mod.ed.campos[+el.dataset.i];
    if (el.dataset.k === "obrigatorio") c.obrigatorio = el.checked;
    else if (el.dataset.k === "chave") { el.value = el.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_"); c.chave = el.value; renderEdChips(); }
    else c[el.dataset.k] = el.value;
    previaEdicao();
  });
  $$("#edCampos [data-rem]").forEach(b => b.onclick = () => { mod.ed.campos.splice(+b.dataset.rem, 1); renderEdCampos(); previaEdicao(); });
  renderEdChips();
}

function renderEdChips() {
  const chaves = [...new Set([...mod.ed.campos.map(c => c.chave), "VALOR_EXTENSO",
    ...mod.ed.campos.filter(c => c.tipo === "dinheiro").map(c => c.chave + "_EXTENSO"),
    ...(mod.ed.campos.some(c => c.chave === "QTD_PARCELAS") ? ["FORMA_PAGAMENTO"] : [])])];
  $("#edChips").innerHTML = chaves.map(k => `<button class="chip" data-ins="${esc(k)}" title="Inserir {{${esc(k)}}}">${esc(k)}</button>`).join(" ");
  $$("#edChips [data-ins]").forEach(b => b.onclick = () => inserirNoTexto(`{{${b.dataset.ins}}}`));
}

function inserirNoTexto(trecho, envolver = false) {
  const ta = $("#edTexto");
  const [i, f] = [ta.selectionStart, ta.selectionEnd];
  const sel = ta.value.slice(i, f);
  const novo = envolver ? `**${sel || "texto"}**` : trecho;
  ta.setRangeText(novo, i, f, "end");
  ta.focus();
  mod.ed.texto = ta.value;
  previaEdicao();
}

let tEd;
function previaEdicao() {
  clearTimeout(tEd);
  tEd = setTimeout(() => {
    const m = { ...modeloAtual(), campos: mod.ed.campos };
    const ex = {};
    mod.ed.campos.forEach(c => ex[c.chave] = c.padrao || `[${c.rotulo}]`);
    ex.VALOR_EXTENSO = "[valor por extenso]";
    mod.ed.campos.filter(c => c.tipo === "dinheiro").forEach(c => ex[c.chave + "_EXTENSO"] = `[${c.rotulo} por extenso]`);
    ex.FORMA_PAGAMENTO = "[forma de pagamento: entrada, parcelas e vencimentos]";
    ex.PARCELAS_TABELA = "| **Parcela** | **Vencimento** | **Valor** |\n| 1ª parcela | [data] | R$ [valor] |";
    $("#edPrevia").innerHTML = renderPapel(m, $("#edTexto").value, ex);
  }, 200);
}

async function salvarModelo() {
  mod.ed.texto = $("#edTexto").value;
  const vazios = mod.ed.campos.filter(c => !c.chave || !c.rotulo);
  if (vazios.length) return toast("Todo campo precisa de código e nome.", "erro");
  try {
    await post("/api/modelos/salvar", { id: mod.id, texto: mod.ed.texto, campos: mod.ed.campos });
    toast("Modelo salvo. Os próximos contratos já saem com o texto novo.", "ok");
    await carregarModelos();
    $("#painelEditar").style.display = "none";
  } catch (e) { toast(e.message, "erro"); }
}

/* ----- lote (selecionados na aba Contratos) ----- */
async function gerarLote(itens, idPadrao = "contabil") {
  if (!itens.length) return;
  if (!mod.lista.length) await carregarModelos();
  const html = `<p>Gerar contratos novos para os <b>${itens.length}</b> arquivos selecionados.</p>
    <div class="form-grade" style="margin:10px 0">
      <label for="loteModelo">Modelo</label>
      <select id="loteModelo">${mod.lista.filter(m => !ehAvulso(m.id)).map(m => `<option value="${m.id}" ${m.id === idPadrao ? "selected" : ""}>${esc(m.nome)}</option>`).join("")}</select>
      <label for="loteInicio">Início da vigência (todos)</label><input type="date" id="loteInicio">
      <label for="loteValor">Valor mensal (opcional)</label><input type="text" id="loteValor" placeholder="deixe vazio para usar o já cadastrado">
    </div>
    <label class="check"><input type="checkbox" id="lotePdf" checked> <span>Salvar também em PDF</span></label>
    <label class="check"><input type="checkbox" id="loteMover"> <span>Mover os contratos antigos para Contratos Encerrados</span></label>
    <p class="ajuda">Razão social e CNPJ vêm do Contask (ou do nome do arquivo). Dados usados em contratos anteriores da mesma empresa
      são reaproveitados. O que faltar sai destacado em amarelo no Word.</p>
    <div class="lista-mov">${itens.map(a => `<div>${esc(a.nome)} ${a.empresa ? `<span class="mini">→ ${esc(a.empresa.nome)}</span>` : '<span class="mini">(sem empresa no Contask)</span>'}</div>`).join("")}</div>`;
  if (!(await confirmar("Gerar no novo modelo", html, `Gerar ${itens.length} contrato(s)`))) return;
  const comuns = { DATA_INICIO: $("#loteInicio").value, VALOR: $("#loteValor").value.trim() };
  try {
    const r = await post("/api/modelos/gerar-lote", { id: $("#loteModelo").value, rels: itens.map(a => a.rel),
      valores_comuns: comuns, mover_antigos: $("#loteMover").checked, com_pdf: $("#lotePdf").checked });
    const ok = r.resultados.filter(x => x.ok);
    await confirmar("Resultado", `<p><b>${ok.length}</b> de ${r.resultados.length} contratos gerados.</p>
      <div class="lista-mov">${r.resultados.map(x => `<div>${x.ok ? "✔" : "✖"} <b>${esc(x.arquivo || x.rel)}</b>
        ${x.faltando?.length ? `<br><span class="mini">Completar no Word: ${esc(x.faltando.join(", "))}</span>` : ""}${x.erro ? `<br><span class="mini">${esc(x.erro)}</span>` : ""}</div>`).join("")}</div>`, "OK");
    st.sel.clear();
    carregarModelos();
    acompanhar();
  } catch (e) { toast(e.message, "erro"); }
}

/* ---------- contratos antigos x novos ---------- */
const EXT_CONTRATO = [".pdf", ".doc", ".docx", ".rtf", ".odt"];
const selAntigos = new Set();

function arquivosNovos() {
  const s = new Set();
  mod.hist.forEach(h => { if (h.arquivo) s.add(h.arquivo); if (h.arquivo_pdf) s.add(h.arquivo_pdf); });
  return s;
}

/* empresa -> contrato novo mais recente (por id do Contask, CNPJ ou nome) */
function indiceNovos(hist = mod.hist) {
  const idx = {};
  [...hist].reverse().forEach(h => {  // do mais antigo ao mais novo: o último gravado vence
    if (h.empresa_id) idx["id:" + h.empresa_id] = h;
    const c = String(h.cnpj || "").replace(/\D/g, "");
    if (c) idx["cnpj:" + c] = h;
    if (h.empresa) idx["nome:" + norm(h.empresa)] = h;
  });
  return idx;
}

function novoDaEmpresa(a, idx) {
  const e = a.empresa;
  if (e) {
    return idx["id:" + e.id] || idx["cnpj:" + String(e.cnpj || "").replace(/\D/g, "")] || idx["nome:" + norm(e.nome)] || null;
  }
  const base = norm(a.nome.replace(/\.[^.]+$/, "").replace(/\s+\d+$/, ""));
  if (base.length < 5) return null;
  return Object.entries(idx).find(([k]) => k.startsWith("nome:") && (k.slice(5).startsWith(base) || base.startsWith(k.slice(5))))?.[1] || null;
}

const dataContrato = a => (a.data_texto || a.modificado || "").slice(0, 10);

function idade(iso) {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00"), h = new Date();
  let meses = (h.getFullYear() - d.getFullYear()) * 12 + h.getMonth() - d.getMonth();
  if (h.getDate() < d.getDate()) meses--;
  if (meses < 1) return "menos de 1 mês";
  const anos = Math.floor(meses / 12), m = meses % 12;
  return [anos ? `${anos} ano${anos > 1 ? "s" : ""}` : "", m ? `${m} ${m > 1 ? "meses" : "mês"}` : ""].filter(Boolean).join(" e ");
}

function listaAntigos() {
  if (!st.analise) return [];
  const novos = arquivosNovos(), idx = indiceNovos();
  const nossos = new Set(st.estado?.config?.status_nossos || []);
  const t = norm($("#anBusca").value).split(/\s+/).filter(Boolean);
  const filtro = $("#anFiltro").value, incluirEnc = $("#anEncerrados").checked;
  const lista = st.analise.arquivos
    .filter(a => !novos.has(a.rel) && EXT_CONTRATO.includes(a.ext) && a.situacao !== "MODELO" && (incluirEnc || !a.em_encerrados))
    .map(a => ({ a, novo: novoDaEmpresa(a, idx), data: dataContrato(a) }))
    .filter(({ a, novo }) => {
      if (filtro === "sem_novo" && novo) return false;
      if (filtro === "com_novo" && !novo) return false;
      if (filtro === "nossas" && !(a.empresa && nossos.has(a.empresa.status))) return false;
      if (t.length) {
        const alvo = norm([a.nome, a.pasta, a.empresa?.nome, a.empresa?.num, a.contratante].join(" "));
        if (!t.every(x => alvo.includes(x))) return false;
      }
      return true;
    });
  const dir = $("#anOrdem").value === "desc" ? -1 : 1;
  lista.sort((x, y) => ((x.data || "9999") < (y.data || "9999") ? -1 : (x.data || "9999") > (y.data || "9999") ? 1 : 0) * dir);
  return lista;
}

function renderAntigos() {
  const lista = listaAntigos();
  const semNovo = lista.filter(x => !x.novo).length;
  const maisVelho = lista.map(x => x.data).filter(Boolean).sort()[0];
  $("#contAntigos").textContent = st.analise ? listaAntigosTotal() : "";
  $("#kpisAntigos").innerHTML = [
    ["Contratos antigos", lista.length, "nesta lista", "var(--laranja)"],
    ["Ainda sem contrato novo", semNovo, "empresas a atualizar", "var(--amarelo)"],
    ["Já têm contrato novo", lista.length - semNovo, "podem ir para Encerrados", "var(--verde)"],
    ["Mais antigo", maisVelho ? dataBR(maisVelho) : "—", maisVelho ? idade(maisVelho) : "", "var(--texto-3)"],
  ].map(([r, n, d, c]) => `<div class="cartao kpi" style="--cor:${c}"><div class="rot">${r}</div><div class="num" style="font-size:${String(n).length > 6 ? 20 : 28}px">${n}</div><div class="det">${esc(d)}</div></div>`).join("");
  $("#corpoAntigos").innerHTML = lista.map(({ a, novo, data }) => {
    const e = a.empresa;
    return `<tr class="${selAntigos.has(a.rel) ? "sel" : ""}">
      <td><input type="checkbox" data-sela="${esc(a.rel)}" ${selAntigos.has(a.rel) ? "checked" : ""}></td>
      <td class="data">${dataBR(data)}${a.data_texto ? '<div class="mini">data no contrato</div>' : '<div class="mini">data do arquivo</div>'}</td>
      <td class="data">${idade(data)}</td>
      <td><button class="btn link nome-arq" data-det="${esc(a.rel)}" style="text-align:left">${esc(a.nome)}</button>
        <div class="caminho">${esc(a.pasta || "(pasta principal)")}</div></td>
      <td>${e ? `${esc(e.nome)} ${stTag(e.status)}` : '<span class="mini">não identificada no Contask</span>'}</td>
      <td>${novo ? `<span class="tag s-ATIVA">Sim</span><div class="mini">${dataBR(novo.data)} · ${esc(novo.modelo.replace("Contrato de ", ""))}</div>` : '<span class="tag s-SUSPENSA">Ainda não</span>'}</td>
      <td><div class="acoes-ant">
        <button class="btn peq pri" data-gerar-ant="aditivo" data-rel="${esc(a.rel)}" title="Gerar termo aditivo para atualizar este contrato">📝 Termo Aditivo</button>
        <button class="btn peq" data-gerar-ant="locacao" data-rel="${esc(a.rel)}" title="Gerar contrato de aluguel no modelo novo">🏢 Aluguel</button>
        <button class="btn peq" data-abrir-ant="${esc(a.rel)}">Abrir</button></div></td></tr>`;
  }).join("") || `<tr><td colspan="7" class="vazio">${st.analise ? "Nenhum contrato antigo com esses filtros." : "Sem análise ainda."}</td></tr>`;
  $("#rodapeAntigos").textContent = `${lista.length} contratos antigos`;
  $("#anSelTodos").checked = lista.length && lista.every(x => selAntigos.has(x.a.rel));
  $$("#corpoAntigos [data-sela]").forEach(cb => cb.onchange = () => {
    cb.checked ? selAntigos.add(cb.dataset.sela) : selAntigos.delete(cb.dataset.sela);
    cb.closest("tr").classList.toggle("sel", cb.checked); barraAntigos();
  });
  $$("#corpoAntigos [data-det]").forEach(b => b.onclick = () => abrirGaveta(b.dataset.det));
  $$("#corpoAntigos [data-gerar-ant]").forEach(b => b.onclick = () => abrirGerar(b.dataset.gerarAnt, { rel: b.dataset.rel }));
  $$("#corpoAntigos [data-abrir-ant]").forEach(b => b.onclick = () => abrirItem(b.dataset.abrirAnt));
  barraAntigos();
}

function listaAntigosTotal() {
  const novos = arquivosNovos();
  return st.analise.arquivos.filter(a => !novos.has(a.rel) && EXT_CONTRATO.includes(a.ext) && a.situacao !== "MODELO" && !a.em_encerrados).length;
}

function barraAntigos() {
  $("#barraAntigos").classList.toggle("on", selAntigos.size > 0);
  $("#anQtd").textContent = `${selAntigos.size} selecionado${selAntigos.size === 1 ? "" : "s"}`;
}

const kpiHtml = itens => itens.map(([r, n, d, c]) =>
  `<div class="cartao kpi" style="--cor:${c}"><div class="rot">${r}</div><div class="num">${n}</div><div class="det">${esc(d)}</div></div>`).join("");

/* linhas da tabela de contratos gerados (usada em Contratos Novos e Termos Aditivos) */
function linhasGerados(lista, comModelo) {
  const existentes = new Set((st.analise?.arquivos || []).map(a => a.rel));
  const porRel = Object.fromEntries((st.analise?.arquivos || []).map(a => [a.rel, a]));
  return lista.map(h => {
    const existe = existentes.has(h.arquivo);
    const aut = (porRel[h.arquivo]?.autentique || porRel[h.arquivo_pdf]?.autentique || [])[0];
    return `<tr>
      <td class="data">${dataBR(h.data, true)}</td>
      <td><b>${esc(h.empresa || "—")}</b><div class="mini">${esc(h.cnpj || "")}</div></td>
      ${comModelo ? `<td>${ROTULO_MOD[h.modelo_id] || esc(h.modelo)}</td>` : ""}
      <td style="white-space:nowrap">
        <button class="btn peq" data-abrir-ger="${esc(h.arquivo)}" ${existe ? "" : "disabled"}>📄 Word</button>
        ${h.arquivo_pdf ? `<button class="btn peq" data-abrir-ger="${esc(h.arquivo_pdf)}" ${existentes.has(h.arquivo_pdf) ? "" : "disabled"}>📕 PDF</button>` : ""}
        ${h.valores ? `<button class="btn peq" data-pdf-ger="${esc(h.id)}">⬇ Baixar PDF</button>
          <button class="btn peq pri" data-editar-ger="${esc(h.id)}" title="Alterar os dados deste contrato e regravar o Word/PDF">✏️ Editar</button>` : ""}
        <div class="caminho">${esc(h.arquivo)}</div>
        ${h.edicoes?.length ? `<div class="mini">✏️ alterado em ${dataBR(h.edicoes.at(-1).data, true)} por ${esc(h.edicoes.at(-1).usuario || "")}</div>` : ""}</td>
      <td>${esc(h.usuario)}</td>
      <td class="mini">${h.substituiu ? esc(h.substituiu) + "<br>(foi para Encerrados)" : "—"}</td>
      <td>${existe ? '<span class="tag s-ATIVA">Na pasta</span>' : '<span class="tag s-ARQUIVADO" title="O arquivo foi movido, renomeado ou apagado">Não encontrado</span>'}
        ${aut ? `<div style="margin-top:4px">${autTag(aut.status)}</div>` : ""}
        ${h.faltando?.length ? `<div class="mini" style="color:var(--amarelo)">Completar: ${esc(h.faltando.join(", "))}</div>` : ""}</td></tr>`;
  }).join("");
}

function ligarGerados(sel) {
  $$(sel + " [data-abrir-ger]").forEach(b => b.onclick = () => abrirItem(b.dataset.abrirGer));
  $$(sel + " [data-editar-ger]").forEach(b => b.onclick = () => editarGerado(mod.hist.find(x => x.id === b.dataset.editarGer)));
  $$(sel + " [data-pdf-ger]").forEach(b => b.onclick = () => {
    const h = mod.hist.find(x => x.id === b.dataset.pdfGer);
    baixarPdf(h.modelo_id, h.valores, b);
  });
}

const buscaHist = (h, termos) => !termos.length || termos.every(x => norm([h.empresa, h.cnpj, h.arquivo, h.usuario].join(" ")).includes(x));
const doMes = h => (h.data || "").startsWith(new Date().toISOString().slice(0, 7));

function renderNovos() {
  const todos = mod.hist.filter(h => h.modelo_id !== "aditivo" && !ehAvulso(h.modelo_id));  // têm aba própria
  const t = norm($("#noBusca").value).split(/\s+/).filter(Boolean);
  const modeloF = $("#noModelo").value;
  const lista = todos.filter(h => (!modeloF || h.modelo_id === modeloF) && buscaHist(h, t));
  $("#contNovos").textContent = todos.length || "";
  $("#kpisNovos").innerHTML = kpiHtml([
    ["Contratos novos", todos.length, "gerados no modelo novo", "var(--primaria)"],
    ["Este mês", todos.filter(doMes).length, "gerados neste mês", "var(--verde)"],
    ["Contábeis", todos.filter(h => h.modelo_id === "contabil").length, "prestação de serviços", "var(--azul)"],
    ["Aluguel", todos.filter(h => h.modelo_id === "locacao").length, "endereço fiscal", "var(--roxo)"],
  ]);
  $("#corpoNovos").innerHTML = linhasGerados(lista, true)
    || `<tr><td colspan="7" class="vazio">Nenhum contrato novo ainda. Use “+ Novo contrato” ou a aba Contratos Antigos.</td></tr>`;
  $("#rodapeNovos").textContent = `${lista.length} contratos novos`;
  ligarGerados("#corpoNovos");
}

/* ---------- termos aditivos ---------- */
const selAditivos = new Set();

function pendentesAditivo() {
  if (!st.analise) return [];
  const gerados = arquivosNovos();
  const idx = indiceNovos(mod.hist.filter(h => h.modelo_id === "aditivo"));
  return st.analise.arquivos
    .filter(a => !gerados.has(a.rel) && EXT_CONTRATO.includes(a.ext) && a.situacao !== "MODELO" && !a.em_encerrados)
    .filter(a => !novoDaEmpresa(a, idx))
    .map(a => ({ a, data: dataContrato(a) }))
    .sort((x, y) => (x.data || "9999").localeCompare(y.data || "9999"));
}

function renderAditivos() {
  const todos = mod.hist.filter(h => h.modelo_id === "aditivo");
  const t = norm($("#adBusca").value).split(/\s+/).filter(Boolean);
  const lista = todos.filter(h => buscaHist(h, t));
  const pend = pendentesAditivo().filter(({ a }) => !t.length || t.every(x => norm([a.nome, a.empresa?.nome].join(" ")).includes(x)));
  $("#contAditivos").textContent = todos.length || "";
  $("#kpisAditivos").innerHTML = kpiHtml([
    ["Termos aditivos", todos.length, "gerados", "var(--laranja)"],
    ["Este mês", todos.filter(doMes).length, "gerados neste mês", "var(--verde)"],
    ["Clientes sem termo aditivo", pendentesAditivo().length, "contratos antigos a atualizar", "var(--amarelo)"],
    ["Com PDF", todos.filter(h => h.arquivo_pdf).length, "prontos para o Autentique", "var(--primaria)"],
  ]);
  $("#adQtd").textContent = `${lista.length} termo(s)`;
  $("#corpoAditivos").innerHTML = linhasGerados(lista, false)
    || `<tr><td colspan="6" class="vazio">Nenhum termo aditivo gerado ainda. Use “Gerar termo aditivo”, acima, ou a lista abaixo.</td></tr>`;
  ligarGerados("#corpoAditivos");
  $("#adPendQtd").textContent = `${pend.length} contrato(s)`;
  $("#corpoAdPendentes").innerHTML = pend.map(({ a, data }) => `<tr class="${selAditivos.has(a.rel) ? "sel" : ""}">
      <td><input type="checkbox" data-selad="${esc(a.rel)}" ${selAditivos.has(a.rel) ? "checked" : ""}></td>
      <td class="data">${dataBR(data)}</td><td class="data">${idade(data)}</td>
      <td><button class="btn link" data-det-ad="${esc(a.rel)}" style="white-space:normal;text-align:left;padding:0">${esc(a.nome)}</button></td>
      <td>${a.empresa ? `${esc(a.empresa.nome)} ${stTag(a.empresa.status)}` : '<span class="mini">não identificada no Contask</span>'}</td>
      <td><button class="btn peq pri" data-gerar-ad="${esc(a.rel)}">📝 Gerar</button></td></tr>`).join("")
    || `<tr><td colspan="6" class="vazio">Todos os contratos antigos já têm termo aditivo. 🎉</td></tr>`;
  $("#adSelTodos").checked = pend.length && pend.every(x => selAditivos.has(x.a.rel));
  $$("#corpoAdPendentes [data-selad]").forEach(cb => cb.onchange = () => {
    cb.checked ? selAditivos.add(cb.dataset.selad) : selAditivos.delete(cb.dataset.selad);
    cb.closest("tr").classList.toggle("sel", cb.checked); barraAditivos();
  });
  $$("#corpoAdPendentes [data-gerar-ad]").forEach(b => b.onclick = () => abrirGerar("aditivo", { rel: b.dataset.gerarAd }));
  $$("#corpoAdPendentes [data-det-ad]").forEach(b => b.onclick = () => abrirGaveta(b.dataset.detAd));
  barraAditivos();
}

function barraAditivos() {
  $("#barraAditivos").classList.toggle("on", selAditivos.size > 0);
  $("#adSelQtd").textContent = `${selAditivos.size} selecionado${selAditivos.size === 1 ? "" : "s"}`;
}

/* ---------- cobrança / termos de acordo ---------- */
const PASSOS_COB = [
  { id: "cobranca", n: 1, cor: "var(--amarelo)", titulo: "Cobrança", sub: "Notificação de débito e solicitação de regularização",
    itens: ["Mensalidades em aberto e valor total (com extenso)", "Riscos fiscais: Inscrição Estadual (GDF) e CNPJ inapto (RFB)",
      "Telefone/WhatsApp e e-mail do financeiro para negociar"] },
  { id: "suspensao", n: 2, cor: "var(--laranja)", titulo: "Notificação de suspensão", sub: "Notificação extrajudicial por inadimplemento",
    itens: ["Para quem não respondeu à cobrança", "Suspende todos os serviços com base na cláusula do contrato",
      "Os serviços voltam com a quitação ou com o termo de acordo"] },
  { id: "notificacao", n: 3, cor: "var(--vermelho)", titulo: "Notificação extrajudicial", sub: "Prazo final antes das medidas legais",
    itens: ["Débito com multa e juros de mora do contrato", "Prazo para regularizar (padrão: 5 dias)",
      "Avisa: CDL, assessoria de cobrança (+10%) e ação judicial"] },
  { id: "acordo", n: 4, cor: "var(--verde)", titulo: "Termo de acordo", sub: "Parcelamento para quitar o débito",
    itens: ["Entrada opcional; parcelas calculadas sozinhas", "Cronograma com o vencimento de cada parcela",
      "Assinatura das partes e de 2 testemunhas"] },
];
const ETAPA_COB = { cobranca: ["Cobrado", "s-SUSPENSA"], suspensao: ["Serviços suspensos", "s-ENCERRADA"],
  notificacao: ["Notificado", "s-NAO_CLIENTE"], acordo: ["Em acordo", "s-ATIVA"] };
const PROXIMO_COB = {  // próximo passo sugerido para cada etapa: [modelo, texto do botão]
  cobranca: [["suspensao", "⛔ Notificar suspensão"], ["notificacao", "⚖️ Notificação extrajudicial"], ["acordo", "🤝 Fazer acordo"]],
  suspensao: [["notificacao", "⚖️ Notificação extrajudicial"], ["acordo", "🤝 Fazer acordo"], ["rescisao", "📨 Notificar rescisão"]],
  notificacao: [["acordo", "🤝 Fazer acordo"], ["rescisao", "📨 Notificar rescisão"]],
  acordo: [["cobranca", "💰 Nova cobrança"]],
};
const filtroCob = { tipo: "" };

const docsCob = () => mod.hist.filter(h => COB.includes(h.modelo_id));
const chaveCli = h => { const c = String(h.cnpj || "").replace(/\D/g, ""); return c ? "c:" + c : "n:" + norm(h.empresa); };
const diaDe = iso => { const [a, m, d] = String(iso || "").slice(0, 10).split("-"); return new Date(+a, m - 1, +d); };
const somaDias = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const brData = d => d.toLocaleDateString("pt-BR");
const numBR = v => parseFloat(String(v || "0").replace(/\./g, "").replace(",", ".")) || 0;
const reais = n => "R$ " + n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/* prazo de resposta da cobrança: o informado no documento (cobranças antigas) ou 5 dias */
function prazoCobranca(h) {
  const n = parseInt(String(h.valores?.PRAZO_DIAS || "").match(/\d+/)?.[0] || "5", 10);
  const fim = somaDias(diaDe(h.data), n);
  return { fim, vencido: fim < diaDe(hojeISO()), dias: Math.round((diaDe(hojeISO()) - diaDe(h.data)) / 864e5) };
}

/* lê o cronograma salvo no histórico ("| 1ª parcela | 05/11/2026 | R$ 217,86 |") */
function parcelasAcordo(h) {
  return String(h.valores?.PARCELAS_TABELA || "").split("\n").map(l => l.split("|").map(x => x.trim()))
    .filter(c => /^(\d+ª parcela|Entrada)$/.test(c[1] || "") && /^\d{2}\/\d{2}\/\d{4}$/.test(c[2] || ""))
    .map(c => { const [d, m, a] = c[2].split("/"); return { nome: c[1], data: new Date(+a, m - 1, +d), valor: c[3] }; });
}

/* um registro por cliente com o último documento de cada tipo; a etapa é a do documento mais recente */
function clientesCob() {
  const por = {};
  [...docsCob()].reverse().forEach(h => {  // do mais antigo ao mais novo
    const c = por[chaveCli(h)] ||= { empresa: h.empresa, cnpj: h.cnpj, empresa_id: h.empresa_id, docs: [] };
    c.docs.push(h); c[h.modelo_id] = h; c.ultimo = h;
    if (h.empresa_id) c.empresa_id = h.empresa_id;
  });
  return Object.values(por).sort((a, b) => (b.ultimo.data || "").localeCompare(a.ultimo.data || ""));
}

function situacaoCob(c) {
  const u = c.ultimo, hoje = diaDe(hojeISO());
  if (u.modelo_id === "cobranca") {
    const p = prazoCobranca(u);
    return p.vencido
      ? `<b style="color:var(--vermelho)">Cobrado há ${p.dias} dias, sem retorno</b><div class="mini">se não houve acordo, pode notificar a suspensão</div>`
      : `Aguardando retorno até <b>${brData(p.fim)}</b><div class="mini">cobrado há ${p.dias} dia(s)</div>`;
  }
  if (u.modelo_id === "suspensao") {
    const dias = Math.round((hoje - diaDe(u.data)) / 864e5);
    return `Suspenso desde <b>${dataBR(u.data)}</b><div class="mini">há ${dias} dia(s)</div>`;
  }
  if (u.modelo_id === "notificacao") {
    const p = prazoCobranca(u);
    return p.vencido
      ? `<b style="color:var(--vermelho)">Prazo vencido em ${brData(p.fim)}</b><div class="mini">sem acordo: CDL, assessoria de cobrança ou ação judicial</div>`
      : `Prazo para regularizar até <b>${brData(p.fim)}</b><div class="mini">notificado há ${p.dias} dia(s)</div>`;
  }
  const ps = parcelasAcordo(u);
  if (!ps.length) return '<span class="mini">Acordo assinado</span>';
  const prox = ps.find(p => p.data >= hoje);
  const vencidas = ps.filter(p => p.data < hoje).length;
  return prox
    ? `Próxima: <b>${esc(prox.nome)}</b> em <b>${brData(prox.data)}</b> (${esc(prox.valor)})<div class="mini">${vencidas} de ${ps.length} já venceram — confira os pagamentos</div>`
    : `<b style="color:var(--verde)">Todas as ${ps.length} parcelas já venceram</b><div class="mini">confira os pagamentos para dar a quitação</div>`;
}

function renderCobranca() {
  if (!$("#sec-cobranca")) return;
  // os três passos (subfunções)
  $("#cartoesCobranca").innerHTML = PASSOS_COB.map((p, i) => `
    <div class="cartao cob-passo" style="--cor:${p.cor}">
      <span class="num">${p.n}</span>
      <div style="display:flex;gap:10px;align-items:center">
        <div class="mod-icone">${ICONE_MOD[p.id]}</div>
        <div><h3>${p.n}. ${esc(p.titulo)}</h3><div class="mini">${esc(p.sub)}</div></div>
      </div>
      <ul>${p.itens.map(t => `<li>${esc(t)}</li>`).join("")}</ul>
      <div class="acoes">
        <button class="btn pri" data-cob-gerar="${p.id}">${textoBtnGerar(p.id)}</button>
        <button class="btn" data-cob-editar="${p.id}">✏️ Editar modelo</button>
      </div>
      ${i < PASSOS_COB.length - 1 ? '<span class="seta">➜</span>' : ""}
    </div>`).join("");
  $$("#cartoesCobranca [data-cob-gerar]").forEach(b => b.onclick = () => abrirGerar(b.dataset.cobGerar));
  $$("#cartoesCobranca [data-cob-editar]").forEach(b => b.onclick = () => abrirEditar(b.dataset.cobEditar));

  const docs = docsCob(), clientes = clientesCob();
  const naEtapa = id => clientes.filter(c => c.ultimo.modelo_id === id);
  const vencidos = naEtapa("cobranca").filter(c => prazoCobranca(c.ultimo)?.vencido);
  const emAberto = clientes.filter(c => c.ultimo.modelo_id !== "acordo").reduce((s, c) => s + numBR(c.ultimo.valores?.VALOR_DEBITO), 0);
  const emAcordo = naEtapa("acordo").reduce((s, c) => s + numBR(c.ultimo.valores?.VALOR_DEBITO), 0);
  $("#contCobranca").textContent = clientes.filter(c => c.ultimo.modelo_id !== "acordo").length || "";
  $("#kpisCobranca").innerHTML = kpiHtml([
    ["Clientes cobrados", naEtapa("cobranca").length, "aguardando retorno", "var(--amarelo)"],
    ["Sem retorno", vencidos.length, "cobrados há mais de 5 dias", "var(--vermelho)"],
    ["Serviços suspensos", naEtapa("suspensao").length, "aguardando acordo ou quitação", "var(--laranja)"],
    ["Notificados", naEtapa("notificacao").length, "notificação extrajudicial", "var(--vermelho)"],
    ["Em acordo", naEtapa("acordo").length, reais(emAcordo) + " parcelados", "var(--verde)"],
    ["Débito em aberto", reais(emAberto), "cobranças, suspensões e notificações", "var(--primaria)"],
  ]);

  // acompanhamento por cliente
  const t = norm($("#cobBusca").value).split(/\s+/).filter(Boolean);
  const etapa = $("#cobEtapa").value;
  const lista = clientes.filter(c => {
    if (etapa === "prazo" ? !(c.ultimo.modelo_id === "cobranca" && prazoCobranca(c.ultimo)?.vencido)
        : etapa === "notif_prazo" ? !(c.ultimo.modelo_id === "notificacao" && prazoCobranca(c.ultimo)?.vencido)
        : etapa && c.ultimo.modelo_id !== etapa) return false;
    return !t.length || t.every(x => norm([c.empresa, c.cnpj].join(" ")).includes(x));
  });
  const celDoc = h => h ? `<b>${dataBR(h.data)}</b><div class="mini">${esc(h.usuario || "")}</div>` : '<span class="mini">—</span>';
  $("#cobCliQtd").textContent = `${lista.length} cliente(s)`;
  $("#corpoCobClientes").innerHTML = lista.map((c, i) => {
    const u = c.ultimo, [rot, tag] = ETAPA_COB[u.modelo_id];
    const ordem = COB.indexOf(u.modelo_id);
    return `<tr>
      <td><b>${esc(c.empresa || "—")}</b><div class="mini">${esc(c.cnpj || "")}</div>
        <div class="cob-etapas" style="--cor:${PASSOS_COB[ordem].cor}">${COB.map((_, j) => `<i class="${j <= ordem ? "on" : ""}"></i>`).join("")}</div></td>
      <td style="white-space:nowrap"><b>R$ ${esc(u.valores?.VALOR_DEBITO || "—")}</b>
        ${u.valores?.VENCIMENTOS ? `<div class="mini" style="white-space:normal;max-width:220px">venc.: ${esc(u.valores.VENCIMENTOS)}</div>` : ""}</td>
      <td>${celDoc(c.cobranca)}</td><td>${celDoc(c.suspensao)}</td><td>${celDoc(c.notificacao)}</td>
      <td>${celDoc(c.acordo)}${c.acordo?.valores?.QTD_PARCELAS ? `<div class="mini">${esc(c.acordo.valores.QTD_PARCELAS.replace(/\s*\(.*\)/, ""))}x de R$ ${esc(c.acordo.valores.VALOR_PARCELA || "")}</div>` : ""}</td>
      <td><span class="tag ${tag}">${rot}</span><div style="margin-top:4px">${situacaoCob(c)}</div></td>
      <td><div style="display:flex;flex-direction:column;gap:4px;align-items:flex-start">
        ${PROXIMO_COB[u.modelo_id].map(([id, txt], j) => `<button class="btn peq ${j ? "" : "pri"}" data-cob-prox="${i}" data-id="${id}">${txt}</button>`).join("")}
        <button class="btn peq" data-cob-hist="${i}" title="Mostrar só os documentos deste cliente">📄 Documentos (${c.docs.length})</button></div></td>
    </tr>`;
  }).join("") || `<tr><td colspan="8" class="vazio">${clientes.length ? "Nenhum cliente com esses filtros." : "Nenhuma cobrança emitida ainda. Comece pelo passo 1, acima."}</td></tr>`;
  $$("#corpoCobClientes [data-cob-prox]").forEach(b => b.onclick = () => {
    const c = lista[+b.dataset.cobProx];
    abrirGerar(b.dataset.id, { empresaId: c.empresa_id || null, valores: c.ultimo.valores });
  });
  $$("#corpoCobClientes [data-cob-hist]").forEach(b => b.onclick = () => {
    const c = lista[+b.dataset.cobHist];
    $("#cobBusca").value = String(c.cnpj || c.empresa || ""); filtroCob.tipo = "";
    renderCobranca();
    $("#corpoCobDocs").closest(".cartao").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  // documentos emitidos
  $("#cobTipos").innerHTML = [["", "Todos"], ...COB.map(id => [id, ROTULO_MOD[id]])].map(([id, rot]) =>
    `<button class="chip ${filtroCob.tipo === id ? "on" : ""}" data-cob-tipo="${id}">${rot} <span class="q">${id ? docs.filter(h => h.modelo_id === id).length : docs.length}</span></button>`).join("");
  $$("#cobTipos [data-cob-tipo]").forEach(b => b.onclick = () => { filtroCob.tipo = b.dataset.cobTipo; renderCobranca(); });
  const ldocs = docs.filter(h => (!filtroCob.tipo || h.modelo_id === filtroCob.tipo)
    && (!t.length || t.every(x => norm([h.empresa, h.cnpj, h.arquivo, h.usuario].join(" ")).includes(x))));
  $("#cobDocQtd").textContent = `${ldocs.length} documento(s)`;
  $("#corpoCobDocs").innerHTML = ldocs.map(h => {
    const v = h.valores || {};
    return `<tr>
      <td class="data">${dataBR(h.data, true)}</td>
      <td>${ROTULO_MOD[h.modelo_id]}</td>
      <td><b>${esc(h.empresa || "—")}</b><div class="mini">${esc(h.cnpj || "")}</div></td>
      <td style="white-space:nowrap">R$ ${esc(v.VALOR_DEBITO || "—")}
        ${h.modelo_id === "acordo" && v.QTD_PARCELAS ? `<div class="mini">${v.VALOR_ENTRADA ? `entrada R$ ${esc(v.VALOR_ENTRADA)} + ` : ""}${esc(v.QTD_PARCELAS.replace(/\s*\(.*\)/, ""))}x R$ ${esc(v.VALOR_PARCELA || "")}</div>` : ""}</td>
      <td style="white-space:nowrap">
        <button class="btn peq" data-abrir-ger="${esc(h.arquivo)}" ${h.existe ? "" : "disabled"}>📄 Word</button>
        ${h.arquivo_pdf ? `<button class="btn peq" data-abrir-ger="${esc(h.arquivo_pdf)}" ${h.existe_pdf ? "" : "disabled"}>📕 PDF</button>` : ""}
        <button class="btn peq" data-pdf-ger="${esc(h.id)}">⬇ Baixar PDF</button>
        <div class="caminho">${esc(h.arquivo)}</div></td>
      <td>${esc(h.usuario)}</td>
      <td>${h.existe ? '<span class="tag s-ATIVA">Na pasta</span>' : '<span class="tag s-ARQUIVADO" title="O arquivo foi movido, renomeado ou apagado">Não encontrado</span>'}
        ${h.faltando?.length ? `<div class="mini" style="color:var(--amarelo)">Completar: ${esc(h.faltando.join(", "))}</div>` : ""}</td></tr>`;
  }).join("") || `<tr><td colspan="7" class="vazio">Nenhum documento ${filtroCob.tipo || t.length ? "com esses filtros" : "emitido ainda"}.</td></tr>`;
  ligarGerados("#corpoCobDocs");
  renderEncerramento();
}

/* ---------- aba rescisão / distrato ---------- */
/* um registro por cliente com a última rescisão e o último distrato */
function clientesEnc() {
  const por = {};
  [...mod.hist.filter(h => ENC.includes(h.modelo_id))].reverse().forEach(h => {
    const c = por[chaveCli(h)] ||= { empresa: h.empresa, cnpj: h.cnpj, empresa_id: h.empresa_id, docs: [] };
    c.docs.push(h); c[h.modelo_id] = h; c.ultimo = h;
    if (h.empresa_id) c.empresa_id = h.empresa_id;
  });
  const hoje = diaDe(hojeISO());
  return Object.values(por).map(c => {
    const ref = c.distrato || c.rescisao;
    const [d, m, a] = String(ref.valores?.DATA_ENCERRAMENTO || "").split(/[./]/);
    c.fim = a ? new Date(+a, m - 1, +d) : null;
    c.situacao = c.distrato ? "distrato" : c.fim && c.fim >= hoje ? "aviso" : "semdistrato";
    return c;
  }).sort((x, y) => (y.ultimo.data || "").localeCompare(x.ultimo.data || ""));
}

function renderEncerramento() {
  if (!$("#sec-encerramento")) return;
  const clientes = clientesEnc(), hoje = diaDe(hojeISO());
  const docs = mod.hist.filter(h => ENC.includes(h.modelo_id));
  const em = s => clientes.filter(c => c.situacao === s);
  $("#contEnc").textContent = em("aviso").length + em("semdistrato").length || "";
  $("#kpisEnc").innerHTML = kpiHtml([
    ["Em aviso prévio", em("aviso").length, "contrato ainda não encerrou", "var(--amarelo)"],
    ["Encerrados sem distrato", em("semdistrato").length, "falta formalizar o distrato", "var(--vermelho)"],
    ["Com distrato", em("distrato").length, "encerramento formalizado", "var(--verde)"],
    ["Documentos", docs.length, "rescisões e distratos emitidos", "var(--primaria)"],
  ]);

  const t = norm($("#encBusca").value).split(/\s+/).filter(Boolean);
  const etapa = $("#encEtapa").value;
  const lista = clientes.filter(c => (!etapa || c.situacao === etapa)
    && (!t.length || t.every(x => norm([c.empresa, c.cnpj].join(" ")).includes(x))));
  const celDoc = h => h ? `<b>${dataBR(h.data)}</b><div class="mini">${esc(h.usuario || "")}</div>` : '<span class="mini">—</span>';
  $("#encCliQtd").textContent = `${lista.length} cliente(s)`;
  $("#corpoEncClientes").innerHTML = lista.map((c, i) => {
    const dias = c.fim ? Math.round((c.fim - hoje) / 864e5) : null;
    const sit = c.situacao === "distrato" ? '<span class="tag s-ATIVA">Distrato emitido</span>'
      : c.situacao === "aviso" ? `<span class="tag s-SUSPENSA">Em aviso prévio</span><div class="mini" style="margin-top:4px">encerra em ${dias} dia(s)</div>`
      : `<span class="tag s-NAO_CLIENTE">Encerrado sem distrato</span>${dias !== null ? `<div class="mini" style="margin-top:4px">há ${-dias} dia(s)</div>` : ""}`;
    return `<tr>
      <td><b>${esc(c.empresa || "—")}</b><div class="mini">${esc(c.cnpj || "")}</div></td>
      <td>${celDoc(c.rescisao)}</td>
      <td>${c.fim ? `<b>${brData(c.fim)}</b>` : '<span class="mini">—</span>'}</td>
      <td>${celDoc(c.distrato)}</td>
      <td>${sit}</td>
      <td><div style="display:flex;flex-direction:column;gap:4px;align-items:flex-start">
        ${c.distrato ? "" : `<button class="btn peq pri" data-enc-prox="${i}">📄 Fazer distrato</button>`}
        <button class="btn peq" data-enc-hist="${i}">📄 Documentos (${c.docs.length})</button></div></td></tr>`;
  }).join("") || `<tr><td colspan="6" class="vazio">${clientes.length ? "Nenhum cliente com esses filtros." : "Nenhuma rescisão ou distrato emitido ainda."}</td></tr>`;
  $$("#corpoEncClientes [data-enc-prox]").forEach(b => b.onclick = () => {
    const c = lista[+b.dataset.encProx];
    // débito da última cobrança/suspensão do mesmo cliente vai para o distrato
    const cob = docsCob().find(h => chaveCli(h) === chaveCli(c.ultimo) && h.modelo_id !== "acordo");
    abrirGerar("distrato", { empresaId: c.empresa_id || null,
      valores: { ...(cob ? { VALOR_DEBITO: cob.valores?.VALOR_DEBITO } : {}), ...c.ultimo.valores } });
  });
  $$("#corpoEncClientes [data-enc-hist]").forEach(b => b.onclick = () => {
    const c = lista[+b.dataset.encHist];
    $("#encBusca").value = String(c.cnpj || c.empresa || "");
    renderEncerramento();
    $("#corpoEncDocs").closest(".cartao").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  const ldocs = docs.filter(h => !t.length || t.every(x => norm([h.empresa, h.cnpj, h.arquivo, h.usuario].join(" ")).includes(x)));
  $("#encDocQtd").textContent = `${ldocs.length} documento(s)`;
  $("#corpoEncDocs").innerHTML = ldocs.map(h => `<tr>
      <td class="data">${dataBR(h.data, true)}</td>
      <td>${ROTULO_MOD[h.modelo_id]}</td>
      <td><b>${esc(h.empresa || "—")}</b><div class="mini">${esc(h.cnpj || "")}</div></td>
      <td>${esc(h.valores?.DATA_ENCERRAMENTO || "—")}</td>
      <td style="white-space:nowrap">
        <button class="btn peq" data-abrir-ger="${esc(h.arquivo)}" ${h.existe ? "" : "disabled"}>📄 Word</button>
        ${h.arquivo_pdf ? `<button class="btn peq" data-abrir-ger="${esc(h.arquivo_pdf)}" ${h.existe_pdf ? "" : "disabled"}>📕 PDF</button>` : ""}
        <button class="btn peq" data-pdf-ger="${esc(h.id)}">⬇ Baixar PDF</button>
        <div class="caminho">${esc(h.arquivo)}</div></td>
      <td>${esc(h.usuario)}</td>
      <td>${h.existe ? '<span class="tag s-ATIVA">Na pasta</span>' : '<span class="tag s-ARQUIVADO" title="O arquivo foi movido, renomeado ou apagado">Não encontrado</span>'}
        ${h.faltando?.length ? `<div class="mini" style="color:var(--amarelo)">Completar: ${esc(h.faltando.join(", "))}</div>` : ""}</td></tr>`).join("")
    || `<tr><td colspan="7" class="vazio">Nenhum documento ${t.length ? "com esses filtros" : "emitido ainda"}.</td></tr>`;
  ligarGerados("#corpoEncDocs");
}

/* ---------- aba propostas ---------- */
const filtroProp = { tipo: "" };

function valorProposta(h) {
  const v = h.valores || {};
  return v.VALOR ? `R$ ${esc(v.VALOR)}<div class="mini">mensal</div>`
    : v.VALOR_TOTAL ? `R$ ${esc(v.VALOR_TOTAL)}<div class="mini">total (3 parcelas)</div>`
    : v.PERCENTUAL ? `${esc(v.PERCENTUAL)}<div class="mini">dos créditos</div>` : "—";
}

function renderPropostas() {
  if (!$("#sec-propostas")) return;
  const docs = mod.hist.filter(h => ehProp(h.modelo_id));
  const ano = String(new Date().getFullYear());
  $("#contProp").textContent = docs.filter(h => String(h.data || "").startsWith(ano)).length || "";
  $("#propTipos").innerHTML = [["", "Todas"], ...PROP.map(id => [id, ROTULO_MOD[id]])].map(([id, rot]) =>
    `<button class="chip ${filtroProp.tipo === id ? "on" : ""}" data-prop-tipo="${id}">${rot} <span class="q">${id ? docs.filter(h => h.modelo_id === id).length : docs.length}</span></button>`).join("");
  $$("#propTipos [data-prop-tipo]").forEach(b => b.onclick = () => { filtroProp.tipo = b.dataset.propTipo; renderPropostas(); });
  const t = norm($("#propBusca").value).split(/\s+/).filter(Boolean);
  const lista = docs.filter(h => (!filtroProp.tipo || h.modelo_id === filtroProp.tipo)
    && (!t.length || t.every(x => norm([h.empresa, h.cnpj, h.arquivo, h.usuario, h.valores?.NUMERO_PROPOSTA].join(" ")).includes(x))));
  $("#propDocQtd").textContent = `${lista.length} proposta(s)`;
  $("#corpoPropDocs").innerHTML = lista.map(h => `<tr>
      <td class="data">${dataBR(h.data, true)}</td>
      <td style="white-space:nowrap"><b>${esc(h.valores?.NUMERO_PROPOSTA || "—")}</b></td>
      <td>${ROTULO_MOD[h.modelo_id]}</td>
      <td><b>${esc(h.empresa || "—")}</b><div class="mini">${esc(h.cnpj || "")}</div></td>
      <td style="white-space:nowrap">${valorProposta(h)}</td>
      <td style="white-space:nowrap">
        <button class="btn peq" data-abrir-ger="${esc(h.arquivo)}" ${h.existe ? "" : "disabled"}>📄 Word</button>
        ${h.arquivo_pdf ? `<button class="btn peq" data-abrir-ger="${esc(h.arquivo_pdf)}" ${h.existe_pdf ? "" : "disabled"}>📕 PDF</button>` : ""}
        <button class="btn peq" data-pdf-ger="${esc(h.id)}">⬇ Baixar PDF</button>
        ${h.valores ? `<button class="btn peq" data-editar-ger="${esc(h.id)}">✏️ Alterar</button>` : ""}
        <div class="caminho">${esc(h.arquivo)}</div></td>
      <td>${esc(h.usuario)}</td>
      <td>${h.existe ? '<span class="tag s-ATIVA">Na pasta</span>' : '<span class="tag s-ARQUIVADO" title="O arquivo foi movido, renomeado ou apagado">Não encontrado</span>'}
        ${h.faltando?.length ? `<div class="mini" style="color:var(--amarelo)">Completar: ${esc(h.faltando.join(", "))}</div>` : ""}</td></tr>`).join("")
    || `<tr><td colspan="8" class="vazio">Nenhuma proposta ${filtroProp.tipo || t.length ? "com esses filtros" : "emitida ainda. Escolha um modelo acima"}.</td></tr>`;
  ligarGerados("#corpoPropDocs");
}

/* ---------- movimentações ---------- */
function renderMovs() {
  $("#corpoMovs").innerHTML = st.movs.map(m => `<tr>
    <td class="data">${dataBR(m.data, true)}</td><td>${esc(m.usuario)}</td>
    <td><span class="tag ${m.acao === "ENCERRAR" ? "s-ENCERRADA" : "s-ATIVA"}">${m.acao === "ENCERRAR" ? "Encerrado" : "Restaurado"}</span></td>
    <td>${esc(m.empresa || "—")}${m.empresa_status ? " " + stTag(m.empresa_status) : ""}</td>
    <td><div class="caminho">${esc(m.origem)}</div><div>→ ${esc(m.destino)}</div></td>
    <td>${m.situacao ? sitTag(m.situacao) : ""}<div class="mini">${esc(m.motivo || "")}</div></td>
    <td>${m.desfeito ? `<span class="mini">Desfeito em ${dataBR(m.desfeito_em, true)} por ${esc(m.desfeito_por || "")}</span>` : `<button class="btn peq" data-desf="${esc(m.id)}">Desfazer</button>`}</td>
  </tr>`).join("") || `<tr><td colspan="7" class="vazio">Nenhuma movimentação ainda.</td></tr>`;
  $$("#corpoMovs [data-desf]").forEach(b => b.onclick = async () => {
    if (!(await confirmar("Desfazer movimentação", "<p>O arquivo voltará para o local de onde foi movido.</p>", "Desfazer"))) return;
    try {
      const r = await post("/api/desfazer", { ids: [b.dataset.desf] });
      relatarResultados(r.resultados, "devolvido(s)");
      st.movs = await api("/api/movimentacoes");
      renderMovs();
      acompanhar();
    } catch (e) { toast(e.message, "erro"); }
  });
}

/* ---------- configurações ---------- */
function renderConfig() {
  const e = st.estado;
  if (!e) return;
  const c = e.config;
  if (document.activeElement?.closest("#sec-config")) return; // não sobrescreve o que está sendo digitado
  $("#cApi").value = c.contask_api;
  $("#cEmail").value = e.contask_email || c.contask_email || "";
  $("#cRaiz").value = c.pasta_raiz;
  $("#cEnc").value = c.pasta_encerrados;
  $("#cLimite").value = c.limite_confianca;
  $("#cLimiteRev").value = c.limite_revisao;
  $("#cCnpjs").value = (c.cnpjs_proprios || []).join("\n");
  $("#contaskStatus").innerHTML = e.contask_conectado
    ? `<div class="conectado"><span class="ponto"></span> Conectado como <b>${esc(e.contask_email)}</b></div>` : "";
  $("#redeInfo").innerHTML = e.modo_rede
    ? `<div class="conectado"><span class="ponto"></span> Modo rede ligado. Nos outros computadores, abra no navegador:</div>
       ${e.enderecos_rede.map(x => `<div class="trecho" style="margin-bottom:6px;user-select:all">${esc(x)}</div>`).join("")}`
    : `<p class="ajuda" style="margin-top:0">Hoje o sistema só abre <b>neste</b> computador. Para usar em outros, feche esta janela e abra
       <b>Iniciar Servidor de Rede.bat</b> (na pasta do sistema) neste computador. Depois, nos outros, é só abrir o endereço que aparecer aqui.</p>`;
  $("#redeUsuario").textContent = e.usuario;
  const au = e.autentique || {};
  $("#aPasta").value = c.autentique_pasta || "";
  $("#aSoNossas").checked = c.autentique_somente_nossas !== false;
  $("#autStatus").innerHTML = au.tem_chave
    ? `<div class="conectado"><span class="ponto"></span> Chave configurada${au.total ? ` · ${au.total} documentos (${esc(au.pasta_nome || "")}) em ${dataBR(au.atualizado_em, true)}` : ""}</div>` : "";
  $("#btnAutSair").disabled = !au.tem_chave;
  $("#btnSincronizar").disabled = !e.contask_conectado;
  $("#btnSair").disabled = !e.contask_conectado;
  const emp = e.empresas;
  $("#fonteAtual").innerHTML = emp.total
    ? `Fonte atual: <b>${esc(emp.fonte)}</b> · ${emp.total} empresas · ${dataBR(emp.atualizado_em, true)}<br>` +
      Object.entries(emp.por_status).map(([s, q]) => `${stTag(s)} ${q}`).join(" &nbsp; ")
    : "Nenhuma empresa carregada ainda.";
  const ini = e.inicio_contratos || {};
  $("#inicioAtual").innerHTML = ini.importado_em
    ? `Planilha atual: <b>${esc(ini.fonte)}</b> · ${ini.empresas} empresas · ${ini.sem_empresa} contratos sem empresa ativa · importada em ${dataBR(ini.importado_em, true)}`
    : "Nenhuma planilha importada ainda — a exportação usa só a análise das pastas.";
  const ign = new Set((c.pastas_ignoradas || []).map(x => x.toLowerCase()));
  $("#listaIgnoradas").innerHTML = e.pastas_topo.filter(p => !p.startsWith("_")).map(p =>
    `<label class="check"><input type="checkbox" value="${esc(p)}" ${ign.has(p.toLowerCase()) ? "checked" : ""}> ${esc(p)}</label>`).join("");
  const sn = new Set(c.status_nossos || []);
  $("#listaStatus").innerHTML = ["ATIVA", "SUSPENSA", "BAIXADA", "DISTRATO"].map(s =>
    `<label class="check"><input type="checkbox" value="${s}" ${sn.has(s) ? "checked" : ""}> ${s}</label>`).join("");
}

async function salvarConfig() {
  const dados = {
    contask_api: $("#cApi").value.trim(),
    pasta_raiz: $("#cRaiz").value.trim(),
    pasta_encerrados: $("#cEnc").value.trim() || "Contrato Encerrado",
    limite_confianca: +$("#cLimite").value || 80,
    limite_revisao: +$("#cLimiteRev").value || 60,
    cnpjs_proprios: $("#cCnpjs").value.split(/\s+/).map(x => x.replace(/\D/g, "")).filter(x => x.length === 14),
    pastas_ignoradas: $$("#listaIgnoradas input:checked").map(i => i.value),
    autentique_somente_nossas: $("#aSoNossas").checked,
    status_nossos: $$("#listaStatus input:checked").map(i => i.value),
  };
  if (!dados.status_nossos.length) return toast("Marque ao menos um status como “empresa nossa”.", "erro");
  try {
    await post("/api/config", dados);
    toast("Configurações salvas.", "ok");
    document.activeElement?.blur();
    reanalisar();
  } catch (e) { toast(e.message, "erro"); }
}

/* ------------------------------------------------------------ eventos */
function ligarEventos() {
  // altura do cabeçalho (as abas podem quebrar em 2 linhas) para as barras fixas ficarem logo abaixo dele
  const alturaTopo = () => document.documentElement.style.setProperty("--h-topo", $(".topo").offsetHeight + "px");
  alturaTopo();
  if (window.ResizeObserver) new ResizeObserver(alturaTopo).observe($(".topo"));
  $$(".aba").forEach(b => b.onclick = () => irPara(b.dataset.aba));
  document.addEventListener("click", ev => {
    const ir = ev.target.closest("[data-ir]");
    if (ir) { ev.preventDefault(); irPara(ir.dataset.ir); }
  });
  $("#btnReanalisar").onclick = reanalisar;
  $("#gFechar").onclick = fecharGaveta;
  $("#fundo").onclick = fecharGaveta;
  document.addEventListener("keydown", ev => {
    if (ev.key === "Escape") { if ($("#modal").classList.contains("on")) $("#mCancelar").click(); else fecharGaveta(); }
  });

  let tBusca;
  $("#fBusca").oninput = ev => { clearTimeout(tBusca); tBusca = setTimeout(() => { st.filtro.busca = ev.target.value; renderContratos(); }, 180); };
  $("#fPasta").onchange = ev => { st.filtro.pasta = ev.target.value; renderContratos(); };
  $("#fAcao").onchange = ev => { st.filtro.acao = ev.target.value; renderContratos(); };
  $("#fDataDe").onchange = ev => { st.filtro.de = ev.target.value; renderContratos(); };
  $("#fDataAte").onchange = ev => { st.filtro.ate = ev.target.value; renderContratos(); };
  $("#fOcultarEnc").onchange = ev => { st.filtro.ocultarEnc = ev.target.checked; renderContratos(); };
  $("#btnLimparFiltros").onclick = () => filtrarContratosPor({});
  const selMover = soDoc => {
    const l = arquivosFiltrados().filter(a => a.acao === "MOVER" && (!soDoc || a.prova === "documento"));
    l.forEach(a => st.sel.add(a.rel));
    renderContratos();
    toast(`${l.length} arquivo(s) selecionado(s).`);
  };
  $("#btnSelMover").onclick = () => selMover(false);
  $("#btnSelMoverDoc").onclick = () => selMover(true);
  $$("#barraLote [data-lote]").forEach(b => b.onclick = () => {
    const tipo = b.dataset.lote, itens = itensSelecionados();
    if (tipo === "nada") { st.sel.clear(); renderContratos(); return; }
    if (tipo === "mover") return moverItens(itens);
    if (tipo === "restaurar") return restaurarItens(itens);
    if (tipo === "modelo_novo") return gerarLote(itens);
    if (tipo === "limpar") return ajustar(itens.filter(a => a.ajuste), { limpar: true });
    ajustar(itens.filter(a => !a.em_encerrados), { situacao: tipo }).then(() => { st.sel.clear(); });
  });

  $("#pBusca").oninput = renderPastas;
  $("#pSoComArquivos").onchange = renderPastas;
  let tEmp;
  $("#eBusca").oninput = ev => { clearTimeout(tEmp); tEmp = setTimeout(() => { st.empFiltro.busca = ev.target.value; renderEmpresas(); }, 180); };
  $("#eFiltro").onchange = ev => { st.empFiltro.tipo = ev.target.value; renderEmpresas(); };

  $("#btnConectar").onclick = async () => {
    const email = $("#cEmail").value.trim(), senha = $("#cSenha").value;
    if (!email || !senha) return toast("Informe e-mail e senha do Contask.", "erro");
    const b = $("#btnConectar");
    b.disabled = true; b.textContent = "Conectando…";
    try {
      const api_ = $("#cApi").value.trim();
      if (api_ && api_ !== st.estado.config.contask_api) await post("/api/config", { contask_api: api_ });
      const r = await post("/api/contask/login", { email, senha });
      $("#cSenha").value = "";
      toast(`Conectado! ${r.total} empresas sincronizadas do Contask.`, "ok");
      document.activeElement?.blur();
      reanalisar();
    } catch (e) { toast(e.message, "erro"); }
    finally { b.disabled = false; b.textContent = "Conectar e sincronizar"; }
  };
  $("#btnSincronizar").onclick = async () => {
    try {
      const r = await post("/api/contask/sincronizar");
      toast(`${r.total} empresas sincronizadas.`, "ok");
      reanalisar();
    } catch (e) { toast(e.message, "erro"); carregarEstado().then(renderConfig); }
  };
  $("#btnSair").onclick = async () => { await post("/api/contask/sair"); toast("Desconectado do Contask."); await carregarEstado(); renderConfig(); };
  $("#btnImportarInicio").onclick = async () => {
    const arq = $("#arqInicio").files[0];
    if (!arq) return toast("Escolha o arquivo .xlsx primeiro.", "erro");
    try {
      const r = await api("/api/inicio-contratos/importar", { method: "POST", body: arq, headers: { "X-Nome-Arquivo": encodeURIComponent(arq.name) } });
      toast(`Planilha importada: ${r.empresas} empresas e ${r.sem_empresa} contratos sem empresa ativa.`, "ok");
      await carregarEstado(); renderConfig();
    } catch (e) { toast(e.message, "erro"); }
  };
  $("#btnImportar").onclick = async () => {
    const arq = $("#arqExcel").files[0];
    if (!arq) return toast("Escolha o arquivo .xlsx primeiro.", "erro");
    try {
      const r = await api("/api/empresas/importar-excel", { method: "POST", body: arq, headers: { "X-Nome-Arquivo": encodeURIComponent(arq.name) } });
      toast(`${r.total} empresas importadas da planilha.`, "ok");
      reanalisar();
    } catch (e) { toast(e.message, "erro"); }
  };
  $("#btnSalvarConfig").onclick = salvarConfig;

  // contratos antigos / novos
  ["#anBusca", "#anFiltro", "#anOrdem", "#anEncerrados"].forEach(s => $(s).oninput = $(s).onchange = renderAntigos);
  ["#noBusca", "#noModelo"].forEach(s => $(s).oninput = $(s).onchange = renderNovos);
  $("#propBusca").oninput = renderPropostas;
  $("#anSelTodos").onchange = ev => { listaAntigos().forEach(x => ev.target.checked ? selAntigos.add(x.a.rel) : selAntigos.delete(x.a.rel)); renderAntigos(); };
  $("#anLimparSel").onclick = () => { selAntigos.clear(); renderAntigos(); };
  $("#anGerarLote").onclick = async () => {
    const idx = Object.fromEntries((st.analise?.arquivos || []).map(a => [a.rel, a]));
    await gerarLote([...selAntigos].map(r => idx[r]).filter(Boolean));
    selAntigos.clear(); renderAntigos();
  };
  $("#noNovo").onclick = () => irPara("modelos");
  // termos aditivos
  $("#adBusca").oninput = renderAditivos;
  $("#adSelTodos").onchange = ev => { pendentesAditivo().forEach(x => ev.target.checked ? selAditivos.add(x.a.rel) : selAditivos.delete(x.a.rel)); renderAditivos(); };
  $("#adLimparSel").onclick = () => { selAditivos.clear(); renderAditivos(); };
  // cobrança / termos de acordo
  $("#cobBusca").oninput = renderCobranca;
  $("#encBusca").oninput = renderEncerramento;
  $("#encEtapa").onchange = renderEncerramento;
  $("#cobEtapa").onchange = renderCobranca;
  $("#cobAbrirPasta").onclick = () => docsCob().length
    ? abrirItem("Cobranças e Acordos", true) : toast("A pasta Cobranças e Acordos é criada quando o primeiro documento for gerado.");
  $("#adGerarLote").onclick = async () => {
    const idx = Object.fromEntries((st.analise?.arquivos || []).map(a => [a.rel, a]));
    await gerarLote([...selAditivos].map(r => idx[r]).filter(Boolean), "aditivo");
    selAditivos.clear(); renderAditivos();
  };

  // modelos de contrato
  $("#btnGerar").onclick = gerarContrato;
  $("#btnBaixarPdf").onclick = () => baixarPdf(mod.id, mod.valores, $("#btnBaixarPdf"));
  $("#btnGerLimpar").onclick = () => mod.editando ? editarGerado(mod.editando) : abrirGerar(mod.id);
  $("#btnGerFechar").onclick = () => { $("#painelGerar").style.display = "none"; mod.editando = null; };
  $("#btnEdSalvar").onclick = salvarModelo;
  $("#btnEdCancelar").onclick = () => { $("#painelEditar").style.display = "none"; };
  $("#btnEdRestaurar").onclick = async () => {
    if (!(await confirmar("Restaurar modelo original", "<p>O texto e os campos voltam a ser os do contrato original da Trivium. As alterações feitas serão perdidas.</p>", "Restaurar", true))) return;
    try { await post("/api/modelos/restaurar", { id: mod.id }); await carregarModelos(); abrirEditar(mod.id); toast("Modelo restaurado.", "ok"); }
    catch (e) { toast(e.message, "erro"); }
  };
  $("#edTexto").oninput = () => { mod.ed.texto = $("#edTexto").value; previaEdicao(); };
  $("#edNegrito").onclick = () => inserirNoTexto("", true);
  $("#edSecao").onclick = () => inserirNoTexto("\n\n## NOVA SEÇÃO\n\n");
  $("#edAssin").onclick = () => inserirNoTexto("\n\n[[ASSINATURAS]]\n\n");
  $("#edAddCampo").onclick = () => { mod.ed.campos.push({ chave: "NOVO_CAMPO", rotulo: "Novo campo", padrao: "" }); renderEdCampos(); };
  const gEmp = $("#gerEmpresa"), gSug = $("#gerSug");
  gEmp.oninput = () => {
    const t = norm(gEmp.value).trim(), dig = gEmp.value.replace(/\D/g, "");
    if (t.length < 2) { gSug.classList.remove("on"); return; }
    const res = st.empresas.filter(x => norm(x.nome + " " + x.fantasia + " " + x.num).includes(t) || (dig.length >= 4 && (x.cnpj || "").includes(dig))).slice(0, 30);
    gSug.innerHTML = res.map(x => `<button data-id="${esc(x.id)}">${esc(x.nome)} ${stTag(x.status)}<br><span class="mini">${x.num ? "Nº " + esc(x.num) + " · " : ""}${esc(x.cnpj_fmt || "")}</span></button>`).join("")
      || `<div class="mini" style="padding:8px">Nenhuma empresa encontrada — preencha os campos à mão.</div>`;
    gSug.classList.add("on");
    $$("button", gSug).forEach(b => b.onclick = () => {
      gSug.classList.remove("on"); gEmp.value = "";
      escolherEmpresaGerar(b.dataset.id);
    });
  };

  $("#btnAutSync").onclick = sincronizarAutentique;
  let tAut;
  $("#aBusca").oninput = ev => { clearTimeout(tAut); tAut = setTimeout(() => { autFiltro.busca = ev.target.value; renderAutentique(); }, 180); };
  $("#aFiltro").onchange = ev => { autFiltro.tipo = ev.target.value; renderAutentique(); };
  $("#aSoNossas").onchange = async ev => {
    try {
      await post("/api/config", { autentique_somente_nossas: ev.target.checked });
      toast(ev.target.checked ? "Autentique: só empresas nossas." : "Autentique: todos os documentos.", "ok");
      document.activeElement?.blur();
      reanalisar();
    } catch (e) { toast(e.message, "erro"); }
  };
  $("#btnAutConectar").onclick = async () => {
    const b = $("#btnAutConectar");
    b.disabled = true; b.textContent = "Conectando…";
    try {
      const r = await post("/api/autentique/conectar", { chave: $("#aChave").value.trim(), pasta: $("#aPasta").value.trim() });
      $("#aChave").value = "";
      toast(`Autentique conectado: ${r.total} documentos${r.pasta ? " da pasta " + r.pasta : ""}.`, "ok");
      document.activeElement?.blur();
      setTimeout(acompanhar, 300);
    } catch (e) { toast(e.message, "erro"); }
    finally { b.disabled = false; b.textContent = "Conectar e sincronizar"; }
  };
  $("#btnAutSair").onclick = async () => {
    if (!(await confirmar("Remover chave do Autentique", "<p>A chave será apagada deste computador. Os dados já sincronizados continuam visíveis.</p>", "Remover"))) return;
    await post("/api/autentique/desconectar"); toast("Chave removida."); await carregarEstado(); renderConfig(); renderAutentique();
  };
}

/* ------------------------------------------------------------ início */
(async function iniciar() {
  ligarEventos();
  try {
    await carregarTudo();
    if (!st.estado.acesso_local && !nomeUsuario()) { await perguntarNome(); await carregarEstado(); }
    if (st.estado.analise.rodando) acompanhar();
  } catch (e) {
    toast("Não foi possível falar com o servidor: " + e.message, "erro");
  }
  // mantém o estado em dia (ex.: análise disparada por outra aba)
  setInterval(() => { if (!st.estado?.analise?.rodando) acompanhar().catch(() => {}); }, 15000);
})();
