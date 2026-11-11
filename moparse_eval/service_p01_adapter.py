"""Thin P01 development compatibility wrapper over the shared native adapter."""
from app.adapters.native_readers import audit_copy as audit_copy
from app.adapters.saved_native import adapt_saved_document


def adapt_p01(native, source, options, *, document_id, include_source_markers=False, **evidence):
    if native.get('pipeline') != 'P01':
        raise ValueError('P01 wrapper requires its declared configuration')
    return adapt_saved_document(native, source, options, document_id=document_id,
                                include_source_markers=include_source_markers, **evidence)
