import logging

_logger = logging.getLogger(__name__)

# Campos que los modulos custom eliminaron al pasar de 18.0 a 19.0. Sus vistas,
# acciones y filtros siguen vivos en la base despues del upgrade. Los modulos que
# desaparecieron del codigo (account_tax_settlement, l10n_ar_account_tax_settlement,
# sale_automatic_workflow, sale_automatic_workflow_stock) nunca cargan o se desinstalaron,
# asi que Odoo no limpia sus vistas obsoletas solo.
REMOVED_FIELDS = (
    "all_qty_delivered",
    "allow_move_with_valuation_cancelation",
    "arba_code",
    "arba_cot",
    "arba_warning_html",
    "autofilled_check_number",
    "autoprinted",
    "book_id",
    "book_required",
    "bundle_counterpart_currency_amount",
    "check_note_already_in_use",
    "check_sequence_next_number",
    "client_order_ref_in_invoice_line_desc",
    "counterpart_exchange_rate",
    "create_invoice_filter_domain",
    "create_invoice_filter_id",
    "default_sn_package_column_index",
    "default_sn_product_column_index",
    "default_sn_search_product_by_field",
    "default_sn_serial_column_index",
    "display_discount_with_tax",
    "exchange_rate",
    "group_arba_cot_enabled",
    "group_enable_eval_on_wa",
    "group_enable_fines_on_wa",
    "group_enable_wa_on_in",
    "group_enable_wa_on_invoice",
    "group_enable_wa_on_po",
    "group_enforce_wa_on_in",
    "group_enforce_wa_on_invoice",
    "group_stock_accounting_automatic",
    "hide_expected_arrival_when_eta",
    "incl_in_payment",
    "incl_paid",
    "incl_partial",
    "interest_ids",
    "invoice_date_is_order_date",
    "invoice_service_delivery",
    "l10n_ar_afip_activity_id",
    "lines_per_voucher",
    "lock_posted_moves",
    "manual_currency_po_inv",
    "next_number",
    "next_voucher_number",
    "on_sale_line_cancel_decrease_line_qty",
    "order_filter_domain",
    "order_filter_id",
    "payment_filter_domain",
    "payment_filter_id",
    "picking_filter_domain",
    "picking_filter_id",
    "pricelist_cache_auhorize_apikey_ids",
    "purchase_auto_cancel",
    "purchase_pricelist_disable_autocreate",
    "qty_multiple_over_max",
    "report_total_without_discount",
    "restocking_fee_product_id",
    "restrict_sale_order_line_remove",
    "sale_cancel_confirm",
    "sale_commitment_date_in_header",
    "sale_default_invoice_policy",
    "sale_done_filter_domain",
    "sale_done_filter_id",
    "sale_line_block_allowed_groups",
    "sale_line_field_block",
    "sale_order_currency_report_id",
    "sale_order_lot_selection_exclude_pending_orders",
    "sale_planner_calendar_max_duration",
    "sale_planner_done_on_sale_confirm",
    "sale_planner_forward_months",
    "sale_planner_mail_to_attendees",
    "sale_planner_order_cut_hour",
    "sale_report_print_block",
    "sale_require_commitment_date",
    "sale_workflow_copy_mode",
    "send_order_confirmation_mail",
    "sequence_to",
    "set_sales_team_from_products",
    "settled_line_ids",
    "settlement_account_id",
    "settlement_account_tag_ids",
    "settlement_partner_id",
    "show_client_order_ref_invoice",
    "show_client_order_ref_sale",
    "skip_sales_team_if_set",
    "so_line_client_ref_policy",
    "stock_orderpoint_allow_multiple_over_max",
    "susbscriptions_backward_days",
    "tax_settlement",
    "tax_settlement_move_id",
    "tax_state",
    "txt_binary",
    "update_constancia",
    "use_invoice_commercial_partner_filter",
    "use_oca_batch_validation",
    "use_search_filter_amount",
    "use_shipping_commercial_partner_filter",
    "validate_picking",
    "voucher_ids",
    "voucher_number",
    "voucher_number_unique",
    "voucher_required",
    "vouchers",
    "wa_fines_late_account_id",
    "wa_fines_rate",
    "with_vouchers",
    "workflow_process_id",
    "x_studio_first_op_payment_type",
)

