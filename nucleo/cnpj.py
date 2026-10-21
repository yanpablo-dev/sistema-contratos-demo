"""Consulta pública de CNPJ (Receita Federal) para preencher razão social completa, endereço e sócio-administrador.

Usa serviços públicos gratuitos, um depois do outro (se um falhar, tenta o próximo):
  BrasilAPI, CNPJ.ws, ReceitaWS e CNPJá. Apenas o número do CNPJ é enviado.
As respostas ficam em dados/cnpj_cache.json por 30 dias.
"""
import json
import re
import urllib.request
from datetime import datetime, timedelta

from .config import caminho_dados
from .util import formatar_cnpj, ler_json, salvar_json, so_digitos

ARQ_CACHE = caminho_dados("cnpj_cache.json")
VALIDADE = timedelta(days=30)


class ErroCnpj(Exception):
    pass


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ContratosDemo/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode("utf-8"))


def _limpo(v):
    v = re.sub(r"\s+", " ", str(v or "")).strip()
    return "" if v.upper() in ("", "SN", "S/N", "NONE", "NULL") else v


def _cep(v):
    d = so_digitos(v)
    return f"{d[:2]}.{d[2:5]}-{d[5:]}" if len(d) == 8 else _limpo(v)


def montar_endereco(logradouro, numero, complemento, bairro, cidade, uf, cep):
    partes = [_limpo(logradouro)]
    n = _limpo(numero)
    partes.append(f"nº {n}" if n else "s/n")
    for p in (complemento, bairro):
        if _limpo(p):
            partes.append(_limpo(p))
    cid = _limpo(cidade).title().replace(" De ", " de ").replace(" Do ", " do ").replace(" Da ", " da ")
    if cid or uf:
        partes.append(f"{cid}/{_limpo(uf).upper()}".strip("/"))
    if _limpo(cep):
        partes.append(f"CEP {_cep(cep)}")
    return ", ".join(p for p in partes if p)


def _admin(socios):
    """Nome do sócio-administrador, se houver exatamente um."""
    admins = [n for n, q in socios if re.search(r"administrador|presidente|titular|diretor", q or "", re.I)]
    return admins[0] if len(admins) == 1 else ""


def _brasilapi(c):
    d = _get(f"https://brasilapi.com.br/api/cnpj/v1/{c}")
    log = " ".join(filter(None, [_limpo(d.get("descricao_tipo_de_logradouro")), _limpo(d.get("logradouro"))]))
    return {"razao_social": d.get("razao_social"), "fantasia": d.get("nome_fantasia"),
            "endereco": montar_endereco(log, d.get("numero"), d.get("complemento"), d.get("bairro"),
                                        d.get("municipio"), d.get("uf"), d.get("cep")),
            "socio_administrador": _admin([(s.get("nome_socio"), s.get("qualificacao_socio")) for s in d.get("qsa") or []])}


def _cnpjws(c):
    d = _get(f"https://publica.cnpj.ws/cnpj/{c}")
    e = d.get("estabelecimento") or {}
    log = " ".join(filter(None, [_limpo(e.get("tipo_logradouro")), _limpo(e.get("logradouro"))]))
    return {"razao_social": d.get("razao_social"), "fantasia": e.get("nome_fantasia"),
            "endereco": montar_endereco(log, e.get("numero"), e.get("complemento"), e.get("bairro"),
                                        (e.get("cidade") or {}).get("nome"), (e.get("estado") or {}).get("sigla"), e.get("cep")),
            "socio_administrador": _admin([(s.get("nome"), (s.get("qualificacao_socio") or {}).get("descricao"))
                                           for s in d.get("socios") or []])}


def _receitaws(c):
    d = _get(f"https://www.receitaws.com.br/v1/cnpj/{c}")
    if d.get("status") == "ERROR":
        raise ErroCnpj(d.get("message") or "erro")
    return {"razao_social": d.get("nome"), "fantasia": d.get("fantasia"),
            "endereco": montar_endereco(d.get("logradouro"), d.get("numero"), d.get("complemento"), d.get("bairro"),
                                        d.get("municipio"), d.get("uf"), d.get("cep")),
            "socio_administrador": _admin([(s.get("nome"), s.get("qual")) for s in d.get("qsa") or []])}


def _cnpja(c):
    d = _get(f"https://open.cnpja.com/office/{c}")
    a = d.get("address") or {}
    return {"razao_social": (d.get("company") or {}).get("name"), "fantasia": d.get("alias"),
            "endereco": montar_endereco(a.get("street"), a.get("number"), a.get("details"), a.get("district"),
                                        a.get("city"), a.get("state"), a.get("zip")),
            "socio_administrador": _admin([((m.get("person") or {}).get("name"), (m.get("role") or {}).get("text"))
                                           for m in (d.get("company") or {}).get("members") or []])}


FONTES = [("BrasilAPI", _brasilapi), ("CNPJ.ws", _cnpjws), ("ReceitaWS", _receitaws), ("CNPJá", _cnpja)]


def consultar(cnpj, usar_cache=True):
    c = so_digitos(cnpj)
    if len(c) != 14:
        raise ErroCnpj("CNPJ inválido (precisa ter 14 números).")
    cache = ler_json(ARQ_CACHE, {})
    item = cache.get(c)
    if usar_cache and item:
        try:
            if datetime.now() - datetime.fromisoformat(item["consultado_em"]) < VALIDADE:
                return item
        except (KeyError, ValueError):
            pass
    erros = []
    for nome, fn in FONTES:
        try:
            r = fn(c)
            if not r.get("razao_social"):
                raise ErroCnpj("resposta sem razão social")
            r = {k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
            r.update(cnpj=formatar_cnpj(c), fonte=nome, consultado_em=datetime.now().isoformat(timespec="seconds"))
            cache[c] = r
            salvar_json(ARQ_CACHE, cache)
            return r
        except Exception as e:  # tenta a próxima fonte
            erros.append(f"{nome}: {str(e)[:80]}")
    raise ErroCnpj("Não foi possível consultar o CNPJ agora (" + "; ".join(erros) + ").")
