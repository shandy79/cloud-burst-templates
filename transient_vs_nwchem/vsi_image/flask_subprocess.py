import ibm_fn_helper as ifh

import base64
from datetime import datetime
from flask import Flask, request, Response
from glob import glob
import hashlib
import hmac
from ibm_botocore.exceptions import ClientError
import logging
import os
from redis_worker import conn
from rq import Queue
import shutil
import subprocess
import sys

# https://blog.miguelgrinberg.com/post/running-a-flask-application-as-a-service-with-systemd
# https://realpython.com/flask-by-example-implementing-a-redis-task-queue/
# https://github.com/realpython/flask-by-example/blob/part4/app.py
app = Flask(__name__)
q = Queue(connection=conn)

SUBPROCESS_CMD_LIST = ['./run.sh']
SUBPROC_ROOT_DIR = '/tmp/'

cloudant_doc_id = ''


def upload_outputs(cos_bucket, nw_input, local_input_path, local_output_path, local_run_path):
    # Clean up local input file
    if os.path.exists(local_input_path):
        os.remove(local_input_path)

    # Upload result.out file to COS
    if os.path.exists(local_output_path):
        ifh.cos_multi_part_upload(cos_bucket, nw_input['cos_file_output'], local_output_path)
        os.remove(local_output_path)

    # Loop over all other output files, upload to COS, add to Cloudant, remove from local
    for result_file in sorted(glob(f'{local_run_path}/molecule.*')):
        cos_file = result_file[len(SUBPROC_ROOT_DIR):]
        nw_input['cos_results'].append(cos_file)
        ifh.cos_multi_part_upload(cos_bucket, cos_file, result_file)
        os.remove(result_file)


def run_subprocess(data):
    doc_id = data['id']

    cloudant_obj = ifh.cloudant_init(doc_id)
    if cloudant_obj['error'] is not None:
        return { 'error': cloudant_obj['error'] }

    # Validate JSON document for COS information
    if 'cos_bucket' not in cloudant_obj['doc']:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'"cos_bucket" not in document!')
        return { 'error': cloudant_obj['error'] }

    cos_bucket = cloudant_obj['doc']['cos_bucket']

    job_duration = ifh.DEFAULT_JOB_DURATION
    if 'duration' in cloudant_obj['doc']:
        job_duration = cloudant_obj['doc']['duration']

    for nw_input in cloudant_obj['doc']['inputs']:
        # Validate input fields
        if 'id' not in nw_input or 'cos_file_input' not in nw_input:
            nw_input['error'] = 'Missing required fields!'
            cloudant_obj['doc'].save()
            continue

        # Download file from COS to file system
        local_input_path = SUBPROC_ROOT_DIR + nw_input['cos_file_input']

        local_run_path = os.path.dirname(local_input_path)
        os.makedirs(local_run_path, exist_ok=True)

        # Rename user's input file to name expected by run.sh
        local_input_path = local_run_path + '/Inputfile.nw'

        try:
            ifh.cos_download_file(cos_bucket, nw_input['cos_file_input'], local_input_path)
        except ClientError:
            nw_input['error'] = 'COS file not found!'
            cloudant_obj['doc'].save()
            continue

        nw_input['cos_file_output'] = f'{local_run_path[len(SUBPROC_ROOT_DIR):]}/results.out'
        nw_input['cos_results'] = list()

        # Copy run.sh to local_run_path
        shutil.copyfile('/opt/nwchemcloud/run.sh', f'{local_run_path}/run.sh')
        shutil.copystat('/opt/nwchemcloud/run.sh', f'{local_run_path}/run.sh')

        now = datetime.now()
        nw_input['compute_start'] = str(now)

        try:
            # Save cos_file_output and compute_start prior to subprocess execution for debugging
            cloudant_obj['doc'].save()

            local_output_path = f'{SUBPROC_ROOT_DIR}{nw_input["cos_file_output"]}'

            # https://docs.python.org/3.6/library/subprocess.html
            exec_output = subprocess.run(args=SUBPROCESS_CMD_LIST, cwd=local_run_path, timeout=job_duration, check=True)  #, stdout=subprocess.PIPE, encoding='utf-8')
            #cmd_output = exec_output.stdout

            #os.makedirs(os.path.dirname(local_output_path), exist_ok=True)
            #with open(local_output_path, 'w') as f:
            #    f.write(cmd_output)

            now = datetime.now()
            nw_input['compute_end'] = str(now)

            # Upload all result files to COS, clean up all local files
            upload_outputs(cos_bucket, nw_input, local_input_path, local_output_path, local_run_path)

            # Save intermediate updates to Cloudant
            cloudant_obj['doc'].save()

        except Exception as e:
            # Try to save result files
            upload_outputs(cos_bucket, nw_input, local_input_path, local_output_path, local_run_path)

            nw_input['error'] = f'Exception occurred!\n{str(e)}'
            cloudant_obj['doc'].save()
            continue

    # Update JSON document in Cloudant
    cloudant_obj['doc']['status'] = 'complete'
    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, save=True)

    message = f'NWChem complete (CP:{doc_id})'
    print(message)

    return { 'change': message }


