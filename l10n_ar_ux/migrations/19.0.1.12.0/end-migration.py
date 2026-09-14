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
    "sale_automatic_workflow",
    "sale_automatic_workflow_job",
    "sale_automatic_workflow_stock",
    "stock_voucher",
)

REMOVED_FIELDS = (
    "all_qty_delivered",
    "workflow_process_id",
)

REMOVED_MODELS = (
    "automatic.workflow.job",
    "sale.workflow.process",
)


def migrate(cr, version):
    """
    Script de fin de migracion (STEP 3.5 en loading.py).
    Se ejecuta despues de que todos los modulos del grafo hayan cargado, justo antes
    de la comprobacion de estados inconsistentes (linea 504 de loading.py).
    Garantiza que ningun modulo quede en estado 'to upgrade' o 'to install'
    y que ninguna vista huerfana de all_qty_delivered o workflow_process_id quede activa.
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

    # Limpieza final de vistas que pudieran referenciar all_qty_delivered o workflow_process_id
    pattern = r"\y(" + "|".join(REMOVED_FIELDS) + r")\y"
    cr.execute(
        """
        SELECT v.id
          FROM ir_ui_view v
          LEFT JOIN ir_model_data d
            ON d.model = 'ir.ui.view' AND d.res_id = v.id
         WHERE v.type != 'qweb'
           AND (
               v.arch_db::text ~ %s
            OR v.model IN %s
            OR d.module IN %s
           )
        """,
        (pattern, REMOVED_MODELS, MODULES_TO_UNINSTALL),
    )
    view_ids = [row[0] for row in cr.fetchall()]
    if view_ids:
        cr.execute(
            """
            WITH RECURSIVE arbol(id) AS (
                SELECT id FROM ir_ui_view WHERE id IN %s
                UNION
                SELECT h.id FROM ir_ui_view h JOIN arbol a ON h.inherit_id = a.id
            )
            SELECT id FROM arbol
            """,
            (tuple(view_ids),),
        )
        pendientes = {row[0] for row in cr.fetchall()}
        while pendientes:
            cr.execute(
                """
                DELETE FROM ir_ui_view
                 WHERE id IN %s
                   AND id NOT IN (SELECT inherit_id FROM ir_ui_view WHERE inherit_id IS NOT NULL)
             RETURNING id
                """,
                (tuple(pendientes),),
            )
            borradas = {row[0] for row in cr.fetchall()}
            if not borradas:
                break
            pendientes -= borradas

        cr.execute(
            """
            DELETE FROM ir_model_data
             WHERE model = 'ir.ui.view'
               AND res_id NOT IN (SELECT id FROM ir_ui_view)
            """
        )
        _logger.info("l10n_ar_ux end-migration: vistas huerfanas eliminadas")

    # Limpieza de ir_model_fields e ir_model
    cr.execute(
        """
        DELETE FROM ir_model_fields 
         WHERE model IN %s
            OR (model = 'sale.order' AND name IN ('all_qty_delivered', 'workflow_process_id'))
            OR (model = 'account.move' AND name IN ('workflow_process_id'))
            OR (model = 'stock.picking' AND name IN ('workflow_process_id'))
        """,
        (REMOVED_MODELS,),
    )
    cr.execute("DELETE FROM ir_model WHERE model IN %s", (REMOVED_MODELS,))
