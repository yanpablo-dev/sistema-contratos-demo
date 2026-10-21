"""Sistema de Gestão de Contratos - Demo

Servidor local (só aceita conexões deste computador). Abra com "Iniciar Sistema.bat"
ou rode:  python servidor.py   e acesse http://127.0.0.1:8765
"""
import io
import json
import re
import mimetypes
import shutil
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nucleo import analise, autentique, cnpj, config, empresas, inicio_contratos, modelos, movimentacao  # noqa: E402
from nucleo.util import formatar_cnpj, normalizar, so_digitos  # noqa: E402
from nucleo.config import PASTA_WEB  # noqa: E402

SESSAO = {"token": None, "email": None, "desde": None}
MODO = {"rede": False, "enderecos": []}
USUARIO = os.environ.get("USERNAME") or os.environ.get("USER") or "desconhecido"


def _status_empresas():
    d = empresas.carregar()
    por_status = {}
    for e in d.get("empresas") or []:
        por_status[e.get("status")] = por_status.get(e.get("status"), 0) + 1
    return {"atualizado_em": d.get("atualizado_em"), "fonte": d.get("fonte"),
            "total": len(d.get("empresas") or []), "por_status": por_status}


def _unidades_rede():
    """Mapa das unidades de rede (ex.: Z: -> \\\\servidor\\pasta$) via 'net use'."""
    try:
        saida = subprocess.run(["net", "use"], capture_output=True, text=True, timeout=10,
                               encoding="cp850", errors="ignore").stdout
    except Exception:
        return {}
    mapa = {}
    for linha in saida.splitlines():
        m = re.search(r"\s([A-Za-z]:)\s+(\\\\\S.*?)\s{2,}", linha + "  ")
        if m:
            mapa[m.group(1).upper()] = m.group(2).strip()
    return mapa


UNIDADES = {}


def _caminho_rede(caminho):
    """Converte Z:\\... no caminho de rede, que funciona em qualquer computador."""
    unidade = caminho[:2].upper()
    if unidade in UNIDADES:
        return UNIDADES[unidade] + caminho[2:]
    return caminho


def _status_autentique():
    d = autentique.carregar()
    por_status = {}
    for doc in d.get("documentos") or []:
        por_status[doc["status"]] = por_status.get(doc["status"], 0) + 1
    pasta = d.get("pasta") or {}
    return {"tem_chave": bool(autentique.ler_chave()), "atualizado_em": d.get("atualizado_em"),
            "total": len(d.get("documentos") or []), "por_status": por_status,
            "pasta_nome": pasta.get("name") if isinstance(pasta, dict) else None,
            "pastas": d.get("pastas") or []}


def _sincronizar_autentique(chave, pasta):
    docs, escolhida, pastas = autentique.baixar_documentos(chave, pasta)
    info = autentique.salvar_cache(docs, escolhida or {"id": pasta, "name": pasta}, pastas)
    analise.iniciar(config.carregar())
    return {"ok": True, "total": len(docs), "pasta": (escolhida or {}).get("name"), "atualizado_em": info["atualizado_em"]}


def _empresa_por_id(eid):
    return next((e for e in empresas.carregar().get("empresas", []) if e["id"] == eid), None)


def _chave_contratante(vals):
    cnpj = so_digitos(vals.get("CNPJ"))
    return cnpj if len(cnpj) in (11, 14) else normalizar(vals.get("RAZAO_SOCIAL"))


def _sugestao_modelo(id_, empresa_id=None, rel=None):
    """Valores iniciais do formulário: Contask + dados lembrados de contratos anteriores."""
    vals = {}
    item = _itens_por_rel([rel])[0] if rel else {}
    emp = _empresa_por_id(empresa_id) if empresa_id else None
    if not emp and item.get("empresa"):
        emp = _empresa_por_id(item["empresa"]["id"]) or item["empresa"]
    if emp:
        vals["RAZAO_SOCIAL"] = emp.get("nome") or ""
        vals["CNPJ"] = formatar_cnpj(emp.get("cnpj"))
        if emp.get("num"):
            vals["NUMERO_CONTRATO"] = str(emp["num"])  # nº da empresa no Contask
    elif item.get("nome"):  # PDF sem empresa no Contask: usa o nome do arquivo como ponto de partida
        base = os.path.splitext(item["nome"])[0]
        base = re.sub(r"\s+\d+$|\[assinado\]|\(\d+\)", "", base, flags=re.I)
        vals["RAZAO_SOCIAL"] = re.sub(r"^(contrato( de)?( presta[çc][ãa]o)?( de servi[çc]os)?( cont[áa]beis)?\s*-?\s*)", "",
                                      base, flags=re.I).strip()
        cnpjs = item.get("cnpjs_cliente") or []
        if cnpjs:
            vals["CNPJ"] = cnpjs[0]
    lembrado = modelos.contratante(_chave_contratante(vals), id_) if vals else {}
    for k, v in lembrado.items():
        if k not in ("RAZAO_SOCIAL", "CNPJ") or not vals.get(k):
            vals[k] = v
    if id_ in modelos.IDS_PROPOSTA:
        vals["NUMERO_PROPOSTA"] = _proximo_numero_proposta()
    return {"valores": vals, "empresa": emp, "origem": item if rel else None}


