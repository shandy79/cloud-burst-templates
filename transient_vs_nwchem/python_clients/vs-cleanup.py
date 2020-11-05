import ibm_fn_helper as ifh

from ibm_botocore.exceptions import ClientError
import json
from requests import HTTPError
import SoftLayer
import sys

# Connect to Cloudant
cloudant_obj = ifh.cloudant_init(None)
if cloudant_obj['error'] is not None:
    sys.exit(f'Cloudant error!  {cloudant_obj["error"]}')

# Get the not_pending batch JSON documents from the Cloudant view
try:
    view_result = cloudant_obj['db'].get_view_result('_design/nwchemcloud_cleanup', 'not_pending', include_docs=True)
    results = view_result.all()
except HTTPError as e:
    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Cloudant view error!\n{str(e)}')
    sys.exit(cloudant_obj['error'])

good_vsis = list()

for r in results:
    doc = r['doc']
#    print(doc)
    good_vsis.append(doc['compute_target'])

print(f'{len(good_vsis)} good VSIs found!')

client = SoftLayer.Client(username=ifh.SL_API_USERNAME, api_key=ifh.SL_API_KEY)
_maskVirtualGuest = 'id, hostname'
vsi_count = 0

try:
    getHourlyVG = client['SoftLayer_Account'].getHourlyVirtualGuests(mask=_maskVirtualGuest)
#    print(json.dumps(getHourlyVG, sort_keys=True, indent=2, separators=(',', ': ')))

    for v in getHourlyVG:
        if v['id'] not in good_vsis and v['hostname'].startswith('nwchemcloud-2019'):
            print(f'Cancelling VSI {v["id"]} ({vsi_count + 1}) . . .')
            vg = ifh.sl_cancel_transient_vg(v['id'])
            vsi_count += 1
except Exception as e:
    print('Received exception: %s' % (e))

print(f'{vsi_count} orphaned VSIs cancelled!')

# Get Cloudant documents for orphaned and reclaimed VSIs, clean up associated COS documents, then delete Cloudant documents
try:
    view_result = cloudant_obj['db'].get_view_result('_design/nwchemcloud_cleanup', 'pending', include_docs=True)
    results = view_result.all()
except HTTPError as e:
    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Cloudant view error!\n{str(e)}')
    sys.exit(cloudant_obj['error'])

print('Deleting COS and Cloudant objects for orphaned "pending" runs!')
for r in results:
    doc = r['doc']
    print(f'. . . {doc["_id"]}')

    # For each input, create an output directory and download the input, output, and result files
    for i in doc['inputs']:
        ifh.cos_delete_item(doc['cos_bucket'], i['cos_file_input'])

        if 'cos_file_output' in i and ifh.cos_item_exists(doc['cos_bucket'], i['cos_file_output']):
            ifh.cos_delete_item(doc['cos_bucket'], i['cos_file_output'])

        if 'cos_results' in i:
            for c in i['cos_results']:
                ifh.cos_delete_item(doc['cos_bucket'], c)

    # Delete JSON document from Cloudant
    del_doc = cloudant_obj['db'][r['id']]
    del_doc.delete()

# Get Cloudant documents for orphaned and reclaimed VSIs, clean up associated COS documents, then delete Cloudant documents
try:
    view_result = cloudant_obj['db'].get_view_result('_design/nwchemcloud_cleanup', 'reclaimed', include_docs=True)
    results = view_result.all()
except HTTPError as e:
    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Cloudant view error!\n{str(e)}')
    sys.exit(cloudant_obj['error'])

print('Deleting COS and Cloudant objects for "reclaimed" runs!')
for r in results:
    doc = r['doc']
    if not doc['_id'].startswith('stress'):
        print(f'. . . skipping {doc["_id"]}')
        continue

    print(f'. . . {doc["_id"]}')

    # For each input, create an output directory and download the input, output, and result files
    for i in doc['inputs']:
        ifh.cos_delete_item(doc['cos_bucket'], i['cos_file_input'])

        if 'cos_file_output' in i and ifh.cos_item_exists(doc['cos_bucket'], i['cos_file_output']):
            ifh.cos_delete_item(doc['cos_bucket'], i['cos_file_output'])

        if 'cos_results' in i:
            for c in i['cos_results']:
                ifh.cos_delete_item(doc['cos_bucket'], c)

    # Delete JSON document from Cloudant
    del_doc = cloudant_obj['db'][r['id']]
    del_doc.delete()

cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
