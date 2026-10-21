"""Integração com o Autentique (assinatura eletrônica).

API GraphQL: POST https://api.autentique.com.br/v2/graphql
Autenticação: header "Authorization: Bearer <chave>". A chave é gerada em
https://painel.autentique.com.br/perfil/api e fica salva só no perfil do Windows
do usuário (%APPDATA%), nunca na pasta compartilhada.
Limite da API: 60 requisições por minuto.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime

from .config import caminho_dados
from .util import ler_json, salvar_json

URL_API = "https://api.autentique.com.br/v2/graphql"
ARQ_DOCS = caminho_dados("autentique.json")
ARQ_CHAVE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ContratosDemo", "autentique.json")


class ErroAutentique(Exception):
    pass


# ------------------------------------------------------------------ chave
def ler_chave():
    return (ler_json(ARQ_CHAVE, {}) or {}).get("chave")


def salvar_chave(chave):
    if chave:
        salvar_json(ARQ_CHAVE, {"chave": chave.strip(), "salva_em": datetime.now().isoformat(timespec="seconds")})
    elif os.path.exists(ARQ_CHAVE):
        os.remove(ARQ_CHAVE)


def id_da_pasta(texto):
    """Aceita o link do painel (…/pastas/<id>) ou o id puro."""
    texto = (texto or "").strip()
    m = re.search(r"/pastas/([0-9a-zA-Z-]+)", texto)
    return m.group(1) if m else texto


# ------------------------------------------------------------------ GraphQL
def _gql(chave, query, variaveis=None, tentativas=3):
    corpo = json.dumps({"query": query, "variables": variaveis or {}}).encode("utf-8")
    for n in range(tentativas):
        req = urllib.request.Request(URL_API, data=corpo, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {chave}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and n < tentativas - 1:  # limite de 60/min
                time.sleep(20)
                continue
            if e.code in (401, 403):
                raise ErroAutentique("Chave de API do Autentique inválida ou sem permissão.")
            raise ErroAutentique(f"O Autentique respondeu com erro {e.code}.")
        except urllib.error.URLError as e:
            raise ErroAutentique(f"Sem conexão com o Autentique: {e.reason}")
        if resp.get("errors"):
            msg = "; ".join(str(x.get("message")) for x in resp["errors"])
            if "unauthenticated" in msg.lower():
                raise ErroAutentique("Chave de API do Autentique inválida.")
            raise ErroAutentique(msg)
        return resp.get("data") or {}
    raise ErroAutentique("Limite de requisições do Autentique atingido; tente em 1 minuto.")


CAMPOS_DOC = """
  id name created_at deleted_at
  files { original signed }
  signatures {
    public_id name email created_at
    action { name }
    link { short_link }
    user { name email }
    viewed { created_at }
    signed { created_at }
    rejected { created_at reason }
  }
