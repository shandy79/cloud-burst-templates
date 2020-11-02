import ibm_fn_helper as ifh
from create_segments import create_segments

from cloudant.design_document import DesignDocument
from ibm_botocore.exceptions import ClientError
import os


def main(data):
    doc_id = data['id']

    cloudant_obj = ifh.cloudant_init(doc_id)
    if cloudant_obj['error'] is not None:
        return { 'error': cloudant_obj['error'] }

    # Validate JSON document for COS information
    if 'cos_bucket' not in cloudant_obj['doc'] or 'raw' not in cloudant_obj['doc'] or 'cos_path' not in cloudant_obj['doc']['raw']:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'"cos_bucket" and/or "raw[cos_path]" not in document!')
        return { 'error': cloudant_obj['error'] }

    # Verify that segmentation needs to be completed
    if ifh.SEGMENT_TYPE in cloudant_obj['doc'] and 'status' in cloudant_obj['doc'][ifh.SEGMENT_TYPE] and cloudant_obj['doc'][ifh.SEGMENT_TYPE]['status'] != 'pending':
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
        return { 'continue': 'Segmentation already complete for {0}'.format(doc_id) }

    cos_bucket = cloudant_obj['doc']['cos_bucket']
    raw_cos_path = cloudant_obj['doc']['raw']['cos_path']

    # Download file from COS to file system
    local_file_path = '/tmp/' + raw_cos_path
    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

    try:
        ifh.cos_download_file(cos_bucket, raw_cos_path, local_file_path)
    except ClientError:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'COS file "{raw_cos_path}" does not exist!')
        return { 'error': cloudant_obj['error'] }

    # Create design document w/complete and incomplete clean views for this file's segments
    design_doc = DesignDocument(cloudant_obj['db'], document_id='_design/' + ifh.SEGMENT_TYPE + '-' + doc_id)
    design_doc.add_view(ifh.SEGMENT_TYPE + '-' + doc_id + '-incomplete', 'function(doc) { if (doc.type == "' + ifh.SEGMENT_TYPE + '" && doc.raw_id == "' + doc_id + '" && ! ("compute_end" in doc)) { emit(doc._id, doc.id); } }')
    design_doc.add_view(ifh.SEGMENT_TYPE + '-' + doc_id + '-complete', 'function(doc) { if (doc.type == "' + ifh.SEGMENT_TYPE + '" && doc.raw_id == "' + doc_id + '" && "compute_end" in doc) { emit(doc._id, { id: doc.id, segment_start: doc.segment_start, segment_end: doc.segment_end, segment_size: doc.segment_size, sw_version: doc.sw_version, compute_target: doc.compute_target, cos_file_output: doc.cos_file_output, compute_start: doc.compute_start, compute_end: doc.compute_end, error: doc.error }); } }')
    design_doc.save()

    # Invoke segmentation on local raw input file
    segment_count = create_segments(local_file_path, cloudant_obj['db'], cloudant_obj['doc'])

    # Retrieve and update the document with segment information
    cloudant_obj['doc'][ifh.SEGMENT_TYPE]['status'] = 'segmented'
    cloudant_obj['doc'][ifh.SEGMENT_TYPE]['segments'] = segment_count

    # Save the JSON document and cleanup
    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, save=True)

    message = 'Segmentation complete for {0}'.format(doc_id)
    print(message)

    return { 'change': message }
