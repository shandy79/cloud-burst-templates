# Small Molecule Calculations

This project is for mass submission of jobs calcuating permutations of metal atoms w/in a complex and observing how
those permutations change the energies on a reaction path.  Computation is performed using the
[NWChem](http://www.nwchem-sw.org/index.php/Main_Page) software package.  Refer to the
[official documentation](https://github.com/nwchemgit/nwchem/wiki) or to the
[CAC HowTo](https://cac.queensu.ca/wiki/index.php/HowTo:nwchem) for more information.

## General Requirements

- CentOS 7.x 64-bit
- NWChem 6.8.1 or 6.6
- Python 3.6.8
- IBM Cloudant Python Client
- IBM Cloud Object Storage Python Client
- SoftLayer Python Client
- Flask
- Redis
  - Python-Redis
  - Python-RQ 

## VSI Image Template Setup
```
yum update
yum install epel-release -y
yum install python3 redis -y
systemctl start redis
systemctl enable redis
pip3 install cloudant ibm-cos-sdk SoftLayer
mkdir /opt/software/nwchem
# Install NWChem to /opt/software/nwchem/
vi /root/.nwchemrc
mkdir .bluemix
chmod 700 .bluemix
vi /root/.bluemix/cos_credentials
pip3 install flask redis rq
mkdir /opt/nwchemcloud
vi /opt/nwchemcloud/run.sh
chmod u+x /opt/nwchemcloud/run.sh
vi /opt/nwchemcloud/ibm_fn_helper.py
vi /opt/nwchemcloud/ibm_creds.py
vi /opt/nwchemcloud/redis_worker.py
vi /etc/systemd/system/redis_worker.service
vi /opt/nwchemcloud/flask_subprocess.py
vi /etc/systemd/system/flask_subprocess.service
systemctl daemon-reload
systemctl start redis_worker
systemctl enable redis_worker
systemctl start flask_subprocess
systemctl enable flask_subprocess
```
