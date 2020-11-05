import ibm_fn_helper as ifh

from datetime import datetime
import requests


def main(data):
    doc_id = data['id']

    cloudant_obj = ifh.cloudant_init(doc_id)
    if cloudant_obj['error'] is not None:
        return { 'error': cloudant_obj['error'] }

    # Verify that processing needs to be completed
    if 'status' in cloudant_obj['doc'] and cloudant_obj['doc']['status'] != 'pending':
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
        return { 'continue': f'Processing already started. (CP:{doc_id})' }

    # Validate JSON document for required information
    if 'cos_bucket' not in cloudant_obj['doc'] or 'cpus' not in cloudant_obj['doc'] or len(cloudant_obj['doc']['inputs']) == 0:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'"cos_bucket" and/or "cpus" and/or "inputs" not in document!')
        return { 'error': cloudant_obj['error'] }

    valid_input = False

    for nw_input in cloudant_obj['doc']['inputs']:
        if 'id' not in nw_input or 'cos_file_input' not in nw_input:
            nw_input['error'] = 'Missing required fields!'
            continue
        else:
            valid_input = True

    #### Spin up VSI and submit POST of doc to Flask once it's running
    if valid_input:
        cloudant_obj['doc']['status'] = 'processing'
        cloudant_obj['doc']['sw_version'] = ifh.SW_VERSION

        now = datetime.now()
        nowf = now.strftime('%Y%m%d%H%M%S%f')

        hostname = f'nwchemcloud-{nowf}'

        try:
            vg, webhook_return_val = ifh.sl_create_transient_vg(hostname, 'mgnwcsm-reclaim-scheduled', ifh.FLASK_PORT, cloudant_obj['doc']['cpus'])
        except Exception as e:
            cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Unable to create Virtual Guest "{hostname}" ({vg["id"]}/{vg["primaryIpAddress"]})!  {str(e)}', save=True)
            return { 'error': cloudant_obj['error'] }
 
        cloudant_obj['doc']['compute_target'] = vg['id']
        cloudant_obj['doc']['compute_webhook'] = webhook_return_val

        # Submit JSON POST to new VSI to execute NWChem
        # https://requests.kennethreitz.org/en/master/user/quickstart/#errors-and-exceptions
        try:
            response = requests.post(f'http://{vg["primaryIpAddress"]}:{ifh.FLASK_PORT}/', json={ 'id': doc_id })
            response.raise_for_status()
        except requests.HTTPError:
            cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Unable to POST to Virtual Guest {vg["id"]}!', save=True)
            return { 'error': cloudant_obj['error'] }

    # Save the JSON document and cleanup
    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, save=True)

    message = f'NWChem started (CP:{doc_id})'
    print(message)

    return { 'change': message }
