"""Planilha "Início dos contratos - empresas ativas".

A planilha conferida à mão (Inicio_Contratos_Empresas_Ativas.xlsx) é importada para
dados/inicio_contratos.json e serve de base. Na exportação, cada empresa ativa do Contask
recebe uma linha no mesmo modelo: o que foi conferido na planilha tem prioridade e o
restante é completado pela análise das pastas.
"""
import io
import os
from datetime import date, datetime

from .config import caminho_dados
from .util import ler_json, normalizar, salvar_json, so_digitos

ARQ = caminho_dados("inicio_contratos.json")
ABA_EMPRESAS = "Empresas ativas"
ABA_SEM_EMPRESA = "Contratos sem empresa ativa"
CAB_EMPRESAS = ["Número", "Razão social", "CNPJ/CPF", "Início do contrato (relatório)",
                "Início do contrato (encontrado no contrato)", "Fonte da data",
                "Como o contrato foi ligado à empresa", "Arquivo(s) do contrato", "Observação"]
LARG_EMPRESAS = [9, 45, 17, 16, 16, 30, 32, 60, 50]
CAB_SEM_EMPRESA = ["Cliente (nome do arquivo)", "Início da vigência", "CNPJ/CPF lido no contrato", "Observação", "Arquivo"]
LARG_SEM_EMPRESA = [40, 14, 34, 60, 60]
SITUACOES_SEM_EMPRESA = ("ENCERRADA", "NAO_CLIENTE")


class ErroPlanilha(Exception):
    pass


def carregar():
    return ler_json(ARQ, {"empresas": {}, "sem_empresa": []})


def _iso(v):
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _txt(v):
    return str(v).strip() if v not in (None, "") else ""


def _chave(num, cnpj, nome=""):
    d = so_digitos(cnpj)
    if d:
        return d
    return f"num:{_txt(num)}" if _txt(num) else f"nome:{normalizar(nome)}"


def importar(conteudo, nome_arquivo, usuario):
    """Lê a planilha no modelo (as duas abas) e guarda como base."""
    try:
        import openpyxl
    except ImportError:
        raise ErroPlanilha("O módulo openpyxl não está instalado (pip install openpyxl).")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(conteudo), data_only=True)
    except Exception:
        raise ErroPlanilha("Não foi possível abrir a planilha. Use um arquivo .xlsx.")
    if ABA_EMPRESAS not in wb.sheetnames:
        raise ErroPlanilha(f"A planilha precisa ter a aba “{ABA_EMPRESAS}”.")
    emps = {}
    for r in wb[ABA_EMPRESAS].iter_rows(min_row=2, values_only=True):
        r = list(r) + [None] * 9
        if not (r[1] or r[2]):
            continue
        emps[_chave(r[0], r[2], r[1])] = {
            "num": _txt(r[0]), "nome": _txt(r[1]), "cnpj": so_digitos(r[2]),
            "inicio_relatorio": _iso(r[3]), "inicio_contrato": _iso(r[4]), "fonte": _txt(r[5]),
            "ligacao": _txt(r[6]), "arquivos": _txt(r[7]), "obs": _txt(r[8]),
        }
    sem = []
    if ABA_SEM_EMPRESA in wb.sheetnames:
        for r in wb[ABA_SEM_EMPRESA].iter_rows(min_row=2, values_only=True):
            r = list(r) + [None] * 5
            if not (r[0] or r[4]):
                continue
            sem.append({"cliente": _txt(r[0]), "inicio": _iso(r[1]), "cnpj": _txt(r[2]),
                        "obs": _txt(r[3]), "arquivo": _txt(r[4])})
    dados = {"importado_em": datetime.now().isoformat(timespec="seconds"), "fonte": nome_arquivo,
             "por": usuario, "empresas": emps, "sem_empresa": sem}
    salvar_json(ARQ, dados)
    return {"empresas": len(emps), "sem_empresa": len(sem), "importado_em": dados["importado_em"]}


def resumo():
    d = carregar()
    return {"importado_em": d.get("importado_em"), "fonte": d.get("fonte"),
            "empresas": len(d.get("empresas") or {}), "sem_empresa": len(d.get("sem_empresa") or [])}


