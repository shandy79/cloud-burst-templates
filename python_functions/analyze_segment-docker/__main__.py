import ibm_fn_helper as ifh
from analyze_segment import analyze_segment

from datetime import datetime
from ibm_botocore.exceptions import ClientError
import numpy as np
import gc, os, subprocess, sys
from requests import HTTPError


COMPUTE_TARGET = 'fn:analyzeSegmentChange'
SW_VERSION = 'analysis_code:v0.1'  # i.e., a description and version of the analytical code


def save_segment(doc):
    result = False

    for _ in range(ifh.CLOUDANT_409_RETRIES):
        try:
            doc.save()
        except HTTPError as err:
            if err.response.status_code == 409:
                print(f'409 HTTPError: attempting to re-save (analyze_segment:{doc["_id"]})')
        else:
            result = True
            break

    return result


def main(data):
    doc_id = data['id']

    # Added with recommendation from IBM in an attempt to prevent OOM errors on repeated Function invocations
    gc.collect()

    cloudant_obj = ifh.cloudant_init(doc_id)
    if cloudant_obj['error'] is not None:
        return { 'error': cloudant_obj['error'] }

    # Validate JSON document for COS information
    if 'raw_cos_bucket' not in cloudant_obj['doc'] or 'cos_file_raw' not in cloudant_obj['doc']:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'"raw_cos_bucket" and/or "cos_file_raw" not in document!')
        return { 'error': cloudant_obj['error'] }

    # Validate JSON document for segment type
    if 'type' not in cloudant_obj['doc'] or cloudant_obj['doc']['type'] != ifh.SEGMENT_TYPE:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
        return { 'continue': f'Not analyzing (analyze_segment:{doc_id})' }

    # Validate segment not yet analyzed
    if 'compute_end' in cloudant_obj['doc']:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
        return { 'continue': f'Analysis already complete (analyze_segment:{doc_id})' }

    # If a segment to analyze was identified
    cloudant_obj['doc']['sw_version'] = SW_VERSION
    cloudant_obj['doc']['compute_target'] = COMPUTE_TARGET

    cloudant_obj['doc']['cos_file_output'] = cloudant_obj['doc']['raw_id'] + '/' + ifh.SEGMENT_TYPE + '/' + cloudant_obj['doc']['id'] + '.npy'
    now = datetime.now()
    cloudant_obj['doc']['compute_start'] = str(now)

    # Download segment file from COS
    cos_bucket = cloudant_obj['doc']['raw_cos_bucket']
    cos_file_path = cloudant_obj['doc']['cos_file_raw']
    local_segment_path = '/tmp/' + cos_file_path
    os.makedirs(os.path.dirname(local_segment_path), exist_ok=True)

    try:
        ifh.cos_download_file(cos_bucket, cos_file_path, local_segment_path)
    except ClientError:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'COS file "{cos_file_path}" does not exist!')
        return { 'error': cloudant_obj['error'] }

    raw_data = np.load(local_segment_path)

    #### TODO: Run analysis algorithms on this raw data segment (represented as a NumPy array)
    analyzed_segment = analyze_segment(raw_data)

    try:
        # Save analyzed data to COS
        np.save(local_segment_path, analyzed_segment)
        ifh.cos_multi_part_upload(cos_bucket, cloudant_obj['doc']['cos_file_output'], local_segment_path)
        now = datetime.now()
        cloudant_obj['doc']['compute_end'] = str(now)

        # Delete local tmp file
        os.remove(local_segment_path)

    except Exception as e:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Exception occurred in {doc_id}!\n{str(e)}')
        return { 'error': cloudant_obj['error'] }

    # Update full JSON snippet for this segment
    result = save_segment(cloudant_obj['doc'])
    if result == False:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Unable to save document!')
        return { 'error': cloudant_obj['error'] }

    # Delete COS raw file
    if cloudant_obj['doc']['id'] != 'S0':
        ifh.cos_delete_item(cos_bucket, cos_file_path)

    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)

    message = f'Segment analyzed (analyze_segment:{doc_id})'
    print(message)

    # Remaining lines are an attempt to prevent container reuse by the IBM Cloud w/the idea that intermittent
    # failures of this Function are due to a memory leak causing later invocations to exceed the maximum permitted
    # memory allocation.  Suggested by Michael Behrendt of IBM Cloud.

    #### TODO: Set any larger data structures to 'None' here

    # Capture output from Linux 'free' command for debugging
    # https://docs.python.org/3.6/library/subprocess.html
    exec_output = subprocess.run(args=['free'], check=True, stdout=subprocess.PIPE, encoding='utf-8')
    cmd_output = exec_output.stdout
    mem_list = cmd_output.split('\n')[1].split()
    mem_str = f'total={mem_list[1]}, used={mem_list[2]}, free={mem_list[3]}'

     # NOTE: This will prevent normal return of this Function, but it will prevent the memory leak in the container
    sys.exit(mem_str)

    return { 'change': message, 'free': mem_str }
