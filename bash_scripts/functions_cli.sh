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
IC_DOCKER='<docker_hub_user>/<docker_img>:<docker_img_tag>'

if [ "${IC_DEV_OR_PROD}" = 'prod' ]; then
    IC_NAMESPACE='<your_org>Namespace'
    IC_CLOUDANT='<your_org>Cloudant'
    IC_CLOUDANT_DB='<cloudant_db_instance_name>'
    IC_DOCKER='<docker_hub_user>/<docker_img>:<docker_img_tag>'
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

# Step 1:  Creates segments from the raw input file
cd create_segments/; zip -r ../create_segments.zip *; cd ../
#ibmcloud fn trigger $IC_CREATE_OR_UPDATE createSegmentsTrigger $IC_FEED --param dbname $IC_CLOUDANT_DB --param filter cloudant_filters/create_segments
ibmcloud fn action $IC_CREATE_OR_UPDATE createSegmentsChange ./create_segments.zip --kind python:3.6 --memory 1024 --timeout 960000 --web true
#ibmcloud fn rule $IC_CREATE_OR_UPDATE createSegmentsRule createSegmentsTrigger createSegmentsChange

# Step 2:  Analyze each segment using a standard Python runtime
# - OR -   Analyze each segment using a custom Docker runtime
cd analyze_segment/; zip -r ../analyze_segment.zip *; cd ../
ibmcloud fn trigger $IC_CREATE_OR_UPDATE analyzeSegmentTrigger $IC_FEED --param dbname $IC_CLOUDANT_DB --param filter cloudant_filters/analyze_segment
ibmcloud fn action $IC_CREATE_OR_UPDATE analyzeSegmentChange ./analyze_segment.zip --kind python:3.6 --memory 1024 --timeout 960000
# - OR -
#ibmcloud fn action $IC_CREATE_OR_UPDATE analyzeSegmentChange --docker $IC_DOCKER ./analyze_segment.zip --memory 4096 --timeout 960000
ibmcloud fn rule $IC_CREATE_OR_UPDATE analyzeSegmentRule analyzeSegmentTrigger analyzeSegmentChange

# Step 3:  Reassemble segments to output data file following analysis
cd reassemble_segments/; zip -r ../reassemble_segments.zip *; cd ../
ibmcloud fn trigger $IC_CREATE_OR_UPDATE reassembleSegmentsTrigger $IC_FEED --param dbname $IC_CLOUDANT_DB --param filter cloudant_filters/reassemble_segments
ibmcloud fn action $IC_CREATE_OR_UPDATE reassembleSegmentsChange ./reassemble_segments.zip --kind python:3.6 --memory 4096 --timeout 1200000
ibmcloud fn rule $IC_CREATE_OR_UPDATE reassembleSegmentsRule reassembleSegmentsTrigger reassembleSegmentsChange

cd $SCRIPT_DIR

# Used to monitor output from executing triggers and functions
#ibmcloud fn activation poll
#ibmcloud fn activation get <activation_ID>
