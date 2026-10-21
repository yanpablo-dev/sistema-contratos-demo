"""Liga cada contrato a uma empresa da carteira.

Ordem de evidências (da mais forte para a mais fraca):
  1. CNPJ do CONTRATANTE encontrado dentro do documento (= CNPJ do cadastro)  -> 100
  2. Mesma raiz de CNPJ (matriz/filial)                                       -> 95
  3. Nome do CONTRATANTE escrito no documento x razão social / fantasia
  4. Nome do arquivo (sem as palavras "Contrato de Prestação de Serviços...")
  5. Nome da pasta, quando a pasta é de uma empresa (ex.: "Banco Alfa")

A comparação por nome usa pesos por raridade da palavra (IDF): palavras comuns como
COMERCIO ou SERVICOS contam pouco; palavras raras como FRANCAP contam muito.
"""
import math
from difflib import SequenceMatcher

from .util import formatar_cnpj, normalizar

SUFIXOS = {"LTDA", "ME", "EPP", "EIRELI", "SA", "S", "A", "CIA", "LIMITADA", "MEI", "SS", "SLU", "LTD", "SC",
           "DOMESTICA", "DOMESTICO"}
LIGACAO = {"DE", "DA", "DO", "DAS", "DOS", "E", "EM", "COM", "PARA", "X", "VS", "NA", "NO", "AO"}
GENERICAS_ARQUIVO = set("""
CONTRATO CONTRATOS CNTRATO ONTRATO CTT PRESTACAO PRESTACOES PREST PRESTACAO SERVICOS SERVICO
CONTABEIS CONTABIL PROFISSIONAIS TECNICOS ESPECIALIZADOS MODELO MODELOS NOVO NOVA ANTIGO ANTIGOS
ASSINADO ASSINADA VERSAO FINAL COPIA BACKUP SOCIAL LOCACAO COMPRA VENDA INSTRUMENTO PARTICULAR
COMODATO TERMO ADITIVO REAJUSTE BPO FINANCEIRO GESTAO EMPRESARIAL DIAGNOSTICO TRIBUTARIO
RETIFICACAO MALHA FISCAL ALFA DOC DOCX PDF MINUTA ATUAL ARRENDAMENTO MANDATO DIVERSOS
DOCUMENTACAO RECIBO ALUGUEL CARTA COMUNICADO ESTABELECIMENTO COMERCIAL AUDITORIA CONSULTORIA
APRENDIZAGEM EXPERIENCIA PRAZO DETERMINADO ESTATUTO ATA FUNDACAO CONVENCAO REGIMENTO INTERNO
ABERTURA CONSTITUICAO SOCIEDADE CESSAO PERMISSAO DEPARTAMENTO PESSOAL ELEICAO ADMINISTRADOR NAO
SOCIO POSSE EMPRESTIMO DINHEIRO MUTUO EDIFICIO SALA REPRESENTACAO MONITORAMENTO MANUTENCAO PROGRAMA
COMPUTADOR TRABALHO EMPREGADA DOMESTICA AUTONOMO MOTO BOY SCP FILIAL IMOVEL
""".split())
PASTAS_GENERICAS = {"MODELOS ANTIGOS", "NOVO MODELO", "MODELO 2021", "MODELO", "MODELOS", "CONTRATO ENCERRADO",
                    "CONTRATOS ENCERRADOS"}


def tokens_empresa(nome):
    return [t for t in normalizar(nome).split()
            if t not in SUFIXOS and t not in LIGACAO and not t.isdigit() and len(t) >= 2]


def tokens_arquivo(nome):
    out = []
    for t in normalizar(nome).split():
        if t in GENERICAS_ARQUIVO or t in SUFIXOS or t in LIGACAO:
            continue
        if t.isdigit() or len(t) < 2:
            continue
        out.append(t)
    return out


