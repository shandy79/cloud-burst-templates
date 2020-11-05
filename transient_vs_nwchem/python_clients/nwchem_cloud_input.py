import ibm_fn_helper as ifh

import argparse
import copy
from glob import glob
import os
import os.path
import re
import sys


INPUT_FILE_EXT = 'nw'
INPUT_FILE_DESC = f'a directory containing *.{INPUT_FILE_EXT} files to be processed'
INPUT_JSON_TEMPLATE = {
    '_id': '',
    'type': 'nwchemcloud-sm',
    'status': 'pending',
    'cpus': ifh.SL_CPUS,
    'duration': ifh.DEFAULT_JOB_DURATION,
    'cos_bucket': 'sjh15-cos-bucket-nwchemcloud',
    'inputs': [ ]
}


# "id": "molecule-0",
# "cos_file_input": "test-batch-0/molecule-0/Inputfile.nw",
def create_input(doc, input_file):
    nw_input = { }
    path, filename = os.path.split(input_file)
    nw_input['local_root'] = path

    nw_input['id'] = f'molecule-{len(doc["inputs"])}'
    nw_input['cos_file_input'] = f'{doc["_id"]}/{nw_input["id"]}/{filename}'

    try:
        ifh.cos_multi_part_upload(doc['cos_bucket'], nw_input['cos_file_input'], input_file)
    except Exception as e:
        nw_input['error'] = f'Exception occurred!\n{str(e)}'
    finally:
        doc['inputs'].append(nw_input)


# Start script execution
if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('rootdir', help=INPUT_FILE_DESC, type=str)
    parser.add_argument('-c', '--cpus', help='the number of CPUs to request for this set of inputs', type=int, default=ifh.SL_CPUS, choices=[4, 8, 16, 32])
    parser.add_argument('-d', '--duration', help='the maximum permitted duration in hours of the NWChem job', type=int, default=ifh.DEFAULT_JOB_DURATION / (60 * 60), choices=[12, 24, 48, 96])

    args = parser.parse_args()

    rootdir = args.rootdir
    print(rootdir)

    # Do recursive glob here to find all *.nw files, then for each dir do the following
    input_file_list = sorted(glob(f'{rootdir}/**/*.{INPUT_FILE_EXT}', recursive=True))
    print(f'Found {len(input_file_list)} input file(s)!')
    for i, input_file in enumerate(input_file_list):
        input_file_list[i] = os.path.dirname(input_file)

    dir_prefix = os.path.dirname(rootdir) + '/'
    dir_set = set(input_file_list)

    # Connect to Cloudant
    cloudant_obj = ifh.cloudant_init(None)
    if cloudant_obj['error'] is not None:
        sys.exit(f'Cloudant error!  {cloudant_obj["error"]}')

    for input_files in dir_set:
        doc = None
        # Create Cloudant document from template, set _id
        doc = copy.deepcopy(INPUT_JSON_TEMPLATE)

        # Remove dir_prefix and change / to _
        doc['_id'] = input_files
        doc['_id'] = re.sub(dir_prefix, '', doc['_id'], count=1)
        doc['_id'] = re.sub('/', '_', doc['_id'])

        doc['cpus'] = args.cpus
        doc['duration'] = 60 * 60 * args.duration

        # Verify that batch ID has not been previously submitted
        if doc['_id'] in cloudant_obj['db']:
            cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Invalid input!  Batch {doc["_id"]} has already been submitted.')
            sys.exit(cloudant_obj['error'])

        if os.path.isdir(input_files):
            for input_file in sorted(glob(f'{input_files}/*.{INPUT_FILE_EXT}')):
                print(f'Submitting {input_file} for job {doc["_id"]} . . .')
                create_input(doc, input_file)
        else:
            cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'Invalid input!  The "rootdir" argument should be {INPUT_FILE_DESC}.')
            sys.exit(cloudant_obj['error'])

        # Save document to Cloudant
        cloudant_obj['db'].create_document(doc)

    # Disconnect from Cloudant
    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
