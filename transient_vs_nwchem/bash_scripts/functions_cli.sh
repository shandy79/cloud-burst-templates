#!/bin/bash

#### functions_cli.sh
#    This script contains the commands used to create or update the production and development Function triggers,
#    actions, and rules for the steps that comprise the Cloud Burst pipeline.  By default, the script will update
#    the development Functions.  Prerequisites for these commands including having the following resources defined:
#    - All IBM Cloud resources either created by or outlined as prerequisites in resource_setup.sh
#    - Functions:  API defined w/API Key, w/POST operation having Path /segment targeting Action createSegments
#    - ../build directory containing a specific structure amenable to the construction of the *.zip files containing
#      the Function code and dependencies, automatically created by env_setup.sh

SCRIPT_DIR=`pwd`

IC_DEV_OR_PROD=$1
# Valid options are 'dev' and 'prod'; default is 'dev'
if [ -z "${IC_DEV_OR_PROD}" ] || ([ "${IC_DEV_OR_PROD}" != 'dev' ] && [ "${IC_DEV_OR_PROD}" != 'prod' ]); then
    IC_DEV_OR_PROD='dev'
fi

#### NOTE: Expect that each test site will start w/a single production environment, so hard-coding this to 'prod' for now
IC_DEV_OR_PROD='prod'

IC_CREATE_OR_UPDATE=$2
# Valid options are 'create' and 'update', default is 'update'
if [ -z "${IC_CREATE_OR_UPDATE}" ] || ([ "${IC_CREATE_OR_UPDATE}" != 'create' ] && [ "${IC_CREATE_OR_UPDATE}" != 'update' ]); then
    IC_CREATE_OR_UPDATE='update'
fi

IC_CLOUD_FOUNDRY_ORG='<your_cloud_foundry_org>'

IC_NAMESPACE='<your_org>Namespace'
IC_CLOUDANT='<your_org>Cloudant'
IC_CLOUDANT_DB='<cloudant_db_instance_name>'

if [ "${IC_DEV_OR_PROD}" = 'prod' ]; then
    IC_NAMESPACE='<your_org>Namespace'
    IC_CLOUDANT='<your_org>Cloudant'
    IC_CLOUDANT_DB='<cloudant_db_instance_name>'
fi

IC_FEED=''
if [ "${IC_CREATE_OR_UPDATE}" = 'create' ]; then
    IC_FEED="--feed /_/$IC_CLOUDANT/changes"
fi

# Ensure account is pointed to proper resources for our test environment
ibmcloud target -g Default -r us-east
ibmcloud target --cf-api https://api.us-east.bluemix.net -o $IC_CLOUD_FOUNDRY_ORG -s dev-east
ibmcloud fn property set --namespace $IC_NAMESPACE

cd ../build/

# Step 1:  Create VSI from image, trigger NWChem based on input document
cd create_pipeline/; zip -r ../create_pipeline.zip *; cd ../
ibmcloud fn trigger $IC_CREATE_OR_UPDATE createPipelineTrigger $IC_FEED --param dbname $IC_CLOUDANT_DB --param filter nwchemcloud_filters/create_pipeline
ibmcloud fn action $IC_CREATE_OR_UPDATE createPipelineChange ./create_pipeline.zip --kind python:3.6 --memory 256 --timeout 1200000
ibmcloud fn rule $IC_CREATE_OR_UPDATE createPipelineRule createPipelineTrigger createPipelineChange

# Step 2:  When NWChem executions complete, update Cloudant, clean up, terminate VSI
cd destroy_pipeline/; zip -r ../destroy_pipeline.zip *; cd ../
ibmcloud fn trigger $IC_CREATE_OR_UPDATE destroyPipelineTrigger $IC_FEED --param dbname $IC_CLOUDANT_DB --param filter nwchemcloud_filters/destroy_pipeline
ibmcloud fn action $IC_CREATE_OR_UPDATE destroyPipelineChange ./destroy_pipeline.zip --kind python:3.6 --memory 256 --timeout 960000
ibmcloud fn rule $IC_CREATE_OR_UPDATE destroyPipelineRule destroyPipelineTrigger destroyPipelineChange

cd $SCRIPT_DIR

# Used to monitor output from executing triggers and functions
#ibmcloud fn activation poll
#ibmcloud fn activation get <activation_ID>
