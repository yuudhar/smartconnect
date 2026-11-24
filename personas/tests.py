from django.core.management import call_command
from rest_framework.test import APITestCase

from .models import Persona

URL = "/api/personas/"


class PersonaCrudTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos", stdout=open("/dev/null", "w"))

    def test_listar(self):
        r = self.client.get(URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 8)

    def test_crear_formatea_rut(self):
        r = self.client.post(URL, {"rut": "18765432-7", "nombres": "Marta", "apellidos": "Lillo",
                                   "email": "MARTA@smartconnect.test"}, format="json")
        self.assertEqual(r.status_code, 201, r.json())
        self.assertEqual(r.json()["rut"], "18.765.432-7")
        self.assertEqual(r.json()["email"], "marta@smartconnect.test")
        self.assertTrue(r.json()["activo"])

    def test_rut_invalido_y_repetido(self):
        r = self.client.post(URL, {"rut": "18765432-1", "nombres": "X", "apellidos": "Y", "email": "x@y.cl"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("rut", r.json())
        existente = Persona.objects.first().rut
        r = self.client.post(URL, {"rut": existente, "nombres": "X", "apellidos": "Y", "email": "x@y.cl"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_detalle_muestra_vinculos(self):
        benja = Persona.objects.get(email="benja@smartconnect.test")
        r = self.client.get(f"{URL}{benja.pk}/")
        self.assertEqual(r.status_code, 200)
        roles = {v["rol"] for v in r.json()["vinculos"]}
        self.assertEqual(roles, {"arrendatario", "propietario_admin"})

    def test_put_patch_delete(self):
        r = self.client.post(URL, {"rut": "18765432-7", "nombres": "Marta", "apellidos": "Lillo",
                                   "email": "marta@smartconnect.test"}, format="json")
        url = f"{URL}{r.json()['id']}/"
        r = self.client.put(url, {"rut": "18765432-7", "nombres": "Marta Inés", "apellidos": "Lillo Rojas",
                                  "email": "marta@smartconnect.test", "telefono": "+56 9 8888 8888", "activo": True},
                            format="json")
        self.assertEqual(r.status_code, 200, r.json())
        r = self.client.patch(url, {"telefono": "+56 9 9999 9999"}, format="json")
        self.assertEqual(r.json()["telefono"], "+56 9 9999 9999")
        self.assertEqual(r.json()["nombres"], "Marta Inés")
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_borrar_persona_con_relaciones_da_409(self):
        carlos = Persona.objects.get(email="carlos@smartconnect.test")
        r = self.client.delete(f"{URL}{carlos.pk}/")
        self.assertEqual(r.status_code, 409)
        self.assertTrue(Persona.objects.filter(pk=carlos.pk).exists())

    def test_buscar(self):
        r = self.client.get(URL, {"buscar": "fuentes"})
        self.assertEqual(len(r.json()), 2)
