import logging

logger = logging.getLogger(__name__)


def write_association_audit(data_source, object_type, src_id, tgt_type, tgt_id,
                            action, association_name, user_id, user_name):
    try:
        from meta.services.audit_interceptor import AuditInterceptor
        audit = AuditInterceptor(data_source)
        assoc_name = association_name or object_type
        uid = str(user_id) if user_id else None
        uname = user_name or 'system'

        if action == 'ASSOCIATE':
            audit.log_associate(
                object_type=object_type, object_id=src_id,
                tgt_type=tgt_type, tgt_id=tgt_id,
                association_name=assoc_name, user_id=uid, user_name=uname,
            )
        elif action == 'DISSOCIATE':
            audit.log_dissociate(
                object_type=object_type, object_id=src_id,
                tgt_type=tgt_type, tgt_id=tgt_id,
                association_name=assoc_name, user_id=uid, user_name=uname,
            )
        logger.info("[Audit] Logged %s: %s/%s -> %s/%s via %s by %s",
                    action, object_type, src_id, tgt_type, tgt_id, assoc_name, uname)
    except Exception:
        logger.debug("[Audit] Audit logging skipped (no audit tables)")