@app.route('/', methods=['POST'])
def index():
    global cloudant_doc_id

    data = request.get_json()

    job = q.enqueue_call(func='flask_subprocess.run_subprocess', args=(data,), result_ttl=3600, timeout=ifh.DEFAULT_QUEUE_DURATION)
    print(job.get_id())

    cloudant_doc_id = data['id']

    return Response('{ "result": "Job ' + job.get_id() + ' queued for ' + data['id'] + '" }', status=200, mimetype='application/json')


@app.route('/mgnwcsm-reclaim-scheduled', methods=['POST'])
def reclaim_scheduled():
    global cloudant_doc_id

    data = request.get_json()
    headers = request.headers

    # Validate reclaim-scheduled request
    match_flag = False

    # Simplified version that only tests for presence of expected headers and request fields
    if ('Content-Type' in headers and headers['Content-Type'] == 'application/json' and 'X-IBM-Nonce' in headers and 'Authorization' in headers and
            'id' in data and 'serviceName' in data and 'event' in data and 'timestamp' in data and 'link' in data):
        match_flag = True

    if match_flag == False:
        return Response('{ "error": "Validation check failure for reclaim-scheduled!" }', status=500, mimetype='application/json')

    # Find running input, upload results.out, and update JSON document
    cloudant_obj = ifh.cloudant_init(cloudant_doc_id)
    if cloudant_obj['error'] is not None:
        return Response('{ "error": "' + cloudant_obj['error'] + '" }', status=500, mimetype='application/json')

    # Validate JSON document for COS information
    if 'cos_bucket' not in cloudant_obj['doc'] or 'status' not in cloudant_obj['doc']:
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, error=f'"cos_bucket" and/or "status" not in document!')
        return Response('{ "error": "' + cloudant_obj['error'] + '" }', status=500, mimetype='application/json')

    cos_bucket = cloudant_obj['doc']['cos_bucket']

    # If marked complete, ignore, since this reclaim was triggered by the destroyPipeline Function
    if cloudant_obj['doc']['status'] == 'complete':
        cloudant_obj = ifh.cloudant_cleanup(cloudant_obj)
        return Response('{ "result": "' + cloudant_doc_id + ' COMPLETE and prepped for VSI reclamation!" }', status=200, mimetype='application/json')

    # https://cloud.ibm.com/docs/vsi?topic=virtual-servers-configuring-notifications-for-reclaims-of-transient-virtual-servers
    ''' The following code compiles, but does not return a match as expected
    canonical = 'POST' + headers['Content-Type'] + str(data['id']) + str(data['serviceName']) + str(data['event']) + str(data['timestamp']) + headers['X-IBM-Nonce']

    try:
        hd = hmac.new(b'{cloudant_obj["doc"]["compute_webhook"]}', b'{canonical}', hashlib.sha256).hexdigest()
        signature = base64.b64encode(hd.encode('utf-8'))
        match_flag = hmac.compare_digest(headers['Authorization'].encode('utf-8'), signature)
    except Exception as e:
        print("DOC_ID=" + cloudant_doc_id, file=sys.stderr)
        print("WEBHOOK=" + cloudant_obj['doc']['compute_webhook'], file=sys.stderr)
        print("CANONICAL=" + canonical, file=sys.stderr)
        print(str(e), file=sys.stderr)
    '''

    for nw_input in cloudant_obj['doc']['inputs']:
        if 'compute_end' not in nw_input and 'compute_start' in nw_input:
            local_input_path = SUBPROC_ROOT_DIR + nw_input['cos_file_input']
            local_run_path = os.path.dirname(local_input_path)
            local_input_path = local_run_path + '/Inputfile.nw'
            local_output_path = f'{SUBPROC_ROOT_DIR}{nw_input["cos_file_output"]}'

            nw_input['error'] = 'VSI reclaimed during execution!'

            # Upload results to COS
            upload_outputs(cos_bucket, nw_input, local_input_path, local_output_path, local_run_path)

            now = datetime.now()
            nw_input['compute_end'] = str(now)

            break

    cloudant_obj['doc']['status'] = 'reclaimed'
    cloudant_obj = ifh.cloudant_cleanup(cloudant_obj, save=True)

    return Response('{ "result": "' + cloudant_doc_id + ' INCOMPLETE and prepped for VSI reclamation!" }', status=200, mimetype='application/json')


if __name__ == '__main__':
    app.run(host='0.0.0.0')  # run app on public IP on default port 5000


# https://gist.github.com/subfuzion/08c5d85437d5d4f00e58
# curl -X POST -H "Content-Type: application/json" -d '{ "cmd": "ls -la" }' http://169.53.172.66:5000/

# https://www.digitalocean.com/community/tutorials/how-to-install-secure-redis-centos-7
