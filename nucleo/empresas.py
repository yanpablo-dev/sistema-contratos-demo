"""Carteira de empresas: sincronização com o Contask e importação da planilha exportada.

O Contask expõe uma API em http://127.0.0.1:8800:
  POST /login        {email, password} -> {token}
  GET  /company/all  (Authorization: Bearer <token>) -> lista de empresas
Status possíveis: ATIVA, SUSPENSA, BAIXADA, DISTRATO (+ isArchived / ARCHIVED).

A senha nunca é gravada; o token fica só na memória do servidor local.
"""
import io
import json
import urllib.error
import urllib.request
from datetime import datetime

from .config import caminho_dados
from .util import data_iso, formatar_cnpj, ler_json, normalizar, salvar_json, so_digitos

ARQ_EMPRESAS = caminho_dados("empresas.json")


class ErroContask(Exception):
    pass


def _requisicao(url, metodo="GET", corpo=None, token=None, tempo=40):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo)
    req.add_header("Accept", "application/json")
    if dados is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("message")
        except Exception:
            msg = None
        if e.code in (401, 403):
            raise ErroContask(msg or "Acesso negado pelo Contask (login inválido ou sessão expirada).")
        raise ErroContask(msg or f"O Contask respondeu com erro {e.code}.")
    except urllib.error.URLError as e:
        raise ErroContask(f"Não foi possível conectar ao Contask ({url}). Verifique a rede. Detalhe: {e.reason}")
    except TimeoutError:
        raise ErroContask("O Contask demorou demais para responder.")


def login(api, email, senha):
    resp = _requisicao(api.rstrip("/") + "/login", "POST", {"email": email, "password": senha})
    token = (resp or {}).get("token")
    if not token:
        raise ErroContask("O Contask não devolveu um token de acesso.")
    return token


def baixar_empresas(api, token):
    resp = _requisicao(api.rstrip("/") + "/company/all", token=token, tempo=90)
    if isinstance(resp, dict):
        resp = resp.get("data") or resp.get("companies") or resp.get("items") or []
    if not isinstance(resp, list):
        raise ErroContask("Resposta inesperada do Contask ao listar empresas.")
    return [normalizar_empresa_api(e) for e in resp if isinstance(e, dict)]


def _g(d, *chaves):
    for k in chaves:
        v = d.get(k)
        if v not in (None, "", "None"):
            return v
    return None


def _nome_pessoa(v):
    if isinstance(v, dict):
        return v.get("name") or v.get("nome")
    return v if isinstance(v, str) else None


def normalizar_empresa_api(e):
    status = str(_g(e, "status", "situacao") or "").upper()
    arquivada = bool(e.get("isArchived")) or status == "ARCHIVED"
    grupo = e.get("grupo") or e.get("group")
    return {
        "id": str(_g(e, "id", "_id") or _g(e, "num") or ""),
        "num": str(_g(e, "num", "numero") or ""),
        "nome": str(_g(e, "name", "razaoSocial", "razao_social") or "").strip(),
        "fantasia": str(_g(e, "fantasyName", "nomeFantasia", "fantasia", "tradeName") or "").strip(),
        "cnpj": so_digitos(_g(e, "cnpj", "document", "cpfCnpj")),
        "status": "ARQUIVADA" if arquivada and status in ("", "ARCHIVED") else (status or "DESCONHECIDO"),
        "arquivada": arquivada,
        "inicio_contrato": data_iso(_g(e, "contractInit", "inicioContrato")),
        "data_status": data_iso(_g(e, "statusUpdatedAt", "dataStatus")),
        "regime": _g(e, "rule", "regime"),
        "classificacao": _g(e, "classi", "classificacao"),
        "uf": _g(e, "uf"),
        "filial": str(_g(e, "filial") or ""),
        "grupo": _nome_pessoa(grupo) if grupo else (str(e.get("grupoId")) if e.get("grupoId") else None),
        "resp_fiscal": _nome_pessoa(e.get("respFiscal")),
        "resp_dp": _nome_pessoa(e.get("respDp")),
        "resp_contabil": _nome_pessoa(e.get("respContabil")),
    }


COLUNAS_EXCEL = {
    "num": ["numero", "num", "n"],
    "nome": ["razao social", "razao", "nome", "empresa"],
    "fantasia": ["nome fantasia", "fantasia"],
    "cnpj": ["cnpj", "cnpj cpf", "documento"],
    "status": ["status", "situacao"],
    "arquivada": ["arquivado", "arquivada"],
    "inicio_contrato": ["inicio do contrato", "inicio contrato"],
    "data_status": ["data do status", "data status"],
    "regime": ["regime"],
    "classificacao": ["classificacao"],
    "uf": ["uf"],
    "filial": ["filial"],
    "resp_fiscal": ["responsavel fiscal"],
    "resp_dp": ["responsavel dp"],
    "resp_contabil": ["responsavel contabil"],
}


def importar_excel(conteudo):
    """Lê a planilha 'Relatorio_Empresas.xlsx' exportada do Contask (bytes)."""
    try:
        import openpyxl
    except ImportError:
        raise ErroContask("O módulo openpyxl não está instalado (pip install openpyxl).")
    wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    linhas = ws.iter_rows(values_only=True)
    cab = [normalizar(c).lower() for c in next(linhas)]
    idx = {}
    for campo, nomes in COLUNAS_EXCEL.items():
        for i, c in enumerate(cab):
            if c in nomes:
                idx[campo] = i
                break
    if "nome" not in idx:
        raise ErroContask("A planilha não tem a coluna 'Razao Social'.")
    empresas = []
    for lin in linhas:
        def v(campo):
            i = idx.get(campo)
            val = lin[i] if i is not None and i < len(lin) else None
            return None if val in (None, "None", "") else val

        nome = v("nome")
        if not nome:
            continue
        arquivada = str(v("arquivada") or "").strip().lower() in ("sim", "s", "true", "1")
        status = str(v("status") or "ATIVA").upper().strip()
        empresas.append({
            "id": str(v("num") or nome),
            "num": str(v("num") or ""),
            "nome": str(nome).strip(),
            "fantasia": str(v("fantasia") or "").strip(),
            "cnpj": so_digitos(v("cnpj")),
            "status": "ARQUIVADA" if arquivada and status == "ATIVA" else status,
            "arquivada": arquivada,
            "inicio_contrato": data_iso(v("inicio_contrato")),
            "data_status": data_iso(v("data_status")),
            "regime": v("regime"),
            "classificacao": v("classificacao"),
            "uf": v("uf"),
            "filial": str(v("filial") or ""),
            "grupo": None,
            "resp_fiscal": v("resp_fiscal"),
            "resp_dp": v("resp_dp"),
            "resp_contabil": v("resp_contabil"),
        })
    return empresas


def salvar(empresas, fonte):
    for e in empresas:
        e["cnpj_fmt"] = formatar_cnpj(e.get("cnpj"))
    dados = {"atualizado_em": datetime.now().isoformat(timespec="seconds"), "fonte": fonte, "empresas": empresas}
    salvar_json(ARQ_EMPRESAS, dados)
    return dados


def carregar():
    return ler_json(ARQ_EMPRESAS, {"atualizado_em": None, "fonte": None, "empresas": []})
