import logging

_logger = logging.getLogger(__name__)

MODULES_TO_PRESERVE = (
    "account_hide_initial_balances",
    "approvals_purchase_no_merge",
    "sale_progress_certification",
)

MODULES_TO_UNINSTALL = (
    "account_paid_invoice_export",
    "account_tax_settlement",
    "l10n_ar_account_tax_settlement",
    "l10n_ar_stock_adhoc",
    "l10n_ar_tax_ratio",
    "sale_automatic_workflow_stock",
    "stock_voucher",
)


def migrate(cr, version):
    """
    Script de fin de migracion (STEP 3.5 en loading.py).
    Se ejecuta despues de que todos los modulos del grafo hayan cargado, justo antes
    de la comprobacion de estados inconsistentes (linea 504 de loading.py).
    Garantiza que ningun modulo quede en estado 'to upgrade' o 'to install'.
    """
    cr.execute(
        """
        UPDATE ir_module_module
           SET state = 'installed', latest_version = '19.0.1.0.0'
         WHERE name IN %s
           AND state IN ('to upgrade', 'to install')
        """,
        (MODULES_TO_PRESERVE,),
    )
    if cr.rowcount:
        _logger.info("l10n_ar_ux end-migration: %s modulos preservados asegurados como installed", cr.rowcount)

    cr.execute(
        """
        UPDATE ir_module_module
           SET state = 'uninstalled'
         WHERE name IN %s
           AND state IN ('installed', 'to upgrade', 'to install', 'to remove')
        """,
        (MODULES_TO_UNINSTALL,),
    )
    if cr.rowcount:
        _logger.info("l10n_ar_ux end-migration: %s modulos obsoletos asegurados como uninstalled", cr.rowcount)