# Modelos eliminados en 19.0: sus vistas quedan huerfanas.
REMOVED_MODELS = (
    "afip.activity",
    "automatic.workflow.job",
    "sale.workflow.process",
    "stock.book",
    "stock.picking.voucher",
    "stock.valuation.layer.recompute",
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

MODULES_TO_PRESERVE = (
    "account_hide_initial_balances",
    "approvals_purchase_no_merge",
    "sale_progress_certification",
)


def _migrar_remitos_stock_voucher(cr):
    """
    Migra los remitos historicos de stock_voucher hacia stock_picking.l10n_ar_delivery_guide_number
    y hace un backup permanente de la tabla stock_picking_voucher antes de cualquier limpieza.
    """
    cr.execute("ALTER TABLE stock_picking ADD COLUMN IF NOT EXISTS l10n_ar_delivery_guide_number VARCHAR")

    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
             WHERE table_schema = 'public' 
               AND table_name = 'stock_picking_voucher'
        )
    """)
    if cr.fetchone()[0]:
        cr.execute("""
            CREATE TABLE IF NOT EXISTS stock_picking_voucher_backup AS 
            SELECT * FROM stock_picking_voucher
        """)
        _logger.info("l10n_ar_ux pre-migration: tabla stock_picking_voucher_backup asegurada")

        cr.execute("""
            UPDATE stock_picking p
               SET l10n_ar_delivery_guide_number = sub.remitos
              FROM (
                  SELECT picking_id, string_agg(name, ', ' ORDER BY id) AS remitos
                    FROM stock_picking_voucher
                   WHERE name IS NOT NULL AND trim(name) != ''
                   GROUP BY picking_id
              ) sub
             WHERE p.id = sub.picking_id
               AND (p.l10n_ar_delivery_guide_number IS NULL OR trim(p.l10n_ar_delivery_guide_number) = '')
        """)
        _logger.info("l10n_ar_ux pre-migration: %s remitos migrados desde stock_picking_voucher a l10n_ar_delivery_guide_number", cr.rowcount)

    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
             WHERE table_name = 'stock_picking' 
               AND column_name = 'vouchers'
        )
    """)
    if cr.fetchone()[0]:
        cr.execute("""
            UPDATE stock_picking
               SET l10n_ar_delivery_guide_number = vouchers
             WHERE (l10n_ar_delivery_guide_number IS NULL OR trim(l10n_ar_delivery_guide_number) = '')
               AND vouchers IS NOT NULL AND trim(vouchers) != ''
        """)
        _logger.info("l10n_ar_ux pre-migration: %s remitos migrados desde stock_picking.vouchers a l10n_ar_delivery_guide_number", cr.rowcount)


def migrate(cr, version):
    """Limpia vistas, acciones, menus y filtros que apuntan a campos removidos en v19.

    Idempotente. Todo lo borrado que siga existiendo en el codigo se recrea cuando
    carga su modulo; revisar el log por si aparece algo de studio_customization,
    que vive solo en la base y no se regenera.
    """
    _migrar_remitos_stock_voucher(cr)
    _desinstalar_modulos_obsoletos(cr)
    _desactivar_crons_obsoletos(cr)

    pattern = r"\y(" + "|".join(REMOVED_FIELDS) + r")\y"

    _limpiar_vistas(cr, pattern)
    _limpiar_acciones(cr, pattern)


def _desinstalar_modulos_obsoletos(cr):
    cr.execute(
        """
        UPDATE ir_module_module
           SET state = 'installed', latest_version = '19.0.1.0.0'
         WHERE name IN %s
           AND state IN ('installed', 'to upgrade', 'to install')
        """,
        (MODULES_TO_PRESERVE,),
    )
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
        _logger.info("limpieza v19: %s modulos obsoletos marcados como uninstalled", cr.rowcount)


