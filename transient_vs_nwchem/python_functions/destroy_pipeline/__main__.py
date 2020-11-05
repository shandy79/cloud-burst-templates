import ibm_fn_helper as ifh


def main(data):
    doc_id = data['id']

    cloudant_obj = ifh.cloudant_init(doc_id)
    if cloudant_obj['error'] is not None:
        return { 'error': cloudant_obj['error'] }

    # Verify that processing is complete
    if 'status' in cloudant_obj['doc'] and cloudant_obj['doc']['status'] != 'complete':
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
        return { 'continue': f'Processing incomplete. (DP:{doc_id})' }

    # Validate JSON document for required information
    if 'compute_target' not in cloudant_obj['doc']:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'"compute_target" not in document!')
        return { 'error': cloudant_obj['error'] }

    try:
        vg = ifh.sl_cancel_transient_vg(cloudant_obj['doc']['compute_target'])
    except Exception:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Unable to cancel Virtual Guest "{cloudant_obj["doc"]["compute_target"]}"!')
        return { 'error': cloudant_obj['error'] }

    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)

    message = f'NWChem virtual guest cancelled (DP:{doc_id})'
    print(message)

    return { 'change': message }
