from cloudant.adapters import Replay429Adapter
from cloudant.client import Cloudant
from ibm_s3transfer.aspera.manager import AsperaTransferManager
from ibm_s3transfer.aspera.manager import AsperaConfig

# https://stackoverflow.com/questions/40993553/unable-to-suppress-deprecation-warnings
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=DeprecationWarning)
    import ibm_boto3
    from ibm_botocore.client import Config, ClientError

import logging

import ibm_creds


# Constants for this Cloud Burst pipeline
OUTPUT_FILE_EXT = 'extension'  # e.g., tsv, h5, vcf
SEGMENT_TYPE = 'analysis_type'  # e.g., preprocessing, classification, etc.
DEFAULT_SEGMENT_SIZE = 864000

# Constants for IBM Cloudant
# 429 Too Many Requests
CLOUDANT_429_RETRIES = 5
CLOUDANT_INIT_BACKOFF = 0.75
# 409 Document Conflict
CLOUDANT_409_RETRIES = 10

# Constants for IBM Cloud Object Storage
COS_RESOURCE = ibm_boto3.resource('s3',
    ibm_api_key_id=ibm_creds.COS_API_KEY_ID,
    ibm_service_instance_id=ibm_creds.COS_RESOURCE_CRN,
    ibm_auth_endpoint=ibm_creds.COS_AUTH_ENDPOINT,
    config=Config(signature_version='oauth'),
    endpoint_url=ibm_creds.COS_ENDPOINT
)

COS_CLIENT = ibm_boto3.client('s3',
    ibm_api_key_id=ibm_creds.COS_API_KEY_ID,
    ibm_service_instance_id=ibm_creds.COS_RESOURCE_CRN,
    ibm_auth_endpoint=ibm_creds.COS_AUTH_ENDPOINT,
    config=Config(signature_version='oauth'),
    endpoint_url=ibm_creds.COS_ENDPOINT
)

transfer_manager = AsperaTransferManager(COS_CLIENT)

ms_transfer_config = AsperaConfig(multi_session="all",
                                  target_rate_mbps=2500,
                                  multi_session_threshold_mb=100)

# https://docs.python.org/3.6/howto/logging.html
logging.basicConfig(level=logging.WARNING, format='%(asctime)s:%(levelname)s:%(filename)s:%(lineno)s  %(message)s', datefmt='%Y-%m-%d %H:%M:%S')


def cloudant_cleanup(cloudant_obj, error=None, save=False):
    cloudant_obj['error'] = error
    if cloudant_obj['error'] is not None:
        cloudant_obj['error'] += f' ({cloudant_obj["id"]})'
        logging.error(cloudant_obj['error'])

    if save == True and cloudant_obj['doc'] is not None:
        cloudant_obj['doc'].save()

    cloudant_obj['doc'] = None
    cloudant_obj['db'] = None
    cloudant_obj['client'].disconnect()
    cloudant_obj['client'] = None

    return cloudant_obj


def cloudant_init(doc_id):
    cloudant_obj = { }
    cloudant_obj['id'] = doc_id
    cloudant_obj['error'] = None

    cloudant_obj['client'] = Cloudant.iam(ibm_creds.CLOUDANT_USERNAME, ibm_creds.CLOUDANT_API_KEY,
                                adapter=Replay429Adapter(retries=CLOUDANT_429_RETRIES, initialBackoff=CLOUDANT_INIT_BACKOFF))
    cloudant_obj['client'].connect()

    cloudant_obj['db'] = cloudant_obj['client'][ibm_creds.CLOUDANT_DATABASE]
    if cloudant_obj['db'].exists() == False:
        cloudant_obj = cloudant_cleanup(cloudant_obj, error=f'Database "{ibm_creds.CLOUDANT_DATABASE}" does not exist!')
        return cloudant_obj

    # Retrieve the Cloudant document, if specified
    if cloudant_obj['id'] is not None:
        if cloudant_obj['id'] in cloudant_obj['db']:
            cloudant_obj['doc'] = cloudant_obj['db'][cloudant_obj['id']]
        else:
            cloudant_obj = cloudant_cleanup(cloudant_obj, error=f'Document does not exist!')
            return cloudant_obj

    return cloudant_obj


