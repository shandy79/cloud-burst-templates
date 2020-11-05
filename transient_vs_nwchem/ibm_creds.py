#### Connection details for IBM Cloudant
#    - Service:  e.g., Cloudant-<your_org>-01
#    - Service Credential:  e.g., ServiceCredentials-<your_org>-Cloudant
CLOUDANT_DATABASE = '<cloudant_db_instance_name>'
# From the Service Credential's JSON document
CLOUDANT_USERNAME = 'XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX-bluemix'
CLOUDANT_API_KEY = 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'

#### Connection details for IBM Cloud Object Storage
#    - Service:  e.g., CloudObjectStorage-<your_org>-01
#    - Service Credential:  e.g., ServiceCredentials-<your_org>-CloudObjectStorage
COS_BUCKET = '<cos_bucket_instance_name>'
COS_AUTH_ENDPOINT = 'https://iam.cloud.ibm.com/identity/token'
# Current list available at https://control.cloud-object-storage.cloud.ibm.com/v2/endpoints
# Entry below assumes the 'tor01' Location, having selected 'Single Site' resiliency
COS_ENDPOINT = 'https://s3.tor01.cloud-object-storage.appdomain.cloud'
# From the Service Credential's JSON document ('apikey' and 'resource_instance_id')
COS_API_KEY_ID = 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'
COS_RESOURCE_CRN = 'crn:v1:bluemix:public:cloud-object-storage:global:a/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX:XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX::'

#### Connection details for IBM Cloud Functions
#    - Namespace:  e.g., <your_org>Namespace-01
#    - API:  segment-api
#    - API Key:  segment-key
FN_API_ROUTE = 'https://XXXXXXXX.us-east.apiconnect.appdomain.cloud/XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/segment?blocking=false'
FN_API_KEY = 'XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX'

#### Connection details for SoftLayer
SL_API_USERNAME = '<sl_api_username>'
SL_API_KEY = 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'

SL_DOMAIN_NAME='<sl_domain_name>'
#SL_PLACEMENT_GROUP_ID = XXXXXX  # Probably need to remove, since limit on concurrent VSIs in a PG
# https://sldn.softlayer.com/python/list_images_templates.py/
# result = client['SoftLayer_Account'].getPrivateBlockDeviceTemplateGroups()
SL_IMAGE_TEMPLATE_ID = 'XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX'
