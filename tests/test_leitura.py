"""Testes da leitura de contratos: CNPJs no texto, nomes de arquivo e endereço."""
import unittest

from nucleo import cnpj, extrator, identificador

CNPJ_ALFA = "11444777000161"  # CNPJ fictício do próprio escritório


class TestExtrator(unittest.TestCase):
    def test_separa_cnpj_do_cliente_e_do_escritorio(self):
        texto = "CONTRATANTE: PADARIA PAO DOURADO, CNPJ 11.222.333/0001-81. CONTRATADA: ALFA, CNPJ 11.444.777/0001-61"
        r = extrator.analisar_texto(texto, [CNPJ_ALFA])
        self.assertEqual(r["cnpjs_cliente"], ["11222333000181"])
        self.assertEqual(r["contratante"], "PADARIA PAO DOURADO")

    def test_ignora_cnpj_invalido(self):
        r = extrator.analisar_texto("CNPJ 10.100.100/0001-00", [CNPJ_ALFA])
        self.assertEqual(r["cnpjs_cliente"], [])


class TestIdentificador(unittest.TestCase):
    def test_tokens_ignoram_sufixos_e_acentos(self):
        self.assertEqual(identificador.tokens_empresa("Padaria Pão Dourado LTDA - ME"), ["PADARIA", "PAO", "DOURADO"])

    def test_tokens_do_arquivo_ignoram_tipo_de_documento(self):
        tokens = identificador.tokens_arquivo("PADARIA PAO DOURADO LTDA - Contrato de Prestação.docx")
        self.assertEqual(tokens, ["PADARIA", "PAO", "DOURADO"])


class TestEndereco(unittest.TestCase):
    def test_endereco_completo(self):
        self.assertEqual(
            cnpj.montar_endereco("Rua A", "10", "Sala 2", "Centro", "Brasília", "DF", "70000000"),
            "Rua A, nº 10, Sala 2, Centro, Brasília/DF, CEP 70.000-000",
        )

    def test_endereco_sem_numero(self):
        self.assertEqual(cnpj.montar_endereco("Rua A", "", "", "", "Brasília", "DF", ""), "Rua A, s/n, Brasília/DF")


if __name__ == "__main__":
    unittest.main()
