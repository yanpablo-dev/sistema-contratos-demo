"""Varre as pastas de contratos, lê datas, identifica a empresa e classifica cada arquivo."""
import os
import threading
import time
from datetime import datetime

from . import autentique as mod_autentique
from . import empresas as mod_empresas
from .config import PASTA_APP, caminho_dados
from .extrator import VERSAO_EXTRATOR, extrair
from .identificador import Identificador, tokens_arquivo
from .util import chave_arquivo, formatar_cnpj, ler_json, normalizar, salvar_json, ts_iso

ARQ_CACHE = caminho_dados("cache_textos.json")
ARQ_AJUSTES = caminho_dados("ajustes.json")
ARQ_ANALISE = caminho_dados("ultima_analise.json")

IGNORAR_NOMES = {"thumbs.db", "desktop.ini", ".ds_store"}

SITUACOES = {
    "ATIVA": ("Empresa nossa (ativa)", "MANTER"),
    "SUSPENSA": ("Empresa nossa (suspensa)", "MANTER"),
    "ENCERRADA": ("Empresa encerrada no Contask", "MOVER"),
    "NAO_CLIENTE": ("Não é empresa nossa", "MOVER"),
    "REVISAR": ("Identificação incerta", "REVISAR"),
    "SEM_IDENTIFICACAO": ("Sem empresa identificável", "REVISAR"),
    "MODELO": ("Modelo / documento padrão", "MANTER"),
    "MANTER": ("Mantido manualmente", "MANTER"),
    "RESTAURAR": ("Encerrado, mas empresa está ativa", "RESTAURAR"),
    "ARQUIVADO": ("Já está em Contrato Encerrado", "NENHUMA"),
}


class Estado:
    def __init__(self):
        self.trava = threading.RLock()
        self.rodando = False
        self.progresso = {"atual": 0, "total": 0, "mensagem": ""}
        self.erro = None
        self.resultado = ler_json(ARQ_ANALISE, None)


ESTADO = Estado()


def carregar_ajustes():
    return ler_json(ARQ_AJUSTES, {})


def salvar_ajuste(chave, dados, usuario):
    ajustes = carregar_ajustes()
    if dados is None:
        ajustes.pop(chave, None)
    else:
        dados = {k: v for k, v in dados.items() if v not in (None, "")}
        dados["por"] = usuario
        dados["em"] = datetime.now().isoformat(timespec="seconds")
        ajustes[chave] = dados
    salvar_json(ARQ_AJUSTES, ajustes)
    return ajustes


def _resumo_empresa(e):
    if not e:
        return None
    return {k: e.get(k) for k in ("id", "num", "nome", "fantasia", "cnpj", "status", "arquivada",
                                  "inicio_contrato", "data_status", "regime", "uf", "resp_contabil",
                                  "resp_fiscal", "resp_dp")} | {"cnpj_fmt": formatar_cnpj(e.get("cnpj"))}


def _ignorada(rel, ignoradas):
    rel_n = rel.replace("/", "\\").lower().strip("\\")
    for p in ignoradas:
        p = p.replace("/", "\\").lower().strip("\\")
        if p and (rel_n == p or rel_n.startswith(p + "\\")):
            return True
    return False


