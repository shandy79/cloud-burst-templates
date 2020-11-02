#!/bin/bash

#### account_setup_cli.sh
#    This script contains commands to install the IBM Cloud CLI with additional plugins.  The script includes
#    commands to set the resource group and region, but does not set the Cloud Foundry developer space.
#    In order to use the relevant Python libraries for IBM Cloud, please make sure your environment includes the
#    following packages, which are also included in the requirements.txt file contained in this repo:
#    - cloudant
#    - ibm-cos-sdk
#    - requests
#    For example, to set up a virtual environment using pipenv, first deactivate any current environment and then
#    use the following commands:
#    - pipenv --python /usr/bin/python3 install -r requirements.txt
#    - pipenv shell

# Install IBM Cloud CLI
# https://cloud.ibm.com/docs/cli?topic=cloud-cli-getting-started
curl -fsSL https://clis.cloud.ibm.com/install/linux | sh
# Select "*-US East" for region when prompted
ibmcloud login

# Ensure account is pointed to proper resources for our PoC environment
ibmcloud target -g Default -r us-east

# Install Cloud Functions CLI plugin
# https://cloud.ibm.com/docs/openwhisk?topic=cloud-functions-cli_install
ibmcloud plugin install cloud-functions

# OPTIONAL:  Install Cloud Object Storage CLI plugin
# https://cloud.ibm.com/docs/cloud-object-storage-cli-plugin?topic=cloud-object-storage-cli-ic-cos-cli
ibmcloud plugin install cloud-object-storage

# OPTIONAL:  Install Cloud Object Storage integration for Functions
# https://cloud.ibm.com/docs/openwhisk?topic=cloud-functions-pkg_obstorage
git clone https://github.com/ibm-functions/package-cloud-object-storage.git
cd package-cloud-object-storage/runtimes/python
ibmcloud fn deploy

# Copy from COS instance Service Credentials section
#vi ~/.bluemix/cos_credentials

# OPTIONAL:  Install IBM Cloud CLI Developer Tools
#   Includes the base CLI plus several plugins, including those for Docker and Kubernetes
curl -sL https://ibm.biz/idt-installer | bash
