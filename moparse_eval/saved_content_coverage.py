"""Input-owned reverse destinations, separate from stage edit replay."""
from __future__ import annotations

from dataclasses import asdict

from app.services.native_content_evidence import NativeContentError, validate_native_content


def native_destinations(result, dispositions):
    contract = validate_native_content(result)
    by_occurrence = {(d['page'], d['occurrence_id']): d for d in dispositions}
    output = []
    for item in contract.items:
        record = {'identity': item.identity, 'kind': item.kind, 'locator': asdict(item.locator),
                  'page': item.input_page, 'parent': item.parent}
        if item.kind == 'metadata' and item.details.get('purpose') == 'native_visual_text_component':
            owner = by_occurrence.get((item.input_page, item.parent))
            if owner is None:
                raise NativeContentError('visual text component lost its adapted owner: ' + item.identity)
            record.update(destination='explicitly_excluded_furniture' if owner['disposition'] == 'explicitly_excluded_furniture'
                          else 'consumed', source_type=item.details['source_type'],
                          adapted_owner=item.parent, owner_destination=owner['disposition'],
                          owner_final_spans=owner['final_spans'], span_basis='owner_display_not_document_charspan')
        elif item.kind in {'container', 'metadata'}:
            record.update(destination='immutable_native_audit', reason='structure_or_metadata_not_markdown_content')
        elif item.kind == 'cell':
            owner = by_occurrence.get((item.input_page, item.parent))
            candidates = [c for c in (owner or {}).get('cells', []) if c.get('native_cell_id', c.get('native_path')) == item.identity]
            if candidates:
                if owner['disposition'] == 'converted' and candidates[0]['disposition'] == 'unresolved_final_location':
                    raise NativeContentError('converted native cell has no actual final span: ' + item.identity)
                record.update(destination=candidates[0]['disposition'], final_spans=candidates[0]['final_spans'],
                              adapted_owner=item.parent)
            elif owner and owner['disposition'] in {'unresolved_retained', 'retained'}:
                record.update(destination='unresolved_source_grid_retained', adapted_owner=item.parent,
                              final_spans=owner['final_spans'])
            else:
                record.update(destination='unresolved_native_readback', adapted_owner=item.parent)
        elif item.kind == 'media':
            record.update(destination='unverified_not_delivered', adapted_owner=item.parent,
                          bytes_read=False, image_semantics='out_of_scope')
        else:
            owner = by_occurrence.get((item.input_page, item.identity))
            if owner is None:
                record.update(destination='unresolved_native_readback')
            else:
                record.update(destination=owner['disposition'], final_spans=owner['final_spans'],
                              adapted_owner=owner['occurrence_id'])
                for a, b in owner['final_spans']:
                    if not 0 <= a <= b <= len(result.markdown):
                        raise NativeContentError('final destination outside actual delivered text')
                if owner['disposition'] == 'unresolved_final_location':
                    raise NativeContentError('available native occurrence has no final destination: ' + item.identity)
        output.append(record)
    return output
