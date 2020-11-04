import ibm_fn_helper as ifh

import numpy as np
import os


# Reconstruct the segments, as NumPy arrays, into the output file
def reassemble_segments(cos_bucket, output_path, segments):

    #### TODO: Refine this general pattern to suit your specific case

    # Reconstruct the segments into this file
    with open(output_path, 'w') as f:
        # Load from COS
        for segment in segments:
            segment_idx = int(segment['id'][1:])
            cos_file_path = segment['cos_file_output']
            filename = os.path.basename(cos_file_path)
            local_segment_path = '/tmp/' + filename

            try:
                ifh.cos_download_file(cos_bucket, cos_file_path, local_segment_path)

                # Load data from the segment file
                analyzed_segment_data = np.load(local_segment_path)

                #### TODO: Output analyzed_segment_data here
                f.write(analyzed_segment_data)

                # Delete local tmp file and COS infer file
                os.remove(local_segment_path)
                if segment_idx != 0:
                    ifh.cos_delete_item(cos_bucket, cos_file_path)

            except Exception as e:
                segment['error'] = f'Exception occurred in {segment["id"]}!\n{str(e)}'
                continue

            # Delete unnecessary keys from segment JSON
            del segment['sw_version']
            del segment['cos_file_output']