def varrer(cfg):
    """Lista pastas e arquivos com suas datas (sem ler conteúdo)."""
    raiz = cfg["pasta_raiz"]
    pasta_app = os.path.normcase(os.path.abspath(PASTA_APP))
    # a pasta de cobranças/notificações/acordos não tem contratos
    ignoradas = list(cfg.get("pastas_ignoradas") or []) + ["Cobranças e Acordos", "Propostas"]
    ext_ign = set(x.lower() for x in cfg.get("extensoes_ignoradas") or [])
    nome_enc = cfg["pasta_encerrados"].lower()
    pastas, arquivos = [], []
    for dirpath, dirnames, filenames in os.walk(raiz):
        rel_dir = os.path.relpath(dirpath, raiz)
        rel_dir = "" if rel_dir == "." else rel_dir
        dirnames[:] = sorted(
            d for d in dirnames
            if os.path.normcase(os.path.abspath(os.path.join(dirpath, d))) != pasta_app
            and not _ignorada(os.path.join(rel_dir, d), ignoradas)
            and not d.startswith(("$", "."))
        )
        em_enc = rel_dir.lower() == nome_enc or rel_dir.lower().startswith(nome_enc + "\\")
        try:
            st = os.stat(dirpath)
            pastas.append({"rel": rel_dir, "nome": os.path.basename(dirpath) if rel_dir else "(raiz)",
                           "nivel": 0 if not rel_dir else rel_dir.count("\\") + 1,
                           "criada": ts_iso(st.st_ctime), "modificada": ts_iso(st.st_mtime),
                           "em_encerrados": em_enc})
        except OSError:
            continue
        for f in sorted(filenames):
            baixo = f.lower()
            if baixo in IGNORAR_NOMES or f.startswith("~$") or os.path.splitext(baixo)[1] in ext_ign:
                continue
            caminho = os.path.join(dirpath, f)
            try:
                st = os.stat(caminho)
            except OSError:
                continue
            arquivos.append({
                "rel": os.path.join(rel_dir, f) if rel_dir else f,
                "nome": f, "pasta": rel_dir, "ext": os.path.splitext(baixo)[1],
                "tamanho": st.st_size, "criado": ts_iso(st.st_ctime), "modificado": ts_iso(st.st_mtime),
                "chave": chave_arquivo(f, st.st_size, st.st_mtime), "em_encerrados": em_enc,
            })
    return pastas, arquivos


def _classificar(a, extr, ident, cfg, ajuste):
    nossos = set(cfg.get("status_nossos") or [])
    lim = cfg.get("limite_confianca", 80)
    pasta_nome = os.path.basename(a["pasta"]) if a["pasta"] else ""
    r = ident.identificar(a["nome"], pasta_nome, extr)

    if ajuste and ajuste.get("empresa_id") and ajuste["empresa_id"] in ident.por_id:
        r.update(empresa=ident.por_id[ajuste["empresa_id"]], confianca=100, metodo="Vínculo manual",
                 evidencia=f"Vinculado manualmente por {ajuste.get('por', '?')} em {ajuste.get('em', '')[:10]}")

    e = r["empresa"]
    conf = r["confianca"]
    nome_n = normalizar(a["nome"])
    eh_modelo = ("MODELO" in nome_n.split() or extr.get("modelo_texto")) and conf < 95
    tem_info = bool(tokens_arquivo(a["nome"].rsplit(".", 1)[0]) or extr.get("contratante") or extr.get("cnpjs_cliente"))

    if e and conf >= lim:
        nossa = e.get("status") in nossos and not e.get("arquivada")
        if a["em_encerrados"]:
            sit = "RESTAURAR" if nossa else "ARQUIVADO"
        elif nossa:
            sit = "SUSPENSA" if e.get("status") == "SUSPENSA" else "ATIVA"
        else:
            sit = "ENCERRADA"
    elif a["em_encerrados"]:
        sit = "ARQUIVADO"
    elif eh_modelo:
        sit = "MODELO"
    elif e and conf >= cfg.get("limite_revisao", 60):
        sit = "REVISAR"
    elif tem_info:
        sit = "NAO_CLIENTE"
    else:
        sit = "SEM_IDENTIFICACAO"

    if ajuste and ajuste.get("situacao") and not a["em_encerrados"]:
        sit = ajuste["situacao"]

    # motivo detalhado
    if sit in ("ATIVA", "SUSPENSA"):
        motivo = f"{e['nome']} está {e.get('status')} no Contask. Identificado por: {r['metodo']}."
    elif sit == "ENCERRADA":
        quando = f" desde {e['data_status']}" if e.get("data_status") else ""
        motivo = f"{e['nome']} está {e.get('status')}{quando} no Contask. Identificado por: {r['metodo']}."
    elif sit == "NAO_CLIENTE":
        if r.get("cnpj_sem_cadastro"):
            motivo = f"O CNPJ do contratante ({formatar_cnpj(r['cnpj_sem_cadastro'])}) não existe na carteira do Contask."
        elif extr.get("contratante"):
            motivo = f'O contratante "{extr["contratante"]}" não corresponde a nenhuma empresa da carteira.'
        else:
            motivo = "Nenhuma empresa da carteira corresponde ao nome do arquivo."
    elif sit == "REVISAR":
        motivo = f"Possível correspondência com {e['nome']} ({conf} pts), mas não há certeza. Confira e vincule manualmente."
    elif sit == "SEM_IDENTIFICACAO":
        motivo = "O nome do arquivo e o conteúdo não indicam qual é a empresa (documento genérico)."
    elif sit == "MODELO":
        motivo = "Parece ser um modelo (nome contém 'modelo' ou o texto tem campos em branco)."
    elif sit == "MANTER":
        motivo = "Marcado manualmente para permanecer onde está."
    elif sit == "RESTAURAR":
        motivo = f"Está em '{cfg['pasta_encerrados']}', mas {e['nome']} está {e.get('status')} no Contask."
    else:
        motivo = "Contrato já arquivado na pasta de encerrados."
    if ajuste and ajuste.get("situacao") and not a["em_encerrados"]:
        motivo = (f"Marcado manualmente como “{SITUACOES[sit][0]}” por {ajuste.get('por', '?')} "
                  f"em {str(ajuste.get('em', ''))[:10]}.")
    if ajuste and ajuste.get("obs"):
        motivo += f" Obs.: {ajuste['obs']}"

    rotulo, acao = SITUACOES[sit]
    # quão forte é a prova de que "não é nossa": lida no documento ou só deduzida do nome do arquivo
    prova = "documento" if (extr.get("contratante") or extr.get("cnpjs_cliente")) else "nome"
    return {
        **a,
        "situacao": sit, "situacao_rotulo": rotulo, "acao": acao, "motivo": motivo, "prova": prova,
        "empresa": _resumo_empresa(e) if (e and conf >= cfg.get("limite_revisao", 60)) else None,
        "confianca": conf, "metodo": r["metodo"], "evidencia": r["evidencia"],
        "alternativas": r["alternativas"],
        "contratante": extr.get("contratante"), "trecho": extr.get("trecho"),
        "cnpjs_cliente": [formatar_cnpj(c) for c in extr.get("cnpjs_cliente") or []],
        "data_texto": extr.get("data_texto"), "tem_texto": extr.get("tem_texto"),
        "erro_leitura": extr.get("erro"), "ajuste": ajuste,
    }


def _estatistica_pastas(pastas, arquivos):
    idx = {p["rel"]: dict(p, arquivos_diretos=0, arquivos_total=0, tamanho=0, mais_antigo=None,
                          mais_recente=None, situacoes={}) for p in pastas}
    for a in arquivos:
        partes = a["pasta"].split("\\") if a["pasta"] else []
        cadeia = [""] + ["\\".join(partes[: i + 1]) for i in range(len(partes))]
        for j, rel in enumerate(cadeia):
            p = idx.get(rel)
            if not p:
                continue
            if j == len(cadeia) - 1:
                p["arquivos_diretos"] += 1
            p["arquivos_total"] += 1
            p["tamanho"] += a["tamanho"]
            m = a["modificado"] or ""
            if m and (not p["mais_antigo"] or m < p["mais_antigo"]):
                p["mais_antigo"] = m
            if m and (not p["mais_recente"] or m > p["mais_recente"]):
                p["mais_recente"] = m
            p["situacoes"][a["situacao"]] = p["situacoes"].get(a["situacao"], 0) + 1
    return sorted(idx.values(), key=lambda p: p["rel"].lower())


def _mesmo_nome(a, b):
    """Nome do documento no Autentique x nome do PDF: todas as palavras do menor estão no maior."""
    if not a or not b:
        return False
    menor, maior = (a, b) if len(a) <= len(b) else (b, a)
    if sum(len(t) for t in menor) < 5:
        return False
    return all(any(Identificador._sim(t, u) >= 0.84 for u in maior) for t in menor) and \
        Identificador._sim(menor[0], maior[0]) >= 0.84


