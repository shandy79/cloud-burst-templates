import ibm_fn_helper as ifh
from reassemble_segments import reassemble_segments

import h5py
import numpy as np
import os
from requests import HTTPError
import time


# Queries incomplete view for the parent doc to determine if any segments have not been analyzed
def is_analysis_complete(cloudant_db, raw_id):
    try:
        view_result = cloudant_db.get_view_result('_design/' + ifh.SEGMENT_TYPE + '-' + raw_id, ifh.SEGMENT_TYPE + '-' + raw_id + '-incomplete', limit=1)
        results = view_result.all()
        if len(results) > 0:
            return False
        else:
            return True
    except HTTPError as err:
        print(f'Incomplete view "{err.response.status_code}" error! (reassemble_segments:{raw_id})')
        if err.response.status_code == 404:
            return True
        else:
            return False

    return False


def main(data):
    doc_id = data['id']

    cloudant_obj = ifh.cloudant_init(doc_id)
    if cloudant_obj['error'] is not None:
        return { 'error': cloudant_obj['error'] }

    # Validate JSON document for COS information
    if 'raw_cos_bucket' in cloudant_obj['doc']:
        cos_bucket = cloudant_obj['doc']['raw_cos_bucket']
    else:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'"raw_cos_bucket" not in document!')
        return { 'error': cloudant_obj['error'] }

    # Validate JSON document for step type
    if 'type' not in cloudant_obj['doc'] or cloudant_obj['doc']['type'] != ifh.SEGMENT_TYPE:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
        return { 'continue': f'Not analyzing (reassemble_segments:{doc_id})' }

    # Validate segment has been analyzed
    if 'compute_end' not in cloudant_obj['doc']:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
        return { 'continue': f'Analysis not complete (reassemble_segments:{doc_id})' }

    # Retrieve the parent document to checking analysis status
    if 'raw_id' in cloudant_obj['doc']:
        raw_id = cloudant_obj['doc']['raw_id']
    else:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'"raw_id" not in document!')
        return { 'error': cloudant_obj['error'] }

    if raw_id in cloudant_obj['db']:
        raw_doc = cloudant_obj['db'][raw_id]
    else:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Raw document does not exist!')
        return { 'error': cloudant_obj['error'] }

    # If analysis marked as complete, then post-analysis cleanup has already started
    if ifh.SEGMENT_TYPE in raw_doc and 'status' in raw_doc[ifh.SEGMENT_TYPE] and raw_doc[ifh.SEGMENT_TYPE]['status'] == 'complete':
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
        return { 'continue': f'Post-analysis cleanup already started 1 (reassemble_segments:{doc_id})' }

    # Verify that all segments have been analyzed
    if cloudant_obj['doc']['last_seg'] == 'true':
        all_clean = False
        while not all_clean:
            time.sleep(30)
            all_clean = is_analysis_complete(cloudant_obj['db'], raw_id)
    else:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
        return { 'continue': f'Analysis not complete for the final segment (reassemble_segments:{doc_id})' }

    # Update parent document analysis status to prevent other functions from starting post-analysis cleanup.
    # If analysis marked as complete after fetch(), then post-analysis cleanup has already been started by another
    # function invocation while this invocation was checking the incomplete view.  Exit here to prevent 409 Conflict error.
    for _ in range(ifh.CLOUDANT_409_RETRIES):
        try:
            raw_doc.fetch()
            if ifh.SEGMENT_TYPE in raw_doc and 'status' in raw_doc[ifh.SEGMENT_TYPE] and raw_doc[ifh.SEGMENT_TYPE]['status'] == 'complete':
                cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
                return { 'continue': f'Post-analysis cleanup already started 2 (reassemble_segments:{doc_id})' }

            raw_doc[ifh.SEGMENT_TYPE]['status'] = 'complete'
            raw_doc.save()
        except HTTPError as err:
            if err.response.status_code == 409:
                print(f'409 HTTPError: attempting to re-save (reassemble_segments:{raw_doc["_id"]}')
        else:
            break

    # Query "complete" view for this raw ID to obtain all segment documents
    view_result = cloudant_obj['db'].get_view_result('_design/' + ifh.SEGMENT_TYPE + '-' + raw_id, ifh.SEGMENT_TYPE + '-' + raw_id + '-complete', include_docs=True)
    try:
        results = view_result.all()
    except HTTPError as err:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Complete view "{err.response.status_code}" error!')
        return { 'error': cloudant_obj['error'] }

    # Load from view results to segments list, sorted by segment ID
    segments = []
    segment_idx = None
    sw_version = None

    for r in results:
        segment = r['value']
        segment_idx = int(segment['id'][1:])
        while segment_idx >= len(segments):
            segments.append(0)
        segments[segment_idx] = segment
        sw_version = segment['sw_version']

        # Delete Cloudant analyzed segment document
        # Deleting S0 if debug flag is not t, else saving S0 for debugging
        if segment_idx != 0 or raw_doc[ifh.SEGMENT_TYPE]['debug_retention_flag'] != 't':  
            del_doc = cloudant_obj['db'][r['id']]
            del_doc.delete()

    output_path = '/tmp/' + raw_id + '-' + ifh.SEGMENT_TYPE + '.' + ifh.OUTPUT_FILE_EXT

    # Reconstruct the segments into the output file
    reassemble_segments(cos_bucket, output_path, segments)

    # Deleting all SO debug files from COS not specified by -d flag
    if raw_doc[ifh.SEGMENT_TYPE]['debug_retention_flag'] != 't':
        ifh.cos_delete_item(cos_bucket, raw_doc['_id'] + '/' + ifh.SEGMENT_TYPE + '/S0.npy')
    if raw_doc['raw']['raw_debug_retention_flag'] != 't':
        ifh.cos_delete_item(cos_bucket, raw_doc['_id'] + '/raw/S0.npy')

    # Deletion of the 0 byte file with no extension left in COS
    input_file_no_ext, _ = raw_doc['raw']['cos_path'].split('/')
    ifh.cos_delete_item(cos_bucket, input_file_no_ext + '/')

    # Upload re-stitched, analyzed output file
    cos_file_output = raw_id + '/' + raw_id + '-' + ifh.SEGMENT_TYPE + '.' + ifh.OUTPUT_FILE_EXT
    ifh.cos_multi_part_upload(cos_bucket, cos_file_output, output_path)
    os.remove(output_path)

    # Delete infer view design document
    clean_view = cloudant_obj['db']['_design/' + ifh.SEGMENT_TYPE + '-' + raw_id]
    clean_view.delete()

    # Save '-complete' view contents to raw_doc, add field for '-infer.h5' COS location
    raw_doc.fetch()
    raw_doc[ifh.SEGMENT_TYPE]['segments'] = segments
    raw_doc[ifh.SEGMENT_TYPE]['sw_version'] = sw_version
    raw_doc[ifh.SEGMENT_TYPE]['cos_file_output'] = cos_file_output
    raw_doc.save()

    # Deletion of input file using retention_flag
    if raw_doc['raw']['input_retention_flag'] == 'f':
        ifh.cos_delete_item(raw_doc['cos_bucket'], raw_doc['raw']['cos_path'])

    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)

    return { 'change': "{0} analyzed fully".format(doc_id) }
