from django.templatetags.static import static
from django.test import SimpleTestCase
from django.urls import reverse


class PaginaInicialTests(SimpleTestCase):
    def test_pagina_inicial_renderiza_template_e_referencia_css(self):
        response = self.client.get(reverse('principal:inicio'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'principal/inicio.html')
        self.assertTemplateUsed(response, 'base.html')
        self.assertContains(response, 'Sistema de Pedidos Online')
        self.assertContains(response, 'Supermercado')
        self.assertContains(response, 'Projeto de estágio em desenvolvimento web')
        self.assertContains(response, static('css/estilos.css'))
