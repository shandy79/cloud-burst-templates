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

        # Always include the cos_aspera library for improving download and upload speeds
        ln -s "../${LIB_DIR}/cos_aspera"

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
# 'cos_aspera.tar.gz' should always be included, while the remaining are examples from the Cardio Cloud project
LIB_ARY=( 'cos_aspera.tar.gz' 'biosppy.tar.gz' 'h5py.tar.gz' 'matplotlib.tar.gz' 'numexpr.tar.gz' 'tables.tar.gz' )

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

FN_NAME='create_segments'
SRC_FN_DIR="../../python_functions/${FN_NAME}"
FN_FILES=( "${SRC_FN_DIR}/create_segments.py" "../${LIB_DIR}/h5py" "../${LIB_DIR}/tables" "../${LIB_DIR}/numexpr" )
create_fn_dir

FN_NAME='analyze_segments'
SRC_FN_DIR="../../python_functions/${FN_NAME}"
FN_FILES=( "${SRC_FN_DIR}/analyze_segments.py" "../${LIB_DIR}/biosppy" "../${LIB_DIR}/matplotlib" "../${LIB_DIR}/pyparsing.py" "../${LIB_DIR}/kiwisolver.cpython-36m-x86_64-linux-gnu.so" )
# - OR -
#FN_FILES=( "${SRC_FN_DIR}/analysis-function" )
create_fn_dir

FN_NAME='reassemble_segments'
SRC_FN_DIR="../../python_functions/${FN_NAME}"
FN_FILES=( "${SRC_FN_DIR}/reassemble_segments.py" "../${LIB_DIR}/h5py" )
create_fn_dir

FN_NAME='python_clients'
SRC_FN_DIR="../../python_clients"
FN_FILES=( )
create_fn_dir
cp -p ../python_clients/cloud_burst_input.py ${BUILD_DIR}/${FN_NAME}/
cp -p ../python_clients/cloud_burst_output.py ${BUILD_DIR}/${FN_NAME}/

# Add standard test data files here if desired
# Ex. of mechanism where files already present in COS will not be re-uploaded, saving time for testing
touch ${BUILD_DIR}/${FN_NAME}/<your_input_data_file>
# Ex. of using symbolic link to reference files elsewhere on your file system
ln -s /<path_to_test_file>/<your_input_data_file> ${BUILD_DIR}/${FN_NAME}/<your_input_data_file>
