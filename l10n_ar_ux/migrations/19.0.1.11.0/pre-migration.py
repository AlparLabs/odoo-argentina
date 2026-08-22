import logging

_logger = logging.getLogger(__name__)

# Campos que los modulos custom eliminaron al pasar de 18.0 a 19.0. Sus vistas,
# acciones y filtros siguen vivos en la base despues del upgrade. Los modulos que
# desaparecieron del codigo (account_tax_settlement, l10n_ar_account_tax_settlement)
# nunca cargan, asi que Odoo tampoco limpia sus registros obsoletos solo.
# Rompen de dos formas:
#   - vistas: "Field settled_line_ids does not exist in model account.move" al
#     revalidar el arch combinado de cualquier vista del mismo modelo
#   - acciones y filtros: "Invalid field account.journal.tax_settlement in
#     condition" al abrir el menu que apunta a una accion con domain viejo
# Lista obtenida diffeando origin/18.0 contra el commit desplegado en los ocho
# submodulos: campos borrados que tenian vista en v18 y ya no existen en v19.
REMOVED_FIELDS = (
    "allow_move_with_valuation_cancelation",
    "arba_warning_html",
    "autofilled_check_number",
    "bundle_counterpart_currency_amount",
    "check_sequence_next_number",
    "counterpart_exchange_rate",
    "create_new_rfq",
    "exchange_rate",
    "incl_in_payment",
    "incl_paid",
    "incl_partial",
    "interest_ids",
    "l10n_ar_afip_activity_id",
    "lock_posted_moves",
    "settled_line_ids",
    "settlement_account_id",
    "settlement_account_tag_ids",
    "settlement_partner_id",
    "tax_settlement",
    "tax_settlement_move_id",
    "tax_state",
    "txt_binary",
    "update_constancia",
    "use_search_filter_amount",
)

# Modelos eliminados en 19.0: sus vistas quedan huerfanas.
REMOVED_MODELS = ("afip.activity",)


def migrate(cr, version):
    """Limpia vistas, acciones, menus y filtros que apuntan a campos removidos en v19.

    Idempotente. Todo lo borrado que siga existiendo en el codigo se recrea cuando
    carga su modulo; revisar el log por si aparece algo de studio_customization,
    que vive solo en la base y no se regenera.
    """
    pattern = r"\y(" + "|".join(REMOVED_FIELDS) + r")\y"

    _limpiar_vistas(cr, pattern)
    _limpiar_acciones(cr, pattern)


def _limpiar_vistas(cr, pattern):
    # Se excluyen las qweb: los templates de reporte no se validan contra los
    # campos del modelo, no rompen la carga, y borrarlos arrastraria a sus hijos.
    cr.execute(
        """
        SELECT v.id, v.model, COALESCE(d.module || '.' || d.name, '(sin xml_id)')
          FROM ir_ui_view v
          LEFT JOIN ir_model_data d
            ON d.model = 'ir.ui.view' AND d.res_id = v.id
         WHERE v.type != 'qweb'
           AND (v.arch_db::text ~ %s OR v.model IN %s)
        """,
        (pattern, REMOVED_MODELS),
    )
    rows = cr.fetchall()
    if not rows:
        _logger.info("limpieza v19: no quedan vistas obsoletas")
        return

    for view_id, model, xml_id in rows:
        _logger.info("limpieza v19: vista obsoleta %s (id=%s, modelo=%s)", xml_id, view_id, model)

    # ir_ui_view.inherit_id es ondelete='restrict' en la base: el cascade lo emula
    # el ORM en Python. Desde SQL hay que arrastrar los hijos a mano.
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
    while pendientes:  # de hojas hacia la raiz, por el FK restrict
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
    """Acciones de ventana con domain/context viejo, sus menus, y filtros guardados."""
    cr.execute(
        """
        SELECT a.id, COALESCE(d.module || '.' || d.name, '(sin xml_id)')
          FROM ir_act_window a
          LEFT JOIN ir_model_data d
            ON d.model = 'ir.actions.act_window' AND d.res_id = a.id
         WHERE COALESCE(a.domain, '') ~ %s
            OR COALESCE(a.context, '') ~ %s
        """,
        (pattern, pattern),
    )
    acciones = cr.fetchall()
    if acciones:
        for act_id, xml_id in acciones:
            _logger.info("limpieza v19: accion obsoleta %s (id=%s)", xml_id, act_id)
        act_ids = tuple(a[0] for a in acciones)
        # ir_ui_menu.action guarda la referencia como texto 'ir.actions.act_window,ID'
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

    # favoritos guardados por usuarios: no los recrea nadie, pero rompen la busqueda
    cr.execute(
        """
        DELETE FROM ir_filters
         WHERE COALESCE(domain, '') ~ %s
            OR COALESCE(context, '') ~ %s
     RETURNING name, model_id
        """,
        (pattern, pattern),
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