"""


def testar(chave):
    q = "query { folders(limit: 100, page: 1, display_children: true) { data { id name path } total } }"
    dados = _gql(chave, q)
    return dados.get("folders", {}).get("data", [])


def listar_pastas(chave):
    pastas, pagina = [], 1
    while pagina <= 20:
        q = """query($p: Int!) { folders(limit: 60, page: $p, display_children: true) {
                 data { id name path created_at } has_more_pages } }"""
        r = _gql(chave, q, {"p": pagina}).get("folders") or {}
        pastas += r.get("data") or []
        if not r.get("has_more_pages"):
            break
        pagina += 1
    return pastas


def _docs_da_pasta(chave, pasta_id, completo=True):
    docs, pagina = [], 1
    campos = CAMPOS_DOC if completo else "id name created_at deleted_at"
    while pagina <= 50:
        q = f"""query($f: UUID!, $p: Int!) {{ documentsByFolder(folder_id: $f, limit: 60, page: $p) {{
                 data {{ {campos} }} has_more_pages }} }}"""
        r = _gql(chave, q, {"f": pasta_id, "p": pagina}).get("documentsByFolder") or {}
        docs += r.get("data") or []
        if not r.get("has_more_pages"):
            break
        pagina += 1
    return docs


def baixar_documentos(chave, pasta):
    """Busca os documentos da pasta configurada. 'pasta' pode ser id, link ou nome."""
    alvo = id_da_pasta(pasta)
    pastas = listar_pastas(chave)
    escolhida = next((p for p in pastas if p["id"] == alvo or p["name"].lower() == alvo.lower()), None)
    pasta_id = escolhida["id"] if escolhida else alvo
    try:
        docs = _docs_da_pasta(chave, pasta_id)
    except ErroAutentique as e:
        if "UUID" in str(e) or "folder" in str(e).lower():
            nomes = ", ".join(p["name"] for p in pastas[:30])
            raise ErroAutentique(f"Pasta '{pasta}' não encontrada pela API. Pastas disponíveis: {nomes}")
        raise
    return [normalizar_doc(d) for d in docs if not d.get("deleted_at")], escolhida, pastas


def _data(x):
    return (x or {}).get("created_at")


def normalizar_doc(d):
    sigs = []
    for s in d.get("signatures") or []:
        acao = ((s.get("action") or {}).get("name") or "").upper()
        user = s.get("user") or {}
        sigs.append({
            "nome": s.get("name") or user.get("name") or s.get("email") or user.get("email"),
            "email": s.get("email") or user.get("email"),
            "acao": acao,
            "visto_em": _data(s.get("viewed")),
            "assinado_em": _data(s.get("signed")),
            "recusado_em": _data(s.get("rejected")),
            "motivo_recusa": (s.get("rejected") or {}).get("reason"),
            "link": (s.get("link") or {}).get("short_link"),
        })
    # quem precisa agir: signatários (ação SIGN) ou, se não houver ação, todos menos o criador
    precisam = [s for s in sigs if s["acao"] in ("SIGN", "APPROVE", "SIGN_AS_A_WITNESS", "RECOGNIZE")] or \
               [s for s in sigs if s["acao"]]
    if any(s["recusado_em"] for s in sigs):
        status = "RECUSADO"
    elif precisam and all(s["assinado_em"] for s in precisam):
        status = "ASSINADO"
    elif any(s["assinado_em"] for s in precisam):
        status = "PARCIAL"
    else:
        status = "PENDENTE"
    datas = [s["assinado_em"] for s in precisam if s["assinado_em"]]
    arquivos = d.get("files") or {}
    return {
        "id": d.get("id"),
        "nome": d.get("name") or "",
        "criado_em": d.get("created_at"),
        "status": status,
        "assinado_em": max(datas) if status == "ASSINADO" and datas else None,
        "assinaturas": sigs,
        "qtd_assinaram": sum(1 for s in precisam if s["assinado_em"]),
        "qtd_signatarios": len(precisam),
        "url_assinado": arquivos.get("signed"),
        "url_original": arquivos.get("original"),
    }


def salvar_cache(docs, pasta, pastas):
    dados = {"atualizado_em": datetime.now().isoformat(timespec="seconds"),
             "pasta": pasta, "pastas": [{"id": p["id"], "name": p["name"]} for p in pastas], "documentos": docs}
    salvar_json(ARQ_DOCS, dados)
    return dados


def carregar():
    return ler_json(ARQ_DOCS, {"atualizado_em": None, "pasta": None, "pastas": [], "documentos": []})


def baixar_pdf(chave, url, destino):
    """Salva o PDF (assinado) no caminho informado, sem sobrescrever arquivos."""
    if os.path.exists(destino):
        raise ErroAutentique("Já existe um arquivo com esse nome na pasta.")
    for com_chave in (False, True):
        req = urllib.request.Request(url)
        if com_chave:
            req.add_header("Authorization", f"Bearer {chave}")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                conteudo = r.read()
            if conteudo[:4] == b"%PDF":
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with open(destino, "wb") as f:
                    f.write(conteudo)
                return destino
        except urllib.error.HTTPError:
            continue
    raise ErroAutentique("Não foi possível baixar o PDF assinado deste documento.")