def _proximo_numero_proposta():
    """Próximo nº de proposta do ano ('048 / 2026'), contando as propostas já geradas pelo sistema."""
    ano = datetime.now().year
    usados = [int(m.group(1)) for h in modelos.historico() if h.get("modelo_id") in modelos.IDS_PROPOSTA
              for m in [re.match(r"\s*(\d+)\s*/\s*(\d{4})", (h.get("valores") or {}).get("NUMERO_PROPOSTA") or "")]
              if m and int(m.group(2)) == ano]
    return f"{max(usados) + 1:03d} / {ano}" if usados else ""


def _completar_por_cnpj(vals):
    """Completa razão social (nome completo da Receita), endereço e representante pelo CNPJ."""
    if len(so_digitos(vals.get("CNPJ"))) != 14:
        return vals
    try:
        info = cnpj.consultar(vals["CNPJ"])
    except cnpj.ErroCnpj:
        return vals
    if info.get("razao_social"):
        vals["RAZAO_SOCIAL"] = info["razao_social"]
    if info.get("endereco") and not vals.get("ENDERECO"):
        vals["ENDERECO"] = info["endereco"]
    if info.get("socio_administrador") and not vals.get("REPRESENTANTE"):
        vals["REPRESENTANTE"] = info["socio_administrador"]
    return vals


def _gerar_contrato(id_, brutos, cfg, usuario, origem_rel=None, mover_antigo=False, empresa_id=None, com_pdf=False):
    m = modelos.carregar(id_)
    vals, faltando = modelos.preparar_valores(m, brutos)
    pasta = os.path.join(cfg["pasta_raiz"], cfg.get("pasta_novos_contratos") or "")
    if id_ in modelos.IDS_COBRANCA:  # cobranças, notificações e acordos ficam numa subpasta própria
        pasta = os.path.join(cfg["pasta_raiz"], modelos.PASTA_COBRANCA)
    elif id_ in modelos.IDS_PROPOSTA:
        pasta = os.path.join(cfg["pasta_raiz"], modelos.PASTA_PROPOSTAS)
    destino = modelos.salvar_docx(m, vals, pasta)
    rel = os.path.relpath(destino, cfg["pasta_raiz"])
    rel_pdf, erro_pdf = None, None
    if com_pdf:
        try:
            rel_pdf = os.path.relpath(modelos.salvar_pdf(m, vals, destino), cfg["pasta_raiz"])
        except (modelos.ErroModelo, OSError) as e:
            erro_pdf = str(e)
    modelos.lembrar_contratante(_chave_contratante(vals), vals, id_)
    movido = None
    if mover_antigo and origem_rel:
        item = _itens_por_rel([origem_rel])[0]
        item = dict(item, motivo=f"Substituído pelo novo modelo: {os.path.basename(destino)}")
        r = movimentacao.executar([item], cfg, usuario, "ENCERRAR")[0]
        movido = r
    modelos.registrar({"id": modelos.novo_id(), "data": datetime.now().isoformat(timespec="seconds"),
                       "usuario": usuario, "modelo": m["nome"], "modelo_id": id_,
                       "empresa": vals.get("RAZAO_SOCIAL"), "cnpj": vals.get("CNPJ"), "empresa_id": empresa_id,
                       "arquivo": rel, "arquivo_pdf": rel_pdf, "valores": vals,
                       "substituiu": origem_rel if movido and movido.get("ok") else None,
                       "faltando": faltando})
    return {"ok": True, "arquivo": rel, "arquivo_pdf": rel_pdf, "erro_pdf": erro_pdf, "faltando": faltando,
            "movido": movido}


