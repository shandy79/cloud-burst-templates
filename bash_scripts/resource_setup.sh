#!/bin/bash

#### resource_setup.sh
#    This script contains the commands used to establish the production Function namespace and Cloudant binding for
#    your Cloud Burst environment.  DO NOT run this script, as the resources have already been created.  Prerequisites
#    for these commands including having the following resources defined:
#    - Cloud Foundry:  your organization w/space dev-east in the us-east region
#    - Cloudant (production):  service Cloudant-<your_org>-01 w/service credential ServiceCredentials-<your_org>-Cloudant

IC_CLOUD_FOUNDRY_ORG='<your_cloud_foundry_org>'

IC_NAMESPACE='<your_org>Namespace'
IC_CLOUDANT='<your_org>Cloudant'
IC_CLOUDANT_INSTANCE='Cloudant-<your_org>-01'
IC_CLOUDANT_SVC_CRED='ServiceCredentials-<your_org>-Cloudant'

# Ensure account is pointed to proper resources for our test environment
ibmcloud target -g Default -r us-east
ibmcloud target --cf-api https://api.us-east.bluemix.net -o $IC_CLOUD_FOUNDRY_ORG -s dev-east

#### Production Resources

# Create Functions namespace
# https://cloud.ibm.com/docs/openwhisk?topic=cloud-functions-namespaces
ibmcloud fn namespace create $IC_NAMESPACE --description "For Cloudant, COS, Functions prototyping"
ibmcloud fn property set --namespace $IC_NAMESPACE

# Bind Cloudant functions to package name
# https://cloud.ibm.com/docs/openwhisk?topic=cloud-functions-pkg_cloudant
ibmcloud fn package bind /whisk.system/cloudant $IC_CLOUDANT
# Bind Cloudant service to the package using the Cloudant service credentials
ibmcloud fn service bind cloudantnosqldb $IC_CLOUDANT --instance $IC_CLOUDANT_INSTANCE --keyname $IC_CLOUDANT_SVC_CRED
