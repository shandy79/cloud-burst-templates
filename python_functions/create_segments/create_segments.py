import ibm_fn_helper as ifh

import numpy as np
import os


TMP_DIR = '/tmp/'


# Opens the raw input file and reads the contents.  The contents are then segmented and saved into NumPy arrays
# and saved to the 'raw/' directory in COS.
def create_segments(local_file_path, cloudant_db, cloudant_doc):

    #### TODO: Open and read data from raw input file.  Determine data size.
    local_file_data = None
    local_file_size = None

    doc_id = cloudant_doc['_id']
    cos_bucket = cloudant_doc['cos_bucket']

    segment_size = cloudant_doc[ifh.SEGMENT_TYPE]['segment_size']
    path_prefix = doc_id + '/raw/'
    os.makedirs(TMP_DIR + path_prefix, exist_ok=True)

    count = 0
    for segment_index in range(0, local_file_size, segment_size):
        # Include redundant raw_cos_bucket field to cut down on Cloudant reads in analysis step
        segment_dict = {
            '_id': doc_id + '.' + ifh.SEGMENT_TYPE + '.S' + str(count),
            'raw_id': doc_id,
            'raw_cos_bucket': cos_bucket,
            'type': ifh.SEGMENT_TYPE,
            'id': 'S' + str(count),
            'segment_start': int(segment_index),
            'segment_end': int(segment_index + segment_size),
            'segment_size': int(segment_size),
            'cos_file_raw': path_prefix + 'S' + str(count) + '.npy',
            'last_seg': 'false'
        }

        # Create empty NumPy array to hold segment data
        segment_data_ary = np.zeros((segment_size, 1), local_file_data.dtype)

        # If final segment, may have different properties, e.g., end position and size
        if (segment_index + segment_size) >= local_file_size:
            last_segment_size = local_file_size - segment_index
            segment_dict['segment_end'] = int(segment_index + last_segment_size)
            segment_dict['segment_size'] = int(last_segment_size)
            segment_data_ary = np.zeros((last_segment_size, 1), local_file_data.dtype)
            segment_dict['last_seg'] = 'true'

        try:
            #### TODO: Populate segment_data_ary data from local_file_data here!

            # Save, upload, delete segment
            tmp_file_path = TMP_DIR + segment_dict['cos_file_raw']
            np.save(tmp_file_path, segment_data_ary)
            ifh.cos_multi_part_upload(cos_bucket, segment_dict['cos_file_raw'], tmp_file_path)
            os.remove(tmp_file_path)

            # Create Cloudant document from JSON snippet
            cloudant_db.create_document(segment_dict)

        except Exception as e:
            print(f'Exception occurred in {doc_id}, segment {count}!\n{str(e)}')
        finally:
            count += 1

    #### TODO: Close the input file if necessary!

    return count
