import io
from django.core.management import call_command
from rest_framework.test import APITestCase

from .models import Edificio, Terreno, Vivienda

URL = "/api/viviendas/"


class ViviendaCrudTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos", stdout=io.StringIO())
        cls.robles = Terreno.objects.get(codigo="TR-ROBLES")
        cls.bosque = Terreno.objects.get(codigo="TR-BOSQUE")
        cls.torre_a = Edificio.objects.get(nombre="Torre A")

    def test_listar_y_filtrar(self):
        self.assertEqual(len(self.client.get(URL).json()), 5)
        self.assertEqual(len(self.client.get(URL, {"tipo": "casa"}).json()), 2)
        self.assertEqual(len(self.client.get(URL, {"terreno": self.robles.pk}).json()), 3)

    def test_crear_depto_y_casa(self):
        r = self.client.post(URL, {"codigo": "lr-a-103", "tipo": "departamento", "numero": "103",
                                   "terreno": self.robles.pk, "edificio": self.torre_a.pk}, format="json")
        self.assertEqual(r.status_code, 201, r.json())
        self.assertEqual(r.json()["codigo"], "LR-A-103")
        self.assertEqual(r.json()["edificio_nombre"], "Torre A")
        r = self.client.post(URL, {"codigo": "EB-C-09", "tipo": "casa", "numero": "9", "terreno": self.bosque.pk},
                             format="json")
        self.assertEqual(r.status_code, 201, r.json())
        self.assertIsNone(r.json()["edificio"])

    def test_reglas_casa_depto_y_terreno(self):
        casa_con_edificio = {"codigo": "X1", "tipo": "casa", "numero": "1", "terreno": self.robles.pk,
                             "edificio": self.torre_a.pk}
        depto_sin_edificio = {"codigo": "X2", "tipo": "departamento", "numero": "1", "terreno": self.robles.pk}
        edificio_de_otro_terreno = {"codigo": "X3", "tipo": "departamento", "numero": "1",
                                    "terreno": self.bosque.pk, "edificio": self.torre_a.pk}
        for datos in (casa_con_edificio, depto_sin_edificio, edificio_de_otro_terreno):
            r = self.client.post(URL, datos, format="json")
            self.assertEqual(r.status_code, 400, datos)
            self.assertIn("edificio", r.json())

    def test_detalle_muestra_personas(self):
        casa7 = Vivienda.objects.get(codigo="EB-C-07")
        r = self.client.get(f"{URL}{casa7.pk}/")
        roles = sorted(p["rol"] for p in r.json()["personas"])
        self.assertEqual(roles, ["propietario_admin", "residente"])

    def test_put_patch_delete(self):
        r = self.client.post(URL, {"codigo": "LR-A-103", "tipo": "departamento", "numero": "103",
                                   "terreno": self.robles.pk, "edificio": self.torre_a.pk}, format="json")
        url = f"{URL}{r.json()['id']}/"
        r = self.client.put(url, {"codigo": "LR-A-104", "tipo": "departamento", "numero": "104",
                                  "terreno": self.robles.pk, "edificio": self.torre_a.pk, "activa": True}, format="json")
        self.assertEqual(r.status_code, 200, r.json())
        r = self.client.patch(url, {"activa": False}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["activa"])
        self.assertEqual(r.json()["numero"], "104")
        r = self.client.patch(url, {"tipo": "casa"}, format="json")  # sigue teniendo edificio
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_borrar_vivienda_con_personas_da_409(self):
        a101 = Vivienda.objects.get(codigo="LR-A-101")
        self.assertEqual(self.client.delete(f"{URL}{a101.pk}/").status_code, 409)
