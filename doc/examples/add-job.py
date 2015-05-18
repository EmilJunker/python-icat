#! /usr/bin/python
#
# Create a job along with the input and output datacollection.
#
# The Datasets and Datafiles in the input datacollection are assumed
# to already exist.  The output Datasets and Datafiles will be created
# by this script.  This script must be run by an ICAT user having
# appropriate permissions.
#

from __future__ import print_function
import sys
import logging
import yaml
import icat
import icat.config
from icat.query import Query

logging.basicConfig(level=logging.INFO)
#logging.getLogger('suds.client').setLevel(logging.DEBUG)

config = icat.config.Config()
config.add_variable('datafile', ("datafile",), 
                    dict(metavar="inputdata.yaml", 
                         help="name of the input datafile"))
config.add_variable('jobname', ("jobname",), 
                    dict(help="name of the job to add"))
conf = config.getconfig()

client = icat.Client(conf.url, **conf.client_kwargs)
if client.apiversion < '4.3':
    raise RuntimeError("Sorry, ICAT version %s is too old, need 4.3.0 or newer."
                       % client.apiversion)
client.login(conf.auth, conf.credentials)


# ------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------

def initobj(obj, attrs):
    """Initialize an entity object from a dict of attributes."""
    for a in obj.InstAttr:
        if a != 'id' and a in attrs:
            setattr(obj, a, attrs[a])

# ------------------------------------------------------------
# Read input data
# ------------------------------------------------------------

if conf.datafile == "-":
    f = sys.stdin
else:
    f = open(conf.datafile, 'r')
data = yaml.load(f)
f.close()

try:
    jobdata = data['jobs'][conf.jobname]
except KeyError:
    raise RuntimeError("unknown job '%s'" % conf.jobname)


# Note: to simplify things, we assume that there is only one facility.
# E.g. we assume that Investigations and DatasetTypes are unique by
# their respective names and that DatafileFormats and Applications are
# unique by name and version.


# ------------------------------------------------------------
# Create the input data collection
# ------------------------------------------------------------

inputcollection = client.new("dataCollection")

for ds in jobdata['input']['datasets']:
    query = Query(client, "Dataset", conditions={
        "name":"= '%s'" % ds['name'], 
        "investigation.name":"= '%s'" % ds['investigation']
    })
    dataset = client.assertedSearch(query)[0]
    dcs = client.new("dataCollectionDataset", dataset=dataset)
    inputcollection.dataCollectionDatasets.append(dcs)

for df in jobdata['input']['datafiles']:
    query = Query(client, "Datafile", conditions={
        "name":"= '%s'" % df['name'], 
        "dataset.name":"= '%s'" % df['dataset'], 
        "dataset.investigation.name":"= '%s'" % df['investigation']
    })
    datafile = client.assertedSearch(query)[0]
    dcf = client.new("dataCollectionDatafile", datafile=datafile)
    inputcollection.dataCollectionDatafiles.append(dcf)

inputcollection.create()


# ------------------------------------------------------------
# Create the output data collection
# ------------------------------------------------------------

outputcollection = client.new("dataCollection")

for ds in jobdata['output']['datasets']:
    query = Query(client, "Investigation", conditions={
        "name":"= '%s'" % ds['investigation']
    })
    investigation = client.assertedSearch(query)[0]
    query = Query(client, "DatasetType", conditions={
        "name":"= '%s'" % data['dataset_types'][ds['type']]['name']
    })
    dataset_type = client.assertedSearch(query)[0]
    print("Dataset: creating '%s' ..." % ds['name'])
    dataset = client.new("dataset")
    initobj(dataset, ds)
    dataset.investigation = investigation
    dataset.type = dataset_type

    for df in ds['datafiles']:
        dff = data['datafile_formats'][df['format']]
        query = Query(client, "DatafileFormat", conditions={
            "name":"= '%s'" % dff['name'], 
            "version":"= '%s'" % dff['version'], 
        })
        datafile_format = client.assertedSearch(query)[0]
        print("Datafile: creating '%s' ..." % df['name'])
        datafile = client.new("datafile")
        initobj(datafile, df)
        datafile.datafileFormat = datafile_format
        dataset.datafiles.append(datafile)

    # Need to override the complete flag from the example data as we
    # do not have create permissions on complete datasets.
    dataset.complete = False
    dataset.create()
    if ds['complete']:
        del dataset.datafiles
        dataset.complete = True
        dataset.update()
    dcs = client.new("dataCollectionDataset", dataset=dataset)
    outputcollection.dataCollectionDatasets.append(dcs)

for df in jobdata['output']['datafiles']:
    query = Query(client, "Dataset", conditions={
        "name":"= '%s'" % df['dataset'], 
        "investigation.name":"= '%s'" % df['investigation']
    })
    dataset = client.assertedSearch(query)[0]
    dff = data['datafile_formats'][df['format']]
    query = Query(client, "DatafileFormat", conditions={
        "name":"= '%s'" % dff['name'], 
        "version":"= '%s'" % dff['version'], 
    })
    datafile_format = client.assertedSearch(query)[0]
    print("Datafile: creating '%s' ..." % df['name'])
    datafile = client.new("datafile")
    initobj(datafile, df)
    datafile.dataset = dataset
    datafile.datafileFormat = datafile_format
    datafile.create()
    dcf = client.new("dataCollectionDatafile", datafile=datafile)
    outputcollection.dataCollectionDatafiles.append(dcf)

outputcollection.create()


# ------------------------------------------------------------
# Create the job
# ------------------------------------------------------------

appdata = data['applications'][jobdata['application']]
appsearch = ("Application [name='%s' AND version='%s']" 
             % ( appdata['name'], appdata['version'] ))
application = client.assertedSearch(appsearch)[0]

job = client.new("job", 
                 application=application, 
                 inputDataCollection=inputcollection, 
                 outputDataCollection=outputcollection)
job.create()
