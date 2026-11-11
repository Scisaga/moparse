"""Compatibility entry for P01 development callers; shared conversion implementation."""
from .saved_content_closure import close_saved_document
from .saved_content_closure import content_dispositions as content_dispositions
from .saved_content_closure import format_readback_checks as format_readback_checks
from .saved_content_closure import main as main


async def close_p01_document(native, source, **kwargs):
    if native.get('pipeline') != 'P01':
        raise ValueError('P01 wrapper requires its own native configuration')
    return await close_saved_document(native, source, **kwargs)


if __name__ == '__main__':
    raise SystemExit(main())