# https://www.peterbe.com/plog/fastest-way-to-find-out-if-a-file-exists-in-s3
def cos_item_exists(bucket_name, item_name):
    response = COS_CLIENT.list_objects_v2(Bucket=bucket_name, Prefix=item_name)

    for item in response.get('Contents', []):
        if item['Key'] == item_name:
            return True

    return False


def cos_download_file(bucket_name, item_name, file_path):
    logging.info(f'{bucket_name}:{item_name}:{file_path}')

    try:
        COS_RESOURCE.Object(bucket_name, item_name).download_file(file_path)
    except ClientError as ce:
        logging.exception(f'ClientError occurred! ({bucket_name}:{item_name}:{file_path})', exc_info=ce)
        raise
    except Exception as e:
        logging.exception(f'Exception occurred! ({bucket_name}:{item_name}:{file_path})', exc_info=e)
        raise

    return item_name


def cos_get_item_contents(bucket_name, item_name):
    logging.info(f'{bucket_name}:{item_name}')

    try:
        item = COS_RESOURCE.Object(bucket_name, item_name).get()
        item_contents = item['Body'].read()
    except ClientError as ce:
        logging.exception(f'ClientError occurred! ({bucket_name}:{item_name})', exc_info=ce)
        raise
    except Exception as e:
        logging.exception(f'Exception occurred! ({bucket_name}:{item_name})', exc_info=e)
        raise

    return item_contents


def cos_create_text_file(bucket_name, item_name, file_text):
    logging.info(f'{bucket_name}:{item_name}')

    try:
        COS_RESOURCE.Object(bucket_name, item_name).put(Body=file_text)
    except ClientError as ce:
        logging.exception(f'ClientError occurred! ({bucket_name}:{item_name})', exc_info=ce)
        raise
    except Exception as e:
        logging.exception(f'Exception occurred! ({bucket_name}:{item_name})', exc_info=e)
        raise

    return item_name


def cos_multi_part_upload(bucket_name, item_name, file_path, overwrite=False):
    logging.info(f'{bucket_name}:{item_name}:{file_path}')

    # If not overwriting existing files and the file exists, just return
    if overwrite == False and cos_item_exists(bucket_name, item_name):
        return item_name

    # set 15 MB threshold
    threshold = 1024 * 1024 * 15
    # set 5 MB chunk size
    chunksize = 1024 * 1024 * 5

    try:
        # upload_fileobj() will execute a multi-part upload in <chunksize> MB chunks for all files over <threshold> MB
        transfer_config = ibm_boto3.s3.transfer.TransferConfig(multipart_threshold=threshold, multipart_chunksize=chunksize)
        with open(file_path, 'rb') as file_data:
            COS_RESOURCE.Object(bucket_name, item_name).upload_fileobj(Fileobj=file_data, Config=transfer_config)
    except ClientError as ce:
        logging.exception(f'ClientError occurred! ({bucket_name}:{item_name}:{file_path})', exc_info=ce)
        raise
    except Exception as e:
        logging.exception(f'Exception occurred! ({bucket_name}:{item_name}:{file_path})', exc_info=e)
        raise

    return item_name


def cos_delete_item(bucket_name, item_name):
    logging.info(f'{bucket_name}:{item_name}')

    try:
        COS_RESOURCE.Object(bucket_name, item_name).delete()
    except ClientError as ce:
        logging.exception(f'ClientError occurred! ({bucket_name}:{item_name})', exc_info=ce)
        raise
    except Exception as e:
        logging.exception(f'Exception occurred! ({bucket_name}:{item_name})', exc_info=e)
        raise

    return item_name


def aspera_file_upload(bucket_name, item_name, file_path, overwrite=False):
    logging.info(f'{bucket_name}:{item_name}:{file_path}')

    # If not overwriting existing files and the file exists, just return
    if overwrite == False and cos_item_exists(bucket_name, item_name):
        return item_name

    # Create Transfer manager
    with AsperaTransferManager(COS_CLIENT) as transfer_manager:

        # Perform upload
        future = transfer_manager.upload(file_path, bucket_name, item_name)

        # Wait for upload to complete
        future.result()

    return item_name


def aspera_file_download(bucket_name, item_name, file_path):
    # Create Transfer manager
    with AsperaTransferManager(COS_CLIENT) as transfer_manager:

        # Get object with Aspera
        future = transfer_manager.download(bucket_name, item_name, file_path)

        # Wait for download to complete
        future.result()

    return item_name
