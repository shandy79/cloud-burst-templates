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
import SoftLayer, secrets, string, time

import ibm_creds


# Constants for this Cloud Burst pipeline
SW_VERSION = 'NWChem 6.6'  # 6.8.1
FLASK_PORT = 5000
DEFAULT_JOB_DURATION = 60 * 60 * 24  # 24h
DEFAULT_QUEUE_DURATION = DEFAULT_JOB_DURATION * 8  # 8d

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

# Constants for SoftLayer
SL_MASK_VG = 'id, primaryIpAddress, primaryBackendIpAddress'
SL_FLAVOR='C1_8X8X25'  # C1_1X1X25|C1_16X16X25
SL_CPUS=8  # 1|16
SL_MEMORY=8  # 1|16
SL_BILLING='true'
SL_DATA_CENTER='tor01'
#SL_OS_CODE='CENTOS_7_64'
#SL_LOCAL_DISK='false'
#SL_DISKS=25

SECRET_CHARACTERS = string.ascii_letters + string.digits + string.punctuation
SL_WEBHOOK_SECRET = ''.join(secrets.choice(SECRET_CHARACTERS) for i in range(32))


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


# https://sldn.softlayer.com/reference/datatypes/SoftLayer_Virtual_Guest/
def sl_create_transient_vg(hostname, webhook_path=None, webhook_port=None, cpus=SL_CPUS):
    logging.info(f'{SL_FLAVOR}:{ibm_creds.SL_IMAGE_TEMPLATE_ID}:{hostname}')
    webhook_return_val = None

    mem = SL_MEMORY
    flavor = SL_FLAVOR

    if cpus != SL_CPUS:
        mem = cpus
        flavor = f'C1_{cpus}X{mem}X25'  # C1_8X8X25

    try:
        client = SoftLayer.Client(username=ibm_creds.SL_API_USERNAME, api_key=ibm_creds.SL_API_KEY)
        request = client['Virtual_Guest'].createObject({
                                                    'hostname': hostname,
                                                    'domain': ibm_creds.SL_DOMAIN_NAME,
                                                    'startCpus': cpus,
                                                    'maxMemory': mem,
                                                    #'localDiskFlag': SL_LOCAL_DISK,
                                                    'hourlyBillingFlag': SL_BILLING,
                                                    'datacenter': { 'name': SL_DATA_CENTER },
                                                    #'placementGroupId': ibm_creds.SL_PLACEMENT_GROUP_ID,
                                                    #'operatingSystemReferenceCode': SL_OS_CODE,
                                                    'supplementalCreateObjectOptions': { 'flavorKeyName': flavor },
                                                    'transientGuestFlag': 'true',
                                                    'blockDeviceTemplateGroup': { 'globalIdentifier': ibm_creds.SL_IMAGE_TEMPLATE_ID },
                                                    #'postInstallScriptUri': 'https://www.dropbox.com/s/5gzid5qqggo6ru8/ShowID.bat?dl=0'
        })

        vg_id = request['id']

        sleep_time = 30
        status = 'PENDING'
        while status != 'COMPLETE':
           time.sleep(sleep_time)
           vg = client['Virtual_Guest'].getObject(id=vg_id, mask='id, lastTransaction')
           if 'lastTransaction' in vg:
              status = vg['lastTransaction']['transactionStatus']['name']
              logging.info(f'{hostname} Transaction status: {status}')
           else:
              logging.warning(f'{hostname} No transaction status!')

        # Fetch relevant information (such as its IP address, login-username, login-password) about the VM
        vg = client['Virtual_Guest'].getObject(id=vg_id, mask=SL_MASK_VG)

        # If a web hook was requested, set it here
        if webhook_path != None:
            webhook_uri = 'http://' + vg['primaryIpAddress']
            if webhook_port != None:
                webhook_uri += ':' + str(webhook_port)
            webhook_uri += '/' + webhook_path
            client['Virtual_Guest'].setTransientWebhook(webhook_uri, SL_WEBHOOK_SECRET, id=vg_id)
            webhook_return_val = SL_WEBHOOK_SECRET

    except Exception as e:
        logging.exception(f'Exception occurred! ({hostname})', exc_info=e)
        raise
    else:
        return vg, webhook_return_val


def sl_cancel_transient_vg(vg_id):
    logging.info(f'{SL_FLAVOR}:{ibm_creds.SL_IMAGE_TEMPLATE_ID}:{vg_id}')

    try:
        client = SoftLayer.Client(username=ibm_creds.SL_API_USERNAME, api_key=ibm_creds.SL_API_KEY)
        billing_id = client['Virtual_Guest'].getBillingItem(id=vg_id, mask='mask[id]')
        cancel_item = client['SoftLayer_Billing_Item'].cancelService(id=billing_id['id'])
    except Exception as e:
        logging.exception(f'Exception occurred! ({vg_id})', exc_info=e)
        raise
    else:
        return cancel_item
