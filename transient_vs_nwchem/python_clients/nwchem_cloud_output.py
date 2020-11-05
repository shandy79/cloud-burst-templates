import ibm_fn_helper as ifh

import argparse
from datetime import datetime
from ibm_botocore.exceptions import ClientError
import json
import os
from requests import HTTPError
import sys


OUTPUT_DIR_DESC=f'a directory to which output files will be written'


def cos_handle_file(cos_bucket, cos_file, batch_dir):
    file_path = f'{batch_dir}/{cos_file}'
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    try:
        ifh.cos_download_file(cos_bucket, cos_file, file_path)
        ifh.cos_delete_item(cos_bucket, cos_file)
    except ClientError as e:
        print(f'COS file download error ({cos_file})!\n{str(e)}')
        return False

    return True


# Start script execution
parser = argparse.ArgumentParser()
parser.add_argument('outdir', help=OUTPUT_DIR_DESC, type=str)

args = parser.parse_args()

output_dir = args.outdir

if os.path.isdir(output_dir) == False:
    sys.exit(f'Invalid input!  The argument should be {OUTPUT_DIR_DESC}.')

# Connect to Cloudant
cloudant_obj = ifh.cloudant_init(None)
if cloudant_obj['error'] is not None:
    sys.exit(f'Cloudant error!  {cloudant_obj["error"]}')

# Get the completed batch JSON documents from the Cloudant view
try:
    view_result = cloudant_obj['db'].get_view_result('_design/nwchemcloud_views', 'complete', include_docs=True)
    results = view_result.all()
except HTTPError as e:
    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Cloudant view error!\n{str(e)}')
    sys.exit(cloudant_obj['error'])

# For each completed batch, create an output directory and write the JSON document
#    "inputs": [
#        {
#            "id": "<molecule_name>-0",
#            "cos_file_input": "<batch_id>/<id>/input_file.nw",
#            "cos_file_output": "<batch_id>/<id>/output_file.out",
#            "cos_results": [
#              "<batch_id>/<id>/result_file-0",
#            ]
#        }
#    ]
for r in results:
    doc = r['doc']

    with open(f'{output_dir}/{doc["_id"]}.json', 'w') as f:
        json.dump(doc, f, indent=4)

    # For each input, create an output directory and download the input, output, and result files
    for i in doc['inputs']:
        cos_handle_file(doc['cos_bucket'], i['cos_file_input'], output_dir)

        if ifh.cos_item_exists(doc['cos_bucket'], i['cos_file_output']):
            cos_handle_file(doc['cos_bucket'], i['cos_file_output'], output_dir)

        if 'cos_results' in i:
            for c in i['cos_results']:
                cos_handle_file(doc['cos_bucket'], c, output_dir)

        if 'compute_end' not in i:
            print(f'Input {doc["_id"]}:{i["id"]} did not complete!')

    # Delete JSON document from Cloudant
    del_doc = cloudant_obj['db'][r['id']]
    del_doc.delete()

# Get the incomplete batch JSON documents from the Cloudant view
try:
    view_result = cloudant_obj['db'].get_view_result('_design/nwchemcloud_views', 'incomplete', include_docs=True)
    results = view_result.all()
except HTTPError as e:
    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Cloudant view error!\n{str(e)}')
    sys.exit(cloudant_obj['error'])

print(f'The following jobs have not completed processing:')
for r in results:
    doc = r['doc']

    # Assumes only one molecule per batch
    if 'compute_start' in doc['inputs'][0]:
        then = datetime.strptime(doc['inputs'][0]['compute_start'], '%Y-%m-%d %H:%M:%S.%f')
    else:
        then = ''

    if 'compute_end' in doc['inputs'][0]:
        now = datetime.strptime(doc['inputs'][0]['compute_end'], '%Y-%m-%d %H:%M:%S.%f')
        time_str = f'ran for {now - then}'
    elif isinstance(then, datetime):
        time_str = f'since {datetime.strftime(then, "%Y-%m-%d %H:%M")}'
    else:
        time_str = 'VM is initializing'

    print(f'  - {doc["_id"]}: {doc["status"]} | {doc["inputs"][0]["local_root"]} | {time_str}')

cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
