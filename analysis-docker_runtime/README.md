# Analysis Function as Custom Docker Runtime Deployment

Create additional subdirectories under the `docker` directory to contain any non-Python code, ML models, libraries,
etc. that you might want to include in your custom runtime.  Also, please keep in mind that your Python code will be
added to this container automatically by the IBM Cloud Functions deployment.  That code can be found in the
`python_functions/analyze_segment-docker` directory in this template repository, but should be renamed to the plain
`python_functions/analyze_segment` directory for your actual implementation.

## Docker Build and Push to Hub

* `docker login`
* `docker pull ibmfunctions/action-python-v3.6:latest`
* `cd ./analysis-docker_runtime/docker/; docker build -t <docker_hub_user>/<docker_img>:<docker_img_tag> .`
* `docker push <docker_hub_user>/<docker_img>:<docker_img_tag>`
