#! /usr/bin/python
"""Provide some examples on how to use the query module.
"""

from __future__ import print_function
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
conf = config.getconfig()

client = icat.Client(conf.url, **conf.client_kwargs)
client.login(conf.auth, conf.credentials)


# ------------------------------------------------------------
# Read input data
# ------------------------------------------------------------

if conf.datafile == "-":
    f = sys.stdin
else:
    f = open(conf.datafile, 'r')
data = yaml.load(f)
f.close()


# ------------------------------------------------------------
# Query examples
# ------------------------------------------------------------

# To simplify things, we take search values from the example data job.
inp = data['jobs']['job1']['input']

print("\nA simple query for an investigation by name.")
name = inp['datasets'][0]['investigation']
q = Query(client, "Investigation", conditions={"name":"= '%s'" % name})
print(str(q))
res = client.search(str(q))
print("%d result(s)" % len(res))
# keep the investigation id for a later example
if res > 0:
    invid = res[0].id
else:
    # No result, use a bogus id instead
    invid = 4711

print("\nQuery a datafile by its name, dataset name, and investigation name:")
df = inp['datafiles'][0]
conditions = { 
    "name":"= '%s'" % df['name'],
    "dataset.name":"= '%s'" % df['dataset'],
    "dataset.investigation.name":"= '%s'" % df['investigation'],
}
q = Query(client, "Datafile", conditions=conditions)
print(str(q))
print("%d result(s)" % len(client.search(str(q))))

print("\nSame example, but use placeholders in the query string now:")
df = inp['datafiles'][0]
conditions = { 
    "name":"= '%(name)s'",
    "dataset.name":"= '%(dataset)s'",
    "dataset.investigation.name":"= '%(investigation)s'",
}
q = Query(client, "Datafile", conditions=conditions)
print(str(q))
print(str(q) % df)
print("%d result(s)" % len(client.search(str(q) % df)))

print("\nQuery lots of information about one single investigation.")
includes = { "facility", "type.facility", "investigationInstruments", 
             "investigationInstruments.instrument.facility", "shifts", 
             "keywords", "publications", "investigationUsers", 
             "investigationUsers.user", "investigationGroups", 
             "investigationGroups.grouping", "parameters", 
             "parameters.type.facility" }
q = Query(client, "Investigation", 
          conditions={"id":"= %d" % invid}, includes=includes)
print(str(q))
print("%d result(s)" % len(client.search(str(q))))

print("\nQuery the instruments related to a given investigation.")
q = Query(client, "Instrument", 
          order=["name"], 
          conditions={ "investigationInstruments.investigation.id":
                       "= %d" % invid }, 
          includes={"facility", "instrumentScientists.user"})
print(str(q))
print("%d result(s)" % len(client.search(str(q))))

print("\nThe datafiles related to a given investigation in natural order.")
q = Query(client, "Datafile", order=True, 
          conditions={ "dataset.investigation.id":"= %d" % invid }, 
          includes={"dataset", "datafileFormat.facility", 
                    "parameters.type.facility"})
print(str(q))
print("%d result(s)" % len(client.search(str(q))))

print("\nRelatedDatafile is the entity type with the most complicated "
      "natural order.")
q = Query(client, "RelatedDatafile", order=True)
print(str(q))
print("%d result(s)" % len(client.search(str(q))))

print("\nThere is no sensible order for DataCollection, fall back to id.")
q = Query(client, "DataCollection", order=True)
print(str(q))
print("%d result(s)" % len(client.search(str(q))))

print("\nDatafiles ordered by format.")
q = Query(client, "Datafile", order=['datafileFormat', 'dataset', 'name'])
print(str(q))
print("%d result(s)" % len(client.search(str(q))))