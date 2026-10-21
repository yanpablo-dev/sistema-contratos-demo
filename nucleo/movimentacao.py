"""Move contratos para a pasta de encerrados (e de volta), com histórico e opção de desfazer.

O caminho original é preservado dentro da pasta de encerrados, por exemplo:
  Contratos de Prestaçäo de Serviços\\Modelos Antigos\\X.doc
  -> Contrato Encerrado\\Contratos de Prestaçäo de Serviços\\Modelos Antigos\\X.doc
"""
import os
import shutil
import uuid
from datetime import datetime

from .config import caminho_dados
from .util import ler_json, salvar_json

ARQ_HISTORICO = caminho_dados("movimentacoes.json")


class ErroMovimentacao(Exception):
    pass


def historico():
    return ler_json(ARQ_HISTORICO, [])


def _dentro(raiz, caminho):
    raiz = os.path.normcase(os.path.abspath(raiz))
    caminho = os.path.normcase(os.path.abspath(caminho))
    return os.path.commonpath([raiz, caminho]) == raiz and caminho != raiz


def _destino_livre(caminho):
    if not os.path.exists(caminho):
        return caminho
    base, ext = os.path.splitext(caminho)
    n = 2
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def _limpar_vazias(pasta, raiz):
    """Remove pastas que ficaram vazias, sem nunca apagar as pastas do primeiro nível."""
    raiz_n = os.path.normcase(os.path.abspath(raiz))
    atual = os.path.abspath(pasta)
    while True:
        rel = os.path.relpath(atual, raiz_n)
        if rel in (".", "") or "\\" not in rel and "/" not in rel:
            break
        try:
            if os.listdir(atual):
                break
            os.rmdir(atual)
        except OSError:
            break
        atual = os.path.dirname(atual)


def _mover(raiz, origem_rel, destino_rel):
    origem = os.path.join(raiz, origem_rel)
    destino = os.path.join(raiz, destino_rel)
    if not (_dentro(raiz, origem) and _dentro(raiz, destino)):
        raise ErroMovimentacao("Caminho fora da pasta de contratos.")
    if not os.path.isfile(origem):
        raise ErroMovimentacao("Arquivo não encontrado (pode ter sido movido ou renomeado).")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    destino = _destino_livre(destino)
    try:
        shutil.move(origem, destino)
    except PermissionError:
        raise ErroMovimentacao("Sem permissão ou arquivo aberto em outro programa (feche o Word e tente de novo).")
    _limpar_vazias(os.path.dirname(origem), raiz)
    return os.path.relpath(destino, raiz)


def executar(itens, cfg, usuario, acao):
    """itens: lista de dicts vindos da análise (rel, empresa, situacao, motivo)."""
    raiz = cfg["pasta_raiz"]
    enc = cfg["pasta_encerrados"]
    hist = historico()
    resultados = []
    for it in itens:
        rel = it["rel"]
        try:
            if acao == "ENCERRAR":
                if rel.lower().startswith(enc.lower() + "\\"):
                    raise ErroMovimentacao("O arquivo já está na pasta de encerrados.")
                destino_rel = os.path.join(enc, rel)
            elif acao == "RESTAURAR":
                if not rel.lower().startswith(enc.lower() + "\\"):
                    raise ErroMovimentacao("O arquivo não está na pasta de encerrados.")
                destino_rel = rel[len(enc) + 1:]
            else:
                raise ErroMovimentacao("Ação desconhecida.")
            final = _mover(raiz, rel, destino_rel)
            emp = it.get("empresa") or {}
            reg = {
                "id": uuid.uuid4().hex[:12],
                "data": datetime.now().isoformat(timespec="seconds"),
                "usuario": usuario, "acao": acao, "origem": rel, "destino": final,
                "empresa": emp.get("nome"), "empresa_num": emp.get("num"), "empresa_status": emp.get("status"),
                "situacao": it.get("situacao"), "motivo": it.get("motivo"), "desfeito": False,
            }
            hist.append(reg)
            resultados.append({"rel": rel, "ok": True, "destino": final})
        except (ErroMovimentacao, OSError) as e:
            resultados.append({"rel": rel, "ok": False, "erro": str(e)})
    salvar_json(ARQ_HISTORICO, hist)
    return resultados


def desfazer(ids, cfg, usuario):
    raiz = cfg["pasta_raiz"]
    hist = historico()
    resultados = []
    for reg in hist:
        if reg["id"] not in ids or reg.get("desfeito"):
            continue
        try:
            volta = _mover(raiz, reg["destino"], reg["origem"])
            reg["desfeito"] = True
            reg["desfeito_em"] = datetime.now().isoformat(timespec="seconds")
            reg["desfeito_por"] = usuario
            reg["desfeito_destino"] = volta
            resultados.append({"id": reg["id"], "ok": True})
        except (ErroMovimentacao, OSError) as e:
            resultados.append({"id": reg["id"], "ok": False, "erro": str(e)})
    salvar_json(ARQ_HISTORICO, hist)
    return resultados
