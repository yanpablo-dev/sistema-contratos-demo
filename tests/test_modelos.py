"""Testes do motor de modelos: valores por extenso, datas, preenchimento e geração do Word."""
import io
import unittest
import zipfile
from datetime import date

from nucleo import modelos


class TestValorExtenso(unittest.TestCase):
    def test_valores(self):
        casos = {
            0: "Zero reais",
            0.01: "Um centavo",
            1: "Um real",
            2.5: "Dois reais e cinquenta centavos",
            100: "Cem reais",
            1000: "Mil reais",
            1001: "Mil e um reais",
            6634.97: "Seis mil, seiscentos e trinta e quatro reais e noventa e sete centavos",
            1000000: "Um milhão de reais",
        }
        for valor, esperado in casos.items():
            with self.subTest(valor=valor):
                self.assertEqual(modelos.valor_extenso(valor), esperado)


class TestFormatacao(unittest.TestCase):
    def test_formatar_dinheiro(self):
        self.assertEqual(modelos.formatar_dinheiro(0), "0,00")
        self.assertEqual(modelos.formatar_dinheiro(6634.97), "6.634,97")
        self.assertEqual(modelos.formatar_dinheiro(1000000), "1.000.000,00")

    def test_data_extenso(self):
        self.assertEqual(modelos.data_extenso(date(2026, 11, 6)), "06 de novembro de 2026")
        self.assertEqual(modelos.data_extenso(date(2026, 1, 31)), "31 de janeiro de 2026")

    def test_preencher_texto(self):
        texto = modelos.preencher_texto("Contratante: {{NOME}}, CNPJ {{CNPJ}}", {"NOME": "Padaria Pão Dourado", "CNPJ": "10.100.100/0001-00"})
        self.assertEqual(texto, "Contratante: Padaria Pão Dourado, CNPJ 10.100.100/0001-00")


class TestModelos(unittest.TestCase):
    def test_lista_tem_os_modelos_principais(self):
        ids = {m.get("id") for m in modelos.listar()}
        for esperado in ("contabil", "aditivo", "distrato", "cobranca", "acordo", "prop_auditoria"):
            with self.subTest(modelo=esperado):
                self.assertIn(esperado, ids)

    def test_todo_modelo_tem_texto_e_campos(self):
        for resumo in modelos.listar():
            with self.subTest(modelo=resumo.get("id")):
                modelo = modelos.carregar(resumo["id"])
                self.assertTrue(modelo.get("texto"))
                self.assertIsInstance(modelo.get("campos"), list)

    def test_campos_obrigatorios_faltando(self):
        modelo = modelos.carregar("contabil")
        _, faltando = modelos.preparar_valores(modelo, {})
        self.assertIn("Razão social do cliente", faltando)


class TestGeracaoWord(unittest.TestCase):
    def setUp(self):
        self.modelo = modelos.carregar("contabil")
        self.vals, _ = modelos.preparar_valores(self.modelo, {
            "RAZAO_SOCIAL": "PADARIA PAO DOURADO LTDA",
            "CNPJ": "11222333000181",
            "VALOR": "1500",
        })

    def test_docx_e_um_word_valido(self):
        dados = modelos.gerar_docx(self.modelo, self.vals)
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            nomes = z.namelist()
            for parte in ("[Content_Types].xml", "word/document.xml", "word/styles.xml", "word/media/logo.jpg"):
                with self.subTest(parte=parte):
                    self.assertIn(parte, nomes)
            documento = z.read("word/document.xml").decode("utf-8")
        self.assertIn("PADARIA PAO DOURADO LTDA", documento)
        self.assertNotIn("{{RAZAO_SOCIAL}}", documento)

    def test_nome_do_arquivo(self):
        nome = modelos.nome_arquivo(self.modelo, self.vals)
        self.assertTrue(nome.startswith("PADARIA PAO DOURADO LTDA"))
        self.assertTrue(nome.endswith(".docx"))


if __name__ == "__main__":
    unittest.main()
