import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _logger.info("l10n_ar_tax: running pre-migration for %s", version)

    # Delete report_payment_receipt_reversal_moves to prevent xpath error
    # ("Element <xpath expr=\"//span[hasclass('reversal_move_lines')]\"> cannot be located in parent view")
    # when updating the parent template report_payment_receipt_document in 19.0.
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE model = 'ir.ui.view'
            AND module = 'l10n_ar_tax'
            AND name = 'report_payment_receipt_reversal_moves'
        )
    """)
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.ui.view'
        AND module = 'l10n_ar_tax'
        AND name = 'report_payment_receipt_reversal_moves'
    """)
