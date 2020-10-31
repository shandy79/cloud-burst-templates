import ibm_fn_helper as ifh

import argparse
from datetime import datetime
from ibm_botocore.exceptions import ClientError
import json
import os
import re
from requests import HTTPError
import sys


OUTPUT_DIR_DESC=f'a directory to which output files will be written'


def cos_handle_file(cos_bucket, cos_file, batch_dir):
    file_path = f'{batch_dir}/{cos_file}'
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    try:
        ifh.aspera_file_download(cos_bucket, cos_file, file_path)
        ifh.cos_delete_item(cos_bucket, cos_file)
    except ClientError as e:
        print(f'COS file download error ({cos_file})!\n{str(e)}')
        return False

    return True


# Start script execution
if __name__ == '__main__':
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
        view_result = cloudant_obj['db'].get_view_result('_design/cloudant_views', 'complete', include_docs=True)
        results = view_result.all()
    except HTTPError as e:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Cloudant view error!\n{str(e)}')
        sys.exit(cloudant_obj['error'])

    print(f'The following jobs have completed processing:')
    # For each completed batch, create an output directory and write the JSON document
    for r in results:
        doc = r['doc']

        with open(f'{output_dir}/{doc["_id"]}.json', 'w') as f:
            json.dump(doc, f, indent=4)

        # Create an output directory and download the segment result files
        if ifh.SEGMENT_TYPE in doc and 'cos_file_output' in doc[ifh.SEGMENT_TYPE] and ifh.cos_item_exists(doc['cos_bucket'], doc[ifh.SEGMENT_TYPE]['cos_file_output']):
            cos_handle_file(doc['cos_bucket'], doc[ifh.SEGMENT_TYPE]['cos_file_output'], output_dir)

        # Delete JSON document from Cloudant
        del_doc = cloudant_obj['db'][r['id']]
        del_doc.delete()

        print(f' - {doc["_id"]}: download complete')

    # Get the incomplete batch JSON documents from the Cloudant view
    try:
        view_result = cloudant_obj['db'].get_view_result('_design/cloudant_views', 'incomplete', include_docs=True)
        results = view_result.all()
    except HTTPError as e:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Cloudant view error!\n{str(e)}')
        sys.exit(cloudant_obj['error'])

    print(f'The following jobs have not completed processing:')
    for r in results:
        doc = r['doc']

        # Looks at only first cleaning and inference segment per batch
        segments_start = ''
        if 'segments' in doc[ifh.SEGMENT_TYPE] and type(doc[ifh.SEGMENT_TYPE]['segments']) is list:
            segments_start = doc[ifh.SEGMENT_TYPE]['segments'][0]['compute_start']

        if len(segments_start) > 0:
            segments_start = ' from ' + re.sub(r'\.\d+$', '', segments_start)

        print(f'  - {doc["_id"]}: {ifh.SEGMENT_TYPE}={doc[ifh.SEGMENT_TYPE]["status"]}{segments_start}')

    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