def _editar_contrato(hist_id, brutos, cfg, usuario, com_pdf=True):
    """Regrava um contrato já gerado (mesmo Word e PDF) com os valores alterados.
    A versão anterior fica guardada em dados/versoes_contratos."""
    reg = next((h for h in modelos.historico() if h.get("id") == hist_id), None)
    if not reg:
        raise modelos.ErroModelo("Contrato não encontrado no histórico.")
    m = modelos.carregar(reg["modelo_id"])
    vals, faltando = modelos.preparar_valores(m, brutos)
    docx = os.path.join(cfg["pasta_raiz"], reg["arquivo"])
    pdf = os.path.join(cfg["pasta_raiz"], reg["arquivo_pdf"]) if reg.get("arquivo_pdf") else os.path.splitext(docx)[0] + ".pdf"
    novo_docx = modelos.gerar_docx(m, vals)  # gera tudo antes de mexer nos arquivos
    novo_pdf, erro_pdf = None, None
    if com_pdf or reg.get("arquivo_pdf"):
        try:
            novo_pdf = modelos.gerar_pdf(m, vals)
        except (modelos.ErroModelo, OSError) as e:
            erro_pdf = str(e)
    # guarda a versão anterior
    pasta_ver = os.path.join(modelos.PASTA_DADOS, "versoes_contratos")
    os.makedirs(pasta_ver, exist_ok=True)
    carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    for caminho in (docx, pdf):
        if os.path.exists(caminho):  # nome curto: o Windows não aceita caminhos com mais de 260 letras
            base, ext = os.path.splitext(os.path.basename(caminho))
            shutil.copy2(caminho, os.path.join(pasta_ver, f"{carimbo} - {base[:70].strip()}{ext}"))
    try:
        os.makedirs(os.path.dirname(docx), exist_ok=True)
        with open(docx, "wb") as f:
            f.write(novo_docx)
        if novo_pdf:
            with open(pdf, "wb") as f:
                f.write(novo_pdf)
    except PermissionError:
        raise modelos.ErroModelo("O arquivo está aberto em outro programa (Word ou leitor de PDF). Feche-o e tente de novo.")
    modelos.lembrar_contratante(_chave_contratante(vals), vals, reg["modelo_id"])
    edicoes = (reg.get("edicoes") or []) + [{"data": datetime.now().isoformat(timespec="seconds"), "usuario": usuario}]
    modelos.atualizar_registro(hist_id, {"valores": vals, "faltando": faltando, "empresa": vals.get("RAZAO_SOCIAL"),
                                         "cnpj": vals.get("CNPJ"), "edicoes": edicoes,
                                         "arquivo_pdf": os.path.relpath(pdf, cfg["pasta_raiz"]) if novo_pdf else reg.get("arquivo_pdf")})
    return {"ok": True, "arquivo": reg["arquivo"], "arquivo_pdf": os.path.relpath(pdf, cfg["pasta_raiz"]) if novo_pdf else reg.get("arquivo_pdf"),
            "erro_pdf": erro_pdf, "faltando": faltando, "editado": True}


def _itens_por_rel(rels):
    res = analise.ESTADO.resultado or {}
    idx = {a["rel"]: a for a in res.get("arquivos", [])}
    return [idx.get(r, {"rel": r}) for r in rels]


