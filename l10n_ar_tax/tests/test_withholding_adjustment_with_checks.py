"""Regresión: el ajuste de retenciones se saltea cuando el pago tiene cheques.

Bug reportado: al confirmar un pago de proveedor con cheques propios + retenciones,
Odoo cortaba con "El asiento no está balanceado".

Root cause: ``_prepare_move_lines_per_type`` decidía saltear el ajuste de retenciones
preguntando si el *pago* tenía cheques (``l10n_latam_new_check_ids``), asumiendo que
``l10n_latam_check_ux`` ya había hecho la cuenta. Pero check_ux se guarda con otra señal:
``liquidity_lines[0]["l10n_latam_check_ids"]``, o sea si ya hay UNA línea de liquidez por
cheque. Ese split lo arma ``l10n_latam_check._prepare_move_liquidity_lines``, que llega por
el PR odoo#248741 (abierto). En imágenes que no lo traen las dos señales divergen: check_ux
se sale temprano y nadie aplica el ajuste.

Consecuencia: la liquidez queda en ``amount`` -que en AR ya viene neto de retenciones- en
vez del valor real de los cheques, y la contrapartida en ``amount`` en vez de
``payment_total``. El asiento del pago cierra igual, porque ambas quedan subvaluadas por el
mismo importe, así que el error no salta ahí: revienta después, cuando
``_l10n_latam_check_split_move()`` crea un segundo asiento repartiendo los cheques por su
importe real contra esa liquidez subvaluada.

Los asserts son a propósito sobre los *totales* y no sobre la cantidad de líneas de
liquidez: con el PR hay una línea por cheque y sin él una sola, pero el invariante que
importa -y que el bug rompía- vale en los dos casos.
"""

from odoo.tests import tagged

from .test_payment_withholding_checks_multimoneda import TestPaymentChecksWithholding


@tagged("post_install", "-at_install")
class TestWithholdingAdjustmentWithChecks(TestPaymentChecksWithholding):
    def test_liquidez_es_el_valor_real_de_los_cheques(self):
        """Factura 12.100 ARS (10.000 neto). 2 cheques propios (6.000 + 5.800 = 11.800)
        + retención IIBB 3% = 300.

        Invariantes del asiento, valgan una o N líneas de liquidez:
        - liquidez total = -amount = -11.800 (el valor real de los cheques)
        - contrapartida  = +payment_total = +12.100 (la deuda bruta)
        - el asiento cierra

        Antes del fix la liquidez salía -11.500 (= amount - retenciones, restadas dos veces)
        y la contrapartida +11.800, ambas subvaluadas en los 300 de la retención.
        """
        invoice = self._create_invoice(10_000, self.ars)
        self.assertAlmostEqual(invoice.amount_total, 12_100, places=2)

        payment = self._create_check_payment_with_wth(
            self.bank_ars,
            invoice,
            [
                {"name": "00000001", "amount": 6_000},
                {"name": "00000002", "amount": 5_800},
            ],
        )

        self.assertAlmostEqual(payment.amount, 11_800, places=2, msg="amount = suma de los cheques")
        self.assertAlmostEqual(payment.withholdings_amount, 300, places=2, msg="IIBB 3% sobre 10.000")
        self.assertAlmostEqual(payment.payment_total, 12_100, places=2, msg="deuda bruta = neto + retenciones")

        res = payment._prepare_move_lines_per_type()

        liquidity_total = sum(line["balance"] for line in res.get("liquidity_lines", []))
        self.assertAlmostEqual(
            liquidity_total,
            -11_800,
            places=2,
            msg="La liquidez debe valer los cheques (11.800), no amount - retenciones (11.500).",
        )

        counterpart_lines = res.get("counterpart_lines", [])
        self.assertTrue(counterpart_lines, "Debe haber línea de contrapartida")
        self.assertAlmostEqual(
            counterpart_lines[0]["balance"],
            12_100,
            places=2,
            msg="La contrapartida debe cancelar la deuda bruta (payment_total), no solo el neto.",
        )

        total = sum(
            line["balance"]
            for key in ("liquidity_lines", "counterpart_lines", "withholding_lines", "write_off_lines")
            for line in res.get(key, [])
        )
        self.assertAlmostEqual(total, 0, places=2, msg="El asiento preparado debe cerrar")

    def test_post_con_cheques_y_retenciones_cancela_la_deuda_completa(self):
        """Mismo escenario, end to end: es el sintoma que reportaba el usuario.

        Verifica que postea sin UserError ("El asiento no está balanceado"), que el asiento
        cierra, y que la factura queda totalmente cancelada. Antes del fix el pago cancelaba
        de menos exactamente el total de retenciones, dejando residuo contra la factura.
        """
        invoice = self._create_invoice(10_000, self.ars)
        payment = self._create_check_payment_with_wth(
            self.bank_ars,
            invoice,
            [
                {"name": "00000003", "amount": 6_000},
                {"name": "00000004", "amount": 5_800},
            ],
        )

        # Si el fix no está, acá salta UserError desde _l10n_latam_check_split_move().
        payment.action_post()
        self.env.flush_all()

        self.assertAlmostEqual(
            sum(payment.move_id.line_ids.mapped("balance")),
            0,
            places=2,
            msg="Partida doble en el asiento del pago",
        )
        self.assertAlmostEqual(
            invoice.amount_residual,
            0,
            places=2,
            msg="La factura debe quedar cancelada por completo (cheques 11.800 + retenciones 300).",
        )