def _desactivar_crons_obsoletos(cr):
    cr.execute(
        """
        UPDATE ir_cron SET active = False
         WHERE id IN (
             SELECT res_id FROM ir_model_data 
              WHERE model = 'ir.cron' 
                AND module IN %s
         )
         OR ir_actions_server_id IN (
             SELECT id FROM ir_act_server 
              WHERE model_name IN %s
         )
        """,
        (MODULES_TO_UNINSTALL, REMOVED_MODELS),
    )
    if cr.rowcount:
        _logger.info("limpieza v19: %s crons obsoletos desactivados", cr.rowcount)


def _limpiar_vistas(cr, pattern):
    cr.execute(
        """
        SELECT v.id, v.model, COALESCE(d.module || '.' || d.name, '(sin xml_id)')
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
    rows = cr.fetchall()
    if not rows:
        _logger.info("limpieza v19: no quedan vistas obsoletas")
        return

    for view_id, model, xml_id in rows:
        _logger.info("limpieza v19: vista obsoleta %s (id=%s, modelo=%s)", xml_id, view_id, model)

    seeds = tuple({row[0] for row in rows})
    cr.execute(
        """
        WITH RECURSIVE arbol(id) AS (
            SELECT id FROM ir_ui_view WHERE id IN %s
            UNION
            SELECT h.id FROM ir_ui_view h JOIN arbol a ON h.inherit_id = a.id
        )
        SELECT id FROM arbol
        """,
        (seeds,),
    )
    pendientes = {row[0] for row in cr.fetchall()}
    if len(pendientes) > len(seeds):
        _logger.info("limpieza v19: %s vistas hijas arrastradas", len(pendientes) - len(seeds))

    total = 0
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
            raise RuntimeError(
                "limpieza v19: no se pueden borrar las vistas %s, quedan referenciadas "
                "por hijas fuera del arbol calculado" % sorted(pendientes)
            )
        pendientes -= borradas
        total += len(borradas)

    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE model = 'ir.ui.view'
           AND res_id NOT IN (SELECT id FROM ir_ui_view)
        """
    )
    _logger.info("limpieza v19: %s vistas obsoletas eliminadas", total)


def _limpiar_acciones(cr, pattern):
    cr.execute(
        """
        SELECT a.id, COALESCE(d.module || '.' || d.name, '(sin xml_id)')
          FROM ir_act_window a
          LEFT JOIN ir_model_data d
            ON d.model = 'ir.actions.act_window' AND d.res_id = a.id
         WHERE COALESCE(a.domain, '') ~ %s
            OR COALESCE(a.context, '') ~ %s
            OR a.res_model IN %s
            OR d.module IN %s
        """,
        (pattern, pattern, REMOVED_MODELS, MODULES_TO_UNINSTALL),
    )
    acciones = cr.fetchall()
    if acciones:
        for act_id, xml_id in acciones:
            _logger.info("limpieza v19: accion obsoleta %s (id=%s)", xml_id, act_id)
        act_ids = tuple(a[0] for a in acciones)
        cr.execute(
            """
            DELETE FROM ir_ui_menu
             WHERE action IN (
                 SELECT 'ir.actions.act_window,' || id FROM ir_act_window WHERE id IN %s
             )
            """,
            (act_ids,),
        )
        cr.execute("DELETE FROM ir_act_window WHERE id IN %s", (act_ids,))
        _logger.info("limpieza v19: %s acciones obsoletas eliminadas", len(act_ids))

    cr.execute(
        """
        DELETE FROM ir_filters
         WHERE COALESCE(domain, '') ~ %s
            OR COALESCE(context, '') ~ %s
            OR model_id IN %s
     RETURNING name, model_id
        """,
        (pattern, pattern, REMOVED_MODELS),
    )
    filtros = cr.fetchall()
    for nombre, modelo in filtros:
        _logger.info("limpieza v19: filtro guardado obsoleto '%s' en %s", nombre, modelo)

    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE (model = 'ir.actions.act_window' AND res_id NOT IN (SELECT id FROM ir_act_window))
            OR (model = 'ir.ui.menu' AND res_id NOT IN (SELECT id FROM ir_ui_menu))
        """
    )