def _exportar_xlsx():
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    res = analise.ESTADO.resultado or {}
    wb = openpyxl.Workbook()

    def planilha(ws, cab, linhas, larguras):
        ws.append(cab)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F5E4B")
            c.alignment = Alignment(vertical="center")
        for lin in linhas:
            ws.append(lin)
        for i, w in enumerate(larguras, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    ws = wb.active
    ws.title = "Contratos"
    linhas = []
    for a in res.get("arquivos", []):
        e = a.get("empresa") or {}
        linhas.append([a["situacao_rotulo"], a["acao"], a["nome"], a["pasta"] or "(raiz)",
                       e.get("num"), e.get("nome"), e.get("cnpj_fmt"), e.get("status"),
                       e.get("inicio_contrato"), e.get("data_status"), a.get("confianca"), a.get("metodo"),
                       a.get("contratante"), ", ".join(a.get("cnpjs_cliente") or []), a.get("data_texto"),
                       (a.get("criado") or "")[:10], (a.get("modificado") or "")[:10], a["motivo"]])
    planilha(ws, ["Situação", "Ação sugerida", "Arquivo", "Pasta", "Nº Empresa", "Empresa", "CNPJ",
                  "Status Contask", "Início contrato", "Data do status", "Confiança", "Identificado por",
                  "Contratante (texto)", "CNPJ no documento", "Data no contrato", "Criado em",
                  "Modificado em", "Motivo"], linhas,
             [26, 14, 60, 45, 10, 45, 20, 14, 14, 14, 10, 28, 40, 22, 14, 12, 12, 80])

    ws2 = wb.create_sheet("Pastas")
    linhas = []
    for p in res.get("pastas", []):
        s = p.get("situacoes", {})
        linhas.append(["    " * p["nivel"] + p["nome"], p["rel"] or "(raiz)", (p.get("criada") or "")[:10],
                       (p.get("modificada") or "")[:10], p["arquivos_diretos"], p["arquivos_total"],
                       (p.get("mais_antigo") or "")[:10], (p.get("mais_recente") or "")[:10],
                       s.get("ATIVA", 0) + s.get("SUSPENSA", 0), s.get("ENCERRADA", 0) + s.get("NAO_CLIENTE", 0),
                       s.get("REVISAR", 0) + s.get("SEM_IDENTIFICACAO", 0), round(p["tamanho"] / 1048576, 2)])
    planilha(ws2, ["Pasta", "Caminho", "Criada em", "Modificada em", "Arquivos na pasta", "Arquivos (total)",
                   "Arquivo mais antigo", "Arquivo mais recente", "Empresas nossas", "A mover",
                   "A revisar", "Tamanho (MB)"], linhas, [50, 70, 12, 14, 12, 12, 14, 14, 12, 10, 10, 12])

    ws3 = wb.create_sheet("Empresas")
    por_emp = res.get("contratos_por_empresa", {})
    linhas = []
    for e in empresas.carregar().get("empresas", []):
        d = por_emp.get(e["id"], {})
        linhas.append([e.get("num"), e.get("nome"), e.get("cnpj_fmt"), e.get("status"), e.get("inicio_contrato"),
                       e.get("data_status"), e.get("regime"), e.get("uf"), e.get("resp_contabil"),
                       d.get("ativos", 0), d.get("encerrados", 0), (d.get("ultimo") or "")[:10]])
    planilha(ws3, ["Nº", "Razão social", "CNPJ", "Status", "Início contrato", "Data do status", "Regime", "UF",
                   "Resp. contábil", "Contratos na pasta ativa", "Contratos em Encerrado", "Último arquivo"],
             linhas, [8, 50, 20, 12, 14, 14, 12, 6, 30, 14, 14, 14])

    ws5 = wb.create_sheet("Autentique")
    status_rot = {"ASSINADO": "Assinado", "PARCIAL": "Assinatura parcial", "PENDENTE": "Aguardando", "RECUSADO": "Recusado"}
    linhas = []
    for d in res.get("autentique", []):
        e = d.get("empresa") or {}
        linhas.append([d["nome"], status_rot.get(d["status"], d["status"]), f'{d["qtd_assinaram"]}/{d["qtd_signatarios"]}',
                       (d.get("criado_em") or "")[:10], (d.get("assinado_em") or "")[:10], e.get("num"), e.get("nome"),
                       e.get("status"), "; ".join(f'{s.get("nome")} ({(s.get("assinado_em") or "pendente")[:10]})' for s in d["assinaturas"]),
                       "; ".join(x["rel"] for x in d.get("arquivos_locais") or []) or "NÃO ESTÁ NA PASTA",
                       f'https://painel.autentique.com.br/documentos/{d["id"]}'])
    planilha(ws5, ["Documento", "Status assinatura", "Assinaram", "Enviado em", "Assinado em", "Nº Empresa", "Empresa",
                   "Status Contask", "Signatários", "PDF na pasta", "Link"], linhas,
             [55, 18, 10, 12, 12, 10, 45, 14, 70, 60, 70])

    ws4 = wb.create_sheet("Movimentações")
    linhas = [[m["data"].replace("T", " "), m["usuario"], m["acao"], m.get("empresa"), m["origem"], m["destino"],
               "Sim" if m.get("desfeito") else "Não", m.get("motivo")] for m in movimentacao.historico()]
    planilha(ws4, ["Data", "Usuário", "Ação", "Empresa", "Origem", "Destino", "Desfeito?", "Motivo"],
             linhas, [18, 16, 12, 40, 70, 70, 10, 80])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class Manipulador(BaseHTTPRequestHandler):
    server_version = "ContratosDemo/1.0"

    def log_message(self, fmt, *args):  # silencia o log de cada requisição
        pass

    # ----------------------------------------------------------- respostas
    def _json(self, dados, codigo=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _erro(self, msg, codigo=400):
        self._json({"erro": msg}, codigo)

    def _corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _corpo_json(self):
        bruto = self._corpo()
        return json.loads(bruto.decode("utf-8")) if bruto else {}

    def _origem_ok(self):
        """Bloqueia chamadas vindas de outros sites (proteção CSRF básica)."""
        origem = self.headers.get("Origin")
        if not origem:
            return True
        host = urlparse(origem).hostname
        meu_host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("127.0.0.1", "localhost") or host == meu_host

    def _local(self):
        return self.client_address[0] in ("127.0.0.1", "::1")

    def _usuario(self):
        """Nome de quem está usando: o próprio Windows (local) ou o nome informado na tela (rede)."""
        if self._local():
            return USUARIO
        nome = unquote(self.headers.get("X-Usuario") or "").strip()[:60] or "sem nome"
        return f"{nome} ({self.client_address[0]})"

    def _servir_arquivo(self, rel):
        cfg = config.carregar()
        raiz = os.path.abspath(cfg["pasta_raiz"])
        alvo = os.path.abspath(os.path.join(raiz, rel or ""))
        if not alvo.startswith(raiz + os.sep) or not os.path.isfile(alvo):
            return self._erro("Arquivo não encontrado.", 404)
        tipo = mimetypes.guess_type(alvo)[0] or "application/octet-stream"
        nome = os.path.basename(alvo)
        with open(alvo, "rb") as f:
            dados = f.read()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        disp = "inline" if tipo in ("application/pdf",) or tipo.startswith(("image/", "text/")) else "attachment"
        self.send_header("Content-Disposition", f"{disp}; filename*=UTF-8''{quote(nome)}")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    # ----------------------------------------------------------------- GET
    def do_GET(self):
        url = urlparse(self.path)
        rota = url.path
        try:
            if rota == "/api/estado":
                cfg = config.carregar()
                est = analise.ESTADO
                return self._json({
                    "usuario": self._usuario(),
                    "acesso_local": self._local(),
                    "modo_rede": MODO["rede"],
                    "enderecos_rede": MODO["enderecos"],
                    "config": cfg,
                    "empresas": _status_empresas(),
                    "contask_conectado": bool(SESSAO["token"]),
                    "contask_email": SESSAO["email"],
                    "autentique": _status_autentique(),
                    "inicio_contratos": inicio_contratos.resumo(),
                    "analise": {"rodando": est.rodando, "progresso": est.progresso, "erro": est.erro,
                                "gerado_em": (est.resultado or {}).get("gerado_em")},
                    "pastas_topo": sorted(
                        d for d in os.listdir(cfg["pasta_raiz"])
                        if os.path.isdir(os.path.join(cfg["pasta_raiz"], d))
                    ) if os.path.isdir(cfg["pasta_raiz"]) else [],
                })
            if rota == "/api/analise":
                return self._json(analise.ESTADO.resultado or {})
            if rota == "/api/arquivo":
                return self._servir_arquivo(parse_qs(url.query).get("rel", [""])[0])
            if rota == "/api/modelos":
                return self._json({"modelos": modelos.listar()})
            if rota == "/api/modelos/logo":
                with open(os.path.join(modelos.PASTA_MODELOS, "logo.jpg"), "rb") as f:
                    dados = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(dados)))
                self.send_header("Cache-Control", "max-age=3600")
                self.end_headers()
                self.wfile.write(dados)
                return
            if rota == "/api/modelos/historico":
                hist = list(reversed(modelos.historico()))
                raiz = config.carregar()["pasta_raiz"]
                for h in hist:  # a pasta de cobranças fica fora da análise: confere aqui se os arquivos existem
                    if h.get("modelo_id") in modelos.IDS_COBRANCA + modelos.IDS_PROPOSTA:
                        h["existe"] = os.path.exists(os.path.join(raiz, h.get("arquivo") or ""))
                        h["existe_pdf"] = bool(h.get("arquivo_pdf")) and os.path.exists(os.path.join(raiz, h["arquivo_pdf"]))
                return self._json(hist)
            if rota == "/api/cnpj":
                try:
                    return self._json(cnpj.consultar(parse_qs(url.query).get("cnpj", [""])[0]))
                except cnpj.ErroCnpj as e:
                    return self._erro(str(e), 502)
            if rota == "/api/modelos/sugestao":
                q = parse_qs(url.query)
                return self._json(_sugestao_modelo(q.get("id", ["contabil"])[0], q.get("empresa_id", [None])[0],
                                                   q.get("rel", [None])[0]))
            if rota == "/api/empresas":
                return self._json(empresas.carregar())
            if rota == "/api/movimentacoes":
                return self._json(list(reversed(movimentacao.historico())))
            if rota == "/api/exportar":
                dados = _exportar_xlsx()
                nome = f"Relatorio_Contratos_{datetime.now():%Y-%m-%d_%H%M}.xlsx"
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", f'attachment; filename="{nome}"')
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)
                return
            if rota == "/api/exportar-inicio":
                dados, nome = inicio_contratos.exportar(analise.ESTADO.resultado, empresas.carregar().get("empresas") or [],
                                                        config.carregar())
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", f'attachment; filename="{nome}"')
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)
                return
            return self._estatico(rota)
        except Exception as e:
            return self._erro(f"{type(e).__name__}: {e}", 500)

    def _estatico(self, rota):
        if rota in ("", "/"):
            rota = "/index.html"
        caminho = os.path.abspath(os.path.join(PASTA_WEB, rota.lstrip("/")))
        if not caminho.startswith(os.path.abspath(PASTA_WEB)) or not os.path.isfile(caminho):
            return self._erro("Não encontrado", 404)
        with open(caminho, "rb") as f:
            dados = f.read()
        tipo = mimetypes.guess_type(caminho)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo.endswith("javascript"):
            tipo += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(dados)

    # ---------------------------------------------------------------- POST
    def do_POST(self):
        if not self._origem_ok():
            return self._erro("Origem não permitida", 403)
        rota = urlparse(self.path).path
        try:
            cfg = config.carregar()
            if rota == "/api/analisar":
                iniciou = analise.iniciar(cfg)
                return self._json({"ok": True, "iniciou": iniciou})

            if rota == "/api/contask/login":
                d = self._corpo_json()
                email, senha = (d.get("email") or "").strip(), d.get("senha") or ""
                if not email or not senha:
                    return self._erro("Informe e-mail e senha do Contask.")
                token = empresas.login(cfg["contask_api"], email, senha)
                SESSAO.update(token=token, email=email, desde=datetime.now().isoformat(timespec="seconds"))
                config.salvar({"contask_email": email})
                lista = empresas.baixar_empresas(cfg["contask_api"], token)
                info = empresas.salvar(lista, f"Contask (API) - {email}")
                return self._json({"ok": True, "total": len(lista), "atualizado_em": info["atualizado_em"]})

            if rota == "/api/contask/sincronizar":
                if not SESSAO["token"]:
                    return self._erro("Conecte-se ao Contask primeiro (Configurações).", 401)
                try:
                    lista = empresas.baixar_empresas(cfg["contask_api"], SESSAO["token"])
                except empresas.ErroContask:
                    SESSAO.update(token=None)
                    raise
                info = empresas.salvar(lista, f"Contask (API) - {SESSAO['email']}")
                return self._json({"ok": True, "total": len(lista), "atualizado_em": info["atualizado_em"]})

            if rota == "/api/contask/sair":
                SESSAO.update(token=None, email=None, desde=None)
                return self._json({"ok": True})

            if rota == "/api/autentique/conectar":
                d = self._corpo_json()
                chave = (d.get("chave") or "").strip() or autentique.ler_chave()
                if not chave:
                    return self._erro("Cole a chave de API do Autentique.")
                pasta = (d.get("pasta") or cfg.get("autentique_pasta") or "").strip()
                autentique.testar(chave)  # valida a chave antes de salvar
                autentique.salvar_chave(chave)
                config.salvar({"autentique_pasta": pasta})
                return self._json(_sincronizar_autentique(chave, pasta))

            if rota == "/api/autentique/sincronizar":
                chave = autentique.ler_chave()
                if not chave:
                    return self._erro("Configure a chave do Autentique primeiro (Configurações).", 401)
                return self._json(_sincronizar_autentique(chave, cfg.get("autentique_pasta")))

            if rota == "/api/autentique/desconectar":
                autentique.salvar_chave(None)
                return self._json({"ok": True})

            if rota == "/api/autentique/baixar":
                d = self._corpo_json()
                chave = autentique.ler_chave()
                if not chave:
                    return self._erro("Configure a chave do Autentique primeiro.", 401)
                doc = next((x for x in autentique.carregar()["documentos"] if x["id"] == d.get("id")), None)
                if not doc:
                    return self._erro("Documento não encontrado. Sincronize o Autentique.", 404)
                url = doc.get("url_assinado") or doc.get("url_original")
                if not url:
                    return self._erro("O Autentique não informou o arquivo deste documento.")
                nome = re.sub(r'[\\/:*?"<>|]+', " ", doc["nome"]).strip() or doc["id"]
                if not nome.lower().endswith(".pdf"):
                    nome += ".pdf"
                if doc.get("status") == "ASSINADO" and "[assinado]" not in nome.lower():
                    nome = nome[:-4] + " [assinado].pdf"
                destino = autentique.baixar_pdf(chave, url, os.path.join(cfg["pasta_raiz"], nome))
                analise.iniciar(cfg)
                return self._json({"ok": True, "arquivo": os.path.relpath(destino, cfg["pasta_raiz"])})

            if rota == "/api/modelos/previa":
                d = self._corpo_json()
                m = modelos.carregar(d.get("id"))
                if d.get("texto") is not None:  # prévia de um modelo em edição (ainda não salvo)
                    m = dict(m, texto=d["texto"], campos=d.get("campos") or m["campos"])
                vals, faltando = modelos.preparar_valores(m, d.get("valores") or {})
                return self._json({"valores": vals, "faltando": faltando, "nome_arquivo": modelos.nome_arquivo(m, vals)})

            if rota == "/api/modelos/pdf":
                # baixa o PDF direto no navegador, sem salvar nada na pasta
                d = self._corpo_json()
                m = modelos.carregar(d.get("id"))
                vals, _ = modelos.preparar_valores(m, d.get("valores") or {})
                dados = modelos.gerar_pdf(m, vals)
                nome = modelos.nome_arquivo(m, vals)[:-5] + ".pdf"
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(nome)}")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)
                return

            if rota == "/api/modelos/salvar":
                d = self._corpo_json()
                return self._json({"ok": True, "modelo": modelos.salvar(d.get("id"), d.get("texto") or "",
                                                                         d.get("campos") or [], self._usuario())})

            if rota == "/api/modelos/restaurar":
                d = self._corpo_json()
                return self._json({"ok": True, "modelo": modelos.restaurar(d.get("id"))})

            if rota == "/api/modelos/gerar":
                d = self._corpo_json()
                if analise.ESTADO.rodando and d.get("mover_antigo"):
                    return self._erro("Aguarde a análise terminar.")
                res = _gerar_contrato(d.get("id"), d.get("valores") or {}, cfg, self._usuario(),
                                      d.get("origem_rel"), bool(d.get("mover_antigo")), d.get("empresa_id"),
                                      bool(d.get("com_pdf")))
                analise.iniciar(cfg)
                return self._json(res)

            if rota == "/api/modelos/editar":
                d = self._corpo_json()
                res = _editar_contrato(d.get("hist_id"), d.get("valores") or {}, cfg, self._usuario(), bool(d.get("com_pdf")))
                analise.iniciar(cfg)
                return self._json(res)

            if rota == "/api/modelos/gerar-lote":
                d = self._corpo_json()
                if analise.ESTADO.rodando:
                    return self._erro("Aguarde a análise terminar.")
                comuns = {k: v for k, v in (d.get("valores_comuns") or {}).items() if v not in (None, "")}
                resultados = []
                for rel in d.get("rels") or []:
                    sug = _sugestao_modelo(d.get("id"), rel=rel)
                    vals = _completar_por_cnpj({**sug["valores"], **comuns})
                    try:
                        r = _gerar_contrato(d.get("id"), vals, cfg, self._usuario(), rel,
                                            bool(d.get("mover_antigos")), (sug.get("empresa") or {}).get("id"),
                                            bool(d.get("com_pdf")))
                        resultados.append({"rel": rel, **r})
                    except (modelos.ErroModelo, OSError) as e:
                        resultados.append({"rel": rel, "ok": False, "erro": str(e)})
                analise.iniciar(cfg)
                return self._json({"ok": True, "resultados": resultados})

            if rota == "/api/empresas/importar-excel":
                conteudo = self._corpo()
                if not conteudo:
                    return self._erro("Arquivo vazio.")
                lista = empresas.importar_excel(conteudo)
                nome = unquote(self.headers.get("X-Nome-Arquivo") or "planilha")
                info = empresas.salvar(lista, f"Planilha {nome}")
                return self._json({"ok": True, "total": len(lista), "atualizado_em": info["atualizado_em"]})

            if rota == "/api/inicio-contratos/importar":
                conteudo = self._corpo()
                if not conteudo:
                    return self._erro("Arquivo vazio.")
                nome = unquote(self.headers.get("X-Nome-Arquivo") or "planilha")
                return self._json({"ok": True, **inicio_contratos.importar(conteudo, nome, self._usuario())})

            if rota in ("/api/mover", "/api/restaurar"):
                d = self._corpo_json()
                rels = d.get("rels") or []
                if not rels:
                    return self._erro("Nenhum arquivo selecionado.")
                if analise.ESTADO.rodando:
                    return self._erro("Aguarde a análise terminar.")
                acao = "ENCERRAR" if rota == "/api/mover" else "RESTAURAR"
                res = movimentacao.executar(_itens_por_rel(rels), cfg, self._usuario(), acao)
                analise.iniciar(cfg)  # reanalisa para refletir os novos caminhos
                return self._json({"ok": True, "resultados": res})

            if rota == "/api/desfazer":
                d = self._corpo_json()
                res = movimentacao.desfazer(set(d.get("ids") or []), cfg, self._usuario())
                analise.iniciar(cfg)
                return self._json({"ok": True, "resultados": res})

            if rota == "/api/ajuste":
                d = self._corpo_json()
                chaves = d.get("chaves") or ([d["chave"]] if d.get("chave") else [])
                if not chaves:
                    return self._erro("Arquivo não informado.")
                for ch in chaves:
                    if d.get("limpar"):
                        analise.salvar_ajuste(ch, None, self._usuario())
                    else:
                        analise.salvar_ajuste(ch, {"empresa_id": d.get("empresa_id"),
                                                   "situacao": d.get("situacao"), "obs": d.get("obs")}, self._usuario())
                analise.iniciar(cfg)
                return self._json({"ok": True})

            if rota == "/api/abrir":
                d = self._corpo_json()
                alvo = os.path.abspath(os.path.join(cfg["pasta_raiz"], d.get("rel") or ""))
                raiz = os.path.abspath(cfg["pasta_raiz"])
                if not alvo.startswith(raiz) or not os.path.exists(alvo):
                    return self._erro("Arquivo não encontrado.", 404)
                if not self._local():
                    # outro computador: o arquivo abre no navegador dele; a pasta é informada pelo caminho de rede
                    if d.get("pasta"):
                        pasta = alvo if os.path.isdir(alvo) else os.path.dirname(alvo)
                        return self._json({"ok": True, "caminho": _caminho_rede(pasta)})
                    if os.path.isdir(alvo):
                        return self._json({"ok": True, "caminho": _caminho_rede(alvo)})
                    return self._json({"ok": True, "url": "/api/arquivo?rel=" + quote(d.get("rel") or "")})
                if d.get("pasta"):
                    if os.path.isfile(alvo):
                        subprocess.Popen(["explorer", "/select,", alvo])
                    else:
                        os.startfile(alvo)
                else:
                    os.startfile(alvo)
                return self._json({"ok": True})

            if rota == "/api/config":
                d = self._corpo_json()
                if "pasta_raiz" in d and not os.path.isdir(d["pasta_raiz"]):
                    return self._erro("A pasta raiz informada não existe.")
                novo = config.salvar(d)
                return self._json({"ok": True, "config": novo})

            return self._erro("Rota desconhecida", 404)
        except (empresas.ErroContask, autentique.ErroAutentique) as e:
            return self._erro(str(e), 502)
        except (modelos.ErroModelo, inicio_contratos.ErroPlanilha) as e:
            return self._erro(str(e), 400)
        except json.JSONDecodeError:
            return self._erro("Requisição inválida.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._erro(f"{type(e).__name__}: {e}", 500)


def _ips_locais():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:  # IP usado para sair para a rede
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def main():
    cfg = config.carregar()
    porta = int(cfg.get("porta") or 8765)
    rede = "--rede" in sys.argv
    url = f"http://127.0.0.1:{porta}"
    UNIDADES.update(_unidades_rede())
    try:
        srv = ThreadingHTTPServer(("0.0.0.0" if rede else "127.0.0.1", porta), Manipulador)
    except OSError:
        # já está rodando: só abre o navegador
        print(f"O sistema já está aberto em {url}")
        webbrowser.open(url)
        return
    MODO["rede"] = rede
    MODO["enderecos"] = [f"http://{ip}:{porta}" for ip in _ips_locais()] + [f"http://{socket.gethostname()}:{porta}"]
    print("=" * 64)
    print("  Sistema de Gestão de Contratos - Demo")
    print(f"  Neste computador:   {url}")
    if rede:
        print("  MODO REDE - nos outros computadores, abra no navegador:")
        for e in MODO["enderecos"]:
            print(f"      {e}")
    print(f"  Pasta:     {cfg['pasta_raiz']}")
    print("  Deixe esta janela aberta enquanto usa o sistema.")
    print("  Para encerrar, feche esta janela ou pressione Ctrl+C.")
    print("=" * 64)
    if not analise.ESTADO.resultado:
        analise.iniciar(cfg)
    if "--sem-navegador" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    socket.setdefaulttimeout(None)
    main()