class Identificador:
    # soma mínima de pesos casados para a evidência por nome valer 100% (≈ uma palavra rara)
    FORCA_MINIMA = 5.5

    def __init__(self, empresas, cfg):
        self.cfg = cfg
        self.empresas = empresas
        self.por_id = {e["id"]: e for e in empresas}
        self.por_cnpj = {}
        self.por_raiz = {}
        for e in empresas:
            c = e.get("cnpj") or ""
            if len(c) == 14:
                self.por_cnpj.setdefault(c, []).append(e)
                self.por_raiz.setdefault(c[:8], []).append(e)
            elif len(c) == 11:
                self.por_cnpj.setdefault(c, []).append(e)

        # variantes de nome por empresa (razão social e fantasia)
        self.variantes = {}
        df = {}
        self.indice = {}
        for e in empresas:
            vs = []
            for nome in (e.get("nome"), e.get("fantasia")):
                tk = tokens_empresa(nome)
                if tk and tk not in vs:
                    vs.append(tk)
            self.variantes[e["id"]] = vs
            vistos = set(t for v in vs for t in v)
            for t in vistos:
                df[t] = df.get(t, 0) + 1
                self.indice.setdefault(t, set()).add(e["id"])
        n = max(len(empresas), 1)
        self.idf = {t: math.log((n + 1) / (q + 1)) + 1 for t, q in df.items()}
        self.idf_max = math.log(n + 1) + 1
        self.vocab = list(self.indice.keys())
        self._similares = {}

    # ------------------------------------------------------------------ util
    def _peso(self, t):
        return self.idf.get(t, self.idf_max)

    @staticmethod
    def _sim(a, b):
        if a == b:
            return 1.0
        if len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)):
            return 0.9
        if len(a) >= 5 and len(b) >= 5 and abs(len(a) - len(b)) <= 3:
            r = SequenceMatcher(None, a, b).ratio()
            if r >= 0.84:
                return r
        return 0.0

    def _tokens_parecidos(self, t):
        if t not in self._similares:
            self._similares[t] = [v for v in self.vocab if self._sim(t, v) > 0]
        return self._similares[t]

    def _candidatas(self, tokens):
        ids = set()
        for t in tokens:
            for v in self._tokens_parecidos(t):
                ids |= self.indice[v]
        juntos = "".join(tokens)
        if len(juntos) >= 6:  # "BARROSAUTOPECAS" x "BARROS AUTO PECAS"
            for eid, vs in self.variantes.items():
                if any(juntos in "".join(v) or ("".join(v) in juntos and len("".join(v)) >= 6) for v in vs):
                    ids.add(eid)
        return ids

    def _pontuar(self, cand, variante):
        peso_c = sum(self._peso(c) for c in cand)
        if not peso_c or not variante:
            return 0.0
        obtido = 0.0
        casados = set()
        for c in cand:
            melhor, melhor_k = 0.0, None
            for k in variante:
                s = self._sim(c, k)
                if s > melhor:
                    melhor, melhor_k = s, k
            obtido += self._peso(c) * melhor
            if melhor_k:
                casados.add(melhor_k)
        cob_c = obtido / peso_c
        peso_k = sum(self._peso(k) for k in variante)
        cob_k = sum(self._peso(k) for k in casados) / peso_k if peso_k else 0
        jc, jk = "".join(cand), "".join(variante)
        curto, longo = sorted((len(jc), len(jk)))
        colado = (len(jc) >= 6 and len(jk) >= 6 and (jk.startswith(jc) or jc.startswith(jk))
                  and jc not in variante and jk not in cand          # não é só uma palavra comum
                  and (curto / longo >= 0.5 or curto >= 10))
        if colado:
            cob_c = max(cob_c, 0.95)
            cob_k = max(cob_k, min(len(jc), len(jk)) / max(len(jc), len(jk)))
            obtido = max(obtido, self.FORCA_MINIMA)
        # uma única palavra comum ("COMERCIO", "IGREJA") não é evidência suficiente
        forca = min(1.0, obtido / self.FORCA_MINIMA) ** 0.7
        pts = 100.0 * (0.6 * cob_c + 0.4 * cob_k) * forca
        # nome do arquivo = começo da razão social ("INSTITUTO ASCENDE" -> "INSTITUTO ASCENDE DE POLITICAS...")
        def igual(c, k):
            return c == k or (len(c) >= 4 and len(k) >= 4 and (c.startswith(k) or k.startswith(c)))

        if (forca >= 1.0 and len(cand) <= len(variante) and (len(cand) > 1 or len(cand[0]) >= 5)
                and all(igual(c, k) for c, k in zip(cand, variante))):
            pts = max(pts, 86.0 + 4.0 * len(cand) / len(variante))
        # a 1ª palavra da razão social costuma ser a que distingue a empresa ("JK" AGENCIA DE VIAGENS);
        # se ela não aparece, a correspondência fica no máximo como "Revisar"
        if (not colado and not any(self._sim(c, variante[0]) >= 0.84 for c in cand)) or \
                (len(cand) == 1 and not igual(cand[0], variante[0])):
            pts = min(pts, self.cfg.get("limite_confianca", 80) - 1)
        return pts

    def por_nome(self, tokens, limite=3):
        """Devolve [(pontuacao, empresa)] ordenado, melhores primeiro."""
        if not tokens:
            return []
        res = []
        for eid in self._candidatas(tokens):
            pts = max((self._pontuar(tokens, v) for v in self.variantes.get(eid, [])), default=0)
            if pts > 0:
                res.append((round(pts, 1), self.por_id[eid]))
        res.sort(key=lambda x: (-x[0], self._ordem_status(x[1])))
        return res[:limite]

    def _ordem_status(self, e):
        return 0 if e.get("status") in self.cfg.get("status_nossos", []) else 1

    def _escolher(self, lista):
        """Entre empresas do mesmo CNPJ/raiz, prefere a ativa."""
        return sorted(lista, key=self._ordem_status)[0]

    # ------------------------------------------------------------- principal
    def identificar(self, nome_arquivo, nome_pasta, extr):
        """Retorna dict: empresa, confianca, metodo, evidencia, alternativas, cnpj_sem_cadastro."""
        r = {"empresa": None, "confianca": 0, "metodo": None, "evidencia": None,
             "alternativas": [], "cnpj_sem_cadastro": None}

        cnpjs = extr.get("cnpjs_cliente") or []
        do_contratante = bool(extr.get("cnpj_do_contratante"))
        for c in cnpjs:
            if c in self.por_cnpj:
                e = self._escolher(self.por_cnpj[c])
                if do_contratante:
                    r.update(empresa=e, confianca=100, metodo="CNPJ do contratante",
                             evidencia=f"CNPJ {formatar_cnpj(c)} na cláusula CONTRATANTE é o mesmo do cadastro")
                else:
                    r.update(empresa=e, confianca=90, metodo="CNPJ citado no documento",
                             evidencia=f"O CNPJ {formatar_cnpj(c)} desta empresa aparece no texto do documento")
                return r
        for c in cnpjs:
            if len(c) == 14 and c[:8] in self.por_raiz:
                e = self._escolher(self.por_raiz[c[:8]])
                r.update(empresa=e, confianca=95 if do_contratante else 85, metodo="CNPJ (mesma matriz/filial)",
                         evidencia=f"CNPJ {formatar_cnpj(c)} do documento tem a mesma raiz de {formatar_cnpj(e.get('cnpj'))}")
                return r

        fontes = []
        if extr.get("contratante"):
            fontes.append(("Nome do contratante no documento", tokens_empresa(extr["contratante"]), extr["contratante"]))
        tk_arq = tokens_arquivo(nome_arquivo.rsplit(".", 1)[0])
        if tk_arq:
            fontes.append(("Nome do arquivo", tk_arq, " ".join(tk_arq)))
        if nome_pasta and normalizar(nome_pasta) not in PASTAS_GENERICAS:
            tk_pasta = tokens_arquivo(nome_pasta)
            if tk_pasta:
                fontes.append(("Nome da pasta", tk_pasta, nome_pasta))

        melhor = None
        alternativas = {}
        for metodo, tokens, texto in fontes:
            for pts, e in self.por_nome(tokens):
                if metodo == "Nome da pasta":
                    pts = round(pts * 0.92, 1)
                atual = alternativas.get(e["id"])
                if not atual or pts > atual[0]:
                    alternativas[e["id"]] = (pts, e, metodo, texto)
                if not melhor or pts > melhor[0]:
                    melhor = (pts, e, metodo, texto)

        ordenadas = sorted(alternativas.values(), key=lambda x: -x[0])
        r["alternativas"] = [
            {"id": e["id"], "nome": e["nome"], "num": e.get("num"), "status": e.get("status"), "pontos": p}
            for p, e, _, _ in ordenadas[:4]
        ]
        if cnpjs:
            r["cnpj_sem_cadastro"] = cnpjs[0]
        if melhor and melhor[0] >= self.cfg.get("limite_revisao", 60):
            pts, e, metodo, texto = melhor
            # empate entre empresas diferentes (que não são do mesmo grupo de CNPJ) reduz a confiança
            if len(ordenadas) > 1:
                p2, e2 = ordenadas[1][0], ordenadas[1][1]
                mesma_raiz = (e.get("cnpj") or "")[:8] and (e.get("cnpj") or "")[:8] == (e2.get("cnpj") or "")[:8]
                if pts - p2 < 4 and not mesma_raiz and e2["id"] != e["id"]:
                    pts = min(pts, self.cfg.get("limite_confianca", 80) - 1)
            # CNPJ no documento diferente do cadastro: só aceita se o nome for muito parecido
            if cnpjs and pts < 92:
                pts = min(pts, self.cfg.get("limite_confianca", 80) - 1)
            r.update(empresa=e, confianca=round(pts), metodo=metodo,
                     evidencia=f'"{texto}" ≈ {e["nome"]}')
        return r
