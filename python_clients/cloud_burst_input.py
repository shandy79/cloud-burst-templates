import ibm_fn_helper as ifh

import argparse
import os
import re
import requests
import sys


# Example for pipeline analyzing HDF5 files
_INPUT_FILE_EXT = r'\.h(df?)?5$'
_INPUT_FILE_DESC = 'a directory containing HDF5 files or one or more HDF5 files to be processed'

_SEGMENT_SIZE_DESC = f'an integer representing the number of data points in a segment.'
_SUFFIX_DESC = 'a string suffix to append to the file name (w/out extension) as the job ID.  The provided value will be appended following a "." character.'

_INPUT_RETENTION_FLAG_ = 'a string, DEFAULT - "t" = input file remains in database, "f" = input file will is deleted database'
_DEBUG_RETENTION_FLAG_ = 'a list of strings, flag can be used multiple times for multiple args, DEFAULT - all debug files in COS and Cloudant are deleted, "a" = all debug files will be saved in both COS and Cloudant, "r" = raw debug files are saved, "s" = segment debug files are saved'


_INPUT_JSON_TEMPLATE = {
    '_id': '',
    'cos_bucket': ifh.ibm_creds.COS_BUCKET,
    'raw': {
        'file_name': '',
        'local_path': '',
        'cos_path': '',
        'input_retention_flag' : '',
        'raw_debug_retention_flag': '',
    },
    ifh.SEGMENT_TYPE: {
        'status': 'pending',
        'segment_size': ifh.DEFAULT_SEGMENT_SIZE,
        'debug_retention_flag': ''
    }
}


def submit_input_file(input_file_path, segment_size, suffix, input_retention_flag, debug_retention_flag):
    # Building Cloudant document
    path, filename = os.path.split(input_file_path)
    doc_id, _ = os.path.splitext(filename)
    cos_path = doc_id + '/' + filename

    doc = _INPUT_JSON_TEMPLATE.copy()
    doc['_id'] = doc_id + suffix
    doc['raw']['file_name'] = filename
    doc['raw']['local_path'] = path
    doc['raw']['cos_path'] = cos_path
    doc[ifh.SEGMENT_TYPE]['segment_size'] = segment_size
    doc['raw']['input_retention_flag'] = input_retention_flag

    # Setting values of individual debug flags
    if 'a' in debug_retention_flag:
        doc['raw']['raw_debug_retention_flag'] = 't'
        doc[ifh.SEGMENT_TYPE]['debug_retention_flag'] = 't'
    else:
        if 'r' in debug_retention_flag:
            doc['raw']['raw_debug_retention_flag'] = 't'
        if 's' in debug_retention_flag:
            doc[ifh.SEGMENT_TYPE]['debug_retention_flag'] = 't'

    # Verify that this file has not been previously submitted
    if doc['_id'] in cloudant_obj['db']:
        print(f'A patient with the same file name ({doc["_id"]}) already exists in our database!')
        return

    # Upload and save the cos_path
    try:
        ifh.aspera_file_upload(doc['cos_bucket'], cos_path, input_file_path)
    except Exception as e:
        print(f'Unable to upload the file for {doc["_id"]}!\n{str(e)}')
        return

    upload_doc = cloudant_obj['db'].create_document(doc)

    if upload_doc.exists():
        head = {
            "Content-Type": "application/json",
            "X-IBM-Client-Id": ifh.ibm_creds.FN_API_KEY,
            "X-Debug-Mode": "true"
        }
        res = requests.post(ifh.ibm_creds.FN_API_ROUTE, headers=head, json={ 'id': doc['_id'] })

        if res.status_code == 200:
            print("Successfully created job for", filename)
        else:
            print(f"Something potentially went wrong ({res.status_code})!  Check Cloudant after one minute to check if segmentation began.")
    else:
        print("Cloudant did not create a job for", filename)


# Start script execution
if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('files', nargs='+', help=_INPUT_FILE_DESC, type=str)
    parser.add_argument('-z', '--segment_size', help=_SEGMENT_SIZE_DESC, type=int, default=ifh.DEFAULT_SEGMENT_SIZE)
    parser.add_argument('-s', '--suffix', help=_SUFFIX_DESC, type=str, default='')
    parser.add_argument('-r', '--input_retention_flag', help=_INPUT_RETENTION_FLAG_, type=str, default='t')
    parser.add_argument('-d', '--debug_retention_flag', action='append', help=_DEBUG_RETENTION_FLAG_, default=[])
    args = parser.parse_args()

    input_files = args.files
    segment_size = args.segment_size
    input_retention_flag = args.input_retention_flag
    debug_retention_flag = args.debug_retention_flag

    suffix = args.suffix
    if len(suffix) > 0:
        suffix = '.' + suffix

    # Connect to Cloudant
    cloudant_obj = ifh.cloudant_init(None)
    if cloudant_obj['error'] is not None:
        sys.exit(f'Cloudant error!  {cloudant_obj["error"]}')

    for input_file in input_files:
        if os.path.isdir(input_file):
            for dir_input_file in os.listdir(input_file):
                dir_input_file = os.path.join(input_file, dir_input_file)
                if os.path.isfile(dir_input_file) and re.search(_INPUT_FILE_EXT, dir_input_file, flags=re.IGNORECASE):
                    submit_input_file(dir_input_file, segment_size, suffix, input_retention_flag, debug_retention_flag)
        elif os.path.isfile(input_file):
            if re.search(_INPUT_FILE_EXT, input_file, flags=re.IGNORECASE):
                submit_input_file(input_file, segment_size, suffix, input_retention_flag, debug_retention_flag)
            else:
                print(f'Argument "{input_file}" is not a valid input file!  Ignoring.')

    # Disconnect from Cloudant
    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