def _cruzar_autentique(arquivos, ident, cfg):
    """Liga cada documento do Autentique à empresa da carteira e aos PDFs da pasta."""
    dados = mod_autentique.carregar()
    lim_rev = cfg.get("limite_revisao", 60)
    lim = cfg.get("limite_confianca", 80)
    tokens_locais = [(a, tokens_arquivo(a["nome"].rsplit(".", 1)[0])) for a in arquivos]
    saida = []
    for d in dados.get("documentos") or []:
        tk = tokens_arquivo(d["nome"].rsplit(".", 1)[0])
        melhor = ident.por_nome(tk, 1)
        pts, emp = (melhor[0][0], melhor[0][1]) if melhor else (0, None)
        if pts < lim_rev:
            emp = None
        locais = []
        for a, tka in tokens_locais:
            pelo_nome = _mesmo_nome(tk, tka)
            mesma_emp = emp and pts >= lim and a["empresa"] and a["empresa"]["id"] == emp["id"]
            if pelo_nome or mesma_emp:
                locais.append({"rel": a["rel"], "em_encerrados": a["em_encerrados"], "pelo_nome": pelo_nome,
                               "empresa": a["empresa"]})
                a.setdefault("_aut_nome", []).append(d["id"])
        locais.sort(key=lambda l: (not l["pelo_nome"], l["em_encerrados"]))
        # sem empresa pelo nome do documento: usa a empresa do PDF correspondente na pasta
        if (not emp or pts < lim) and locais and locais[0]["pelo_nome"] and locais[0]["empresa"]:
            emp, pts = ident.por_id.get(locais[0]["empresa"]["id"], emp), max(pts, lim)
        na_pasta_ativa = any(l["pelo_nome"] and not l["em_encerrados"] for l in locais)
        ativa_contask = bool(emp and pts >= lim and emp.get("status") in (cfg.get("status_nossos") or [])
                             and not emp.get("arquivada"))
        saida.append({**d, "empresa": _resumo_empresa(emp), "confianca": round(pts),
                      "nossa": ativa_contask or na_pasta_ativa, "na_pasta_ativa": na_pasta_ativa,
                      "ativa_contask": ativa_contask,
                      "arquivos_locais": [{k: l[k] for k in ("rel", "em_encerrados", "pelo_nome")} for l in locais[:10]]})
    if cfg.get("autentique_somente_nossas", True):
        saida = [d for d in saida if d["nossa"]]
    return saida