def _data_celula(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d") if iso else None
    except ValueError:
        return None


def _br(iso):
    d = _data_celula(iso)
    return d.strftime("%d/%m/%Y") if d else None


def _juntar(*obs):
    partes = []
    for o in obs:
        for p in (o or "").split(";"):
            p = p.strip()
            if p and p not in partes:
                partes.append(p)
    return "; ".join(partes) or None


def exportar(resultado, lista_empresas, cfg):
    """Gera o .xlsx no modelo da planilha, com a data da exportação."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    base = carregar()
    conferidas = base.get("empresas") or {}
    nossos = set(cfg.get("status_nossos") or [])
    arquivos = (resultado or {}).get("arquivos") or []

    # contratos na pasta ativa ligados a cada empresa
    por_emp = {}
    for a in arquivos:
        e = a.get("empresa")
        if e and not a.get("em_encerrados") and a.get("situacao") in ("ATIVA", "SUSPENSA", "MANTER"):
            por_emp.setdefault(e["id"], []).append(a)

    agora = datetime.now()
    wb = openpyxl.Workbook()

    def aba(ws, cab, larguras):
        ws.append(cab)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E78")
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for i, w in enumerate(larguras, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        ws.oddHeader.right.text = f"Exportado em {agora:%d/%m/%Y %H:%M}"
        ws.oddFooter.center.text = "Página &P de &N"

    def fechar(ws, colunas_data):
        for col in colunas_data:
            for (c,) in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                if isinstance(c.value, datetime):
                    c.number_format = "DD/MM/YYYY"
        ws.auto_filter.ref = ws.dimensions

    # ---------------------------------------------------------- aba 1: empresas ativas
    ws = wb.active
    ws.title = ABA_EMPRESAS
    aba(ws, CAB_EMPRESAS, LARG_EMPRESAS)
    ativas = [e for e in lista_empresas if e.get("status") in nossos and not e.get("arquivada")]

    def conferida(e):
        for k in (_chave(e.get("num"), e.get("cnpj"), e.get("nome")), f"num:{_txt(e.get('num'))}",
                  f"nome:{normalizar(e.get('nome'))}"):
            if k in conferidas:
                return conferidas[k]
        return {}

    # empresas da planilha que não estão (ou não estão mais) entre as ativas do Contask continuam na lista
    ids_vistos = {_chave(e.get("num"), e.get("cnpj"), e.get("nome")) for e in ativas}
    nomes_vistos = {normalizar(e.get("nome")) for e in ativas}
    nums_vistos = {_txt(e.get("num")) for e in ativas if _txt(e.get("num"))}
    extras = [{"id": None, "num": c["num"], "nome": c["nome"], "cnpj": c["cnpj"]} for k, c in conferidas.items()
              if k not in ids_vistos and normalizar(c["nome"]) not in nomes_vistos and c["num"] not in nums_vistos]
    for e in sorted(ativas + extras, key=lambda x: (x.get("nome") or "").upper()):
        conf = conferida(e)
        if not e.get("id"):
            conf = dict(conf, obs=_juntar(conf.get("obs"), "Não está entre as empresas ativas do Contask — conferir"))
        arqs = sorted(por_emp.get(e["id"], []), key=lambda a: a["nome"].lower())
        datas = sorted(a["data_texto"] for a in arqs if a.get("data_texto"))
        if conf.get("inicio_contrato"):
            inicio, fonte = conf["inicio_contrato"], conf.get("fonte")
        elif datas:
            inicio, fonte = datas[0], "Data lida pelo sistema — conferir"
        else:
            inicio, fonte = None, conf.get("fonte")
        nomes = " | ".join(a["nome"] for a in arqs) or conf.get("arquivos")
        ligacao = conf.get("ligacao") or (arqs[0].get("metodo") if arqs else None)
        obs = conf.get("obs")
        if not nomes:
            obs = _juntar(obs, "Nenhum contrato encontrado na pasta")
        elif not inicio:
            obs = _juntar(obs, "Data de início não encontrada — conferir")
        ws.append([_txt(e.get("num")) or None, e.get("nome"), e.get("cnpj"),
                   _br(e.get("inicio_contrato")) or _br(conf.get("inicio_relatorio")),
                   _data_celula(inicio), fonte or None, ligacao or None, nomes or None, obs])
    fechar(ws, [5])

    # ---------------------------------------------------------- aba 2: contratos sem empresa ativa
    ws2 = wb.create_sheet(ABA_SEM_EMPRESA)
    aba(ws2, CAB_SEM_EMPRESA, LARG_SEM_EMPRESA)
    vistos = set()
    linhas = []
    for s in base.get("sem_empresa") or []:
        vistos.add(s["arquivo"].lower())
        linhas.append([s["cliente"] or None, _data_celula(s.get("inicio")), s.get("cnpj") or None,
                       s.get("obs") or None, s["arquivo"] or None])
    for a in arquivos:
        if a.get("em_encerrados") or a.get("situacao") not in SITUACOES_SEM_EMPRESA or a["nome"].lower() in vistos:
            continue
        vistos.add(a["nome"].lower())
        obs = [a.get("situacao_rotulo")]
        if not a.get("data_texto"):
            obs.append("Data de início não encontrada — conferir")
        linhas.append([os.path.splitext(a["nome"])[0], _data_celula(a.get("data_texto")),
                       ", ".join(so_digitos(c) for c in a.get("cnpjs_cliente") or []) or None,
                       _juntar(*obs), a["nome"]])
    for lin in sorted(linhas, key=lambda l: (l[0] or "").upper()):
        ws2.append(lin)
    fechar(ws2, [2])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"Inicio_Contratos_Empresas_Ativas_{agora:%Y-%m-%d}.xlsx"
