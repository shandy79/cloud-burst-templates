#!/bin/bash

#export PATH=/opt/software/nwchem/nwchem-6.8.1/bin/LINUX64/:$PATH
#source /opt/software/nwchem/settings68.sh
export PATH=/opt/software/nwchem/nwchem-6.6/bin/LINUX64/:$PATH
source /opt/software/nwchem/settings66.sh
mpirun --allow-run-as-root -np `nproc` nwchem Inputfile.nw >& results.out