def executar(cfg):
    """Roda a análise completa (chamado numa thread)."""
    est = ESTADO
    inicio = time.time()
    try:
        dados_emp = mod_empresas.carregar()
        lista_emp = dados_emp.get("empresas") or []
        ident = Identificador(lista_emp, cfg)

        est.progresso = {"atual": 0, "total": 0, "mensagem": "Lendo pastas e datas..."}
        pastas, arquivos = varrer(cfg)

        proprios = sorted(set(cfg.get("cnpjs_proprios") or []))
        cache = ler_json(ARQ_CACHE, {})
        if cache.get("versao") != VERSAO_EXTRATOR or cache.get("cnpjs_proprios") != proprios:
            cache = {"versao": VERSAO_EXTRATOR, "cnpjs_proprios": proprios, "itens": {}}
        itens = cache["itens"]
        ajustes = carregar_ajustes()

        resultado_arqs = []
        total = len(arquivos)
        novos = 0
        for i, a in enumerate(arquivos, 1):
            est.progresso = {"atual": i, "total": total, "mensagem": f"Analisando {a['nome']}"}
            extr = itens.get(a["chave"])
            if extr is None:
                extr = extrair(os.path.join(cfg["pasta_raiz"], a["rel"]), a["ext"], proprios)
                itens[a["chave"]] = extr
                novos += 1
                if novos % 40 == 0:
                    salvar_json(ARQ_CACHE, cache)
            resultado_arqs.append(_classificar(a, extr, ident, cfg, ajustes.get(a["chave"])))
        # remove do cache arquivos que não existem mais
        vivos = {a["chave"] for a in arquivos}
        cache["itens"] = {k: v for k, v in itens.items() if k in vivos}
        salvar_json(ARQ_CACHE, cache)

        est.progresso = {"atual": total, "total": total, "mensagem": "Montando resumo..."}
        pastas_est = _estatistica_pastas(pastas, resultado_arqs)

        # contratos por empresa
        por_emp = {}
        for a in resultado_arqs:
            if a["empresa"] and a["situacao"] not in ("REVISAR",):
                d = por_emp.setdefault(a["empresa"]["id"], {"qtd": 0, "ativos": 0, "encerrados": 0, "ultimo": None})
                d["qtd"] += 1
                if a["em_encerrados"]:
                    d["encerrados"] += 1
                else:
                    d["ativos"] += 1
                if a["modificado"] and (not d["ultimo"] or a["modificado"] > d["ultimo"]):
                    d["ultimo"] = a["modificado"]

        docs_aut = _cruzar_autentique(resultado_arqs, ident, cfg)
        aut_por_emp = {}
        for d in docs_aut:
            if d["empresa"] and d["confianca"] >= cfg.get("limite_confianca", 80):
                aut_por_emp.setdefault(d["empresa"]["id"], []).append(
                    {"id": d["id"], "nome": d["nome"], "status": d["status"], "assinado_em": d["assinado_em"],
                     "criado_em": d["criado_em"]})
        por_id_aut = {d["id"]: d for d in docs_aut}
        for a in resultado_arqs:
            lista = list(aut_por_emp.get(a["empresa"]["id"], [])) if a["empresa"] else []
            for did in a.pop("_aut_nome", []):  # mesmo nome do documento no Autentique
                d = por_id_aut.get(did)
                if d and all(x["id"] != did for x in lista):
                    lista.append({"id": d["id"], "nome": d["nome"], "status": d["status"],
                                  "assinado_em": d["assinado_em"], "criado_em": d["criado_em"]})
            a["autentique"] = lista
            if lista and a["situacao"] == "NAO_CLIENTE":
                a["situacao"] = "REVISAR"
                a["situacao_rotulo"], a["acao"] = SITUACOES["REVISAR"]
                a["motivo"] = ("A empresa não está na carteira do Contask, mas este contrato está no Autentique "
                               f"({lista[0]['nome']}). Confirme se ela é nossa antes de mover.")
        for eid, lst in aut_por_emp.items():
            por_emp.setdefault(eid, {"qtd": 0, "ativos": 0, "encerrados": 0, "ultimo": None})["autentique"] = len(lst)

        pastas_est = _estatistica_pastas(pastas, resultado_arqs)  # recalcula após o cruzamento
        contagem = {}
        for a in resultado_arqs:
            contagem[a["situacao"]] = contagem.get(a["situacao"], 0) + 1
        nossos = set(cfg.get("status_nossos") or [])
        ativas = [e for e in lista_emp if e.get("status") in nossos and not e.get("arquivada")]
        sem_contrato = [e["id"] for e in ativas if not por_emp.get(e["id"], {}).get("ativos")]
        encerradas_com_contrato = [e["id"] for e in lista_emp
                                   if e["id"] in por_emp and por_emp[e["id"]]["ativos"]
                                   and (e.get("status") not in nossos or e.get("arquivada"))]

        res = {
            "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "duracao_s": round(time.time() - inicio, 1),
            "pasta_raiz": cfg["pasta_raiz"],
            "pasta_encerrados": cfg["pasta_encerrados"],
            "empresas_atualizadas_em": dados_emp.get("atualizado_em"),
            "empresas_fonte": dados_emp.get("fonte"),
            "arquivos": resultado_arqs,
            "pastas": pastas_est,
            "contratos_por_empresa": por_emp,
            "autentique": docs_aut,
            "resumo": {
                "total_arquivos": len(resultado_arqs),
                "total_pastas": len(pastas_est),
                "por_situacao": contagem,
                "a_mover": sum(1 for a in resultado_arqs if a["acao"] == "MOVER"),
                "a_restaurar": sum(1 for a in resultado_arqs if a["acao"] == "RESTAURAR"),
                "a_revisar": sum(1 for a in resultado_arqs if a["acao"] == "REVISAR"),
                "empresas_total": len(lista_emp),
                "empresas_ativas": len(ativas),
                "ativas_sem_contrato": sem_contrato,
                "encerradas_com_contrato": encerradas_com_contrato,
                "lidos_agora": novos,
            },
        }
        salvar_json(ARQ_ANALISE, res)
        with est.trava:
            est.resultado = res
            est.erro = None
    except Exception as ex:  # mostra o erro na tela em vez de travar
        import traceback
        traceback.print_exc()
        est.erro = f"{type(ex).__name__}: {ex}"
    finally:
        est.rodando = False


def iniciar(cfg):
    with ESTADO.trava:
        if ESTADO.rodando:
            return False
        ESTADO.rodando = True
        ESTADO.erro = None
    threading.Thread(target=executar, args=(cfg,), daemon=True).start()
    return True
