#!/bin/bash

SCRIPT_DIR=`pwd`

IC_DEV_OR_PROD=$1
# Valid options are 'dev' and 'prod'; default is 'dev'
if [ -z "${IC_DEV_OR_PROD}" ] || ([ "${IC_DEV_OR_PROD}" != 'dev' ] && [ "${IC_DEV_OR_PROD}" != 'prod' ]); then
    IC_DEV_OR_PROD='dev'
fi

#### NOTE: Expect that each test site will start w/a single production environment, so hard-coding this to 'prod' for now
IC_DEV_OR_PROD='prod'

ARTIFACTORY_USER=''
ARTIFACTORY_PASSWORD=''


artifactory_credentials() {
    # Prompt for Artifactory username
    echo -n "Please enter your Artifactory username:  "
    read ARTIFACTORY_USER

    # Prompt for Artifactory password
    echo -n "Please enter your Artifactory password:  "
    read ARTIFACTORY_PASSWORD
}


create_fn_dir() {
    local build_fn_dir="${BUILD_DIR}/${FN_NAME}"

    if [ ! -d "${build_fn_dir}" ]; then
        mkdir ${build_fn_dir}
        cd ${build_fn_dir}

        # Create symbolic links to the dependencies specified for this Function
        for fn_file in ${FN_FILES[@]}; do
            ln -s $fn_file 
        done

        # Always include the cos_aspera and SoftLayer libraries
        ln -s "../${LIB_DIR}/cos_aspera"
        ln -s "../${LIB_DIR}/SoftLayer"

        # Functions will generally have a __main__.py script
        if [ -f "${SRC_FN_DIR}/__main__.py" ]; then
            ln -s "${SRC_FN_DIR}/__main__.py"
        fi

        # Functions will always require ibm_fn_helper.py and the ibm_creds.py file for the current environment
        ln -s '../../ibm_fn_helper.py'
        if [ $IC_DEV_OR_PROD = 'prod' ]; then
            ln -s '../../ibm_creds.py'
        else
            ln -s '../../ibm_creds.py-dev' ibm_creds.py
        fi
    fi

    cd $SCRIPT_DIR
}


BUILD_DIR='../build'
LIB_DIR="${BUILD_DIR}/lib"
ARTIFACTORY_URL="http://169.53.172.72:8081/artifactory/cardiocloud-local/lib"

# Array of dependency tarballs stored in remote Artifactory instance, should include those required for all Functions
# 'cos_aspera.tar.gz' and 'SoftLayer.tar.gz' should always be included, while others can be added as required
LIB_ARY=( 'cos_aspera.tar.gz' 'SoftLayer.tar.gz' )

# This block will prompt for the user's Artifactory credentials, the download and extract the dependency tarballs to
# the lib directory, where they can be packaged in the Function zip files for deployment
if [ ! -d "${BUILD_DIR}/lib" ]; then
    artifactory_credentials
    mkdir ${LIB_DIR}

    for LIB_FILE in ${LIB_ARY[@]}; do
        if [ ! -f ${LIB_DIR}/${LIB_FILE} ]; then
            curl -u $ARTIFACTORY_USER:$ARTIFACTORY_PASSWORD -X GET "${ARTIFACTORY_URL}/${LIB_FILE}" -o ${LIB_DIR}/${LIB_FILE}
            tar -xzf ${LIB_DIR}/${LIB_FILE} -C ${LIB_DIR}
            rm ${LIB_DIR}/${LIB_FILE}
        fi
    done
fi

FN_NAME='create_pipeline'
SRC_FN_DIR="../../python_functions/${FN_NAME}"
FN_FILES=( )
create_fn_dir

FN_NAME='destroy_pipeline'
SRC_FN_DIR="../../python_functions/${FN_NAME}"
FN_FILES=( )
create_fn_dir

FN_NAME='python_clients'
SRC_FN_DIR="../../python_clients"
FN_FILES=( )
create_fn_dir
cp -p ../python_clients/nwchem_cloud_input.py ${BUILD_DIR}/${FN_NAME}/
cp -p ../python_clients/nwchem_cloud_output.py ${BUILD_DIR}/${FN_NAME}/
