"""Test the icat.query module.
"""

from __future__ import print_function
import pytest
import icat
import icat.config
from icat.query import Query
from conftest import gettestdata, callscript

dumpfile = gettestdata("icatdump.yaml")


def test_init(icatconfigfile):
    """Set up well defined content at the ICAT server.
    """
    callscript("wipeicat.py", ["-c", icatconfigfile, "-s", "root"])
    args = ["-c", icatconfigfile, "-s", "root", "-f", "YAML", "-i", dumpfile]
    callscript("icatrestore.py", args)


def test_queries(icatconfigfile, recwarn):
    """Test some queries.
    """
    # Note: the number of objects returned in the queries and their
    # attributes obviously depend on the content of the ICAT and need
    # to be kept in sync with the reference input setup above.

    args = ["-c", icatconfigfile, "-s", "root"]
    conf = icat.config.Config().getconfig(args)
    client = icat.Client(conf.url, **conf.client_kwargs)
    client.login(conf.auth, conf.credentials)

    # A simple query for an investigation by name.
    name = "10100601-ST"
    query = Query(client, "Investigation", conditions={"name":"= '%s'" % name})
    print(str(query))
    res = client.search(query)
    assert len(res) == 1
    investigation = res[0]
    assert investigation.BeanName == "Investigation"
    assert investigation.name == name

    # Query a datafile by its name, dataset name, and investigation name.
    dfdata = { 
        'name': "e208945.nxs", 
        'dataset': "e208945", 
        'investigation': "12100409-ST" 
    }
    conditions = { 
        "name": "= '%s'" % dfdata['name'],
        "dataset.name": "= '%s'" % dfdata['dataset'],
        "dataset.investigation.name": "= '%s'" % dfdata['investigation'],
    }
    query = Query(client, "Datafile", conditions=conditions)
    print(str(query))
    qstr = str(query)
    res = client.search(query)
    assert len(res) == 1
    df = res[0]
    assert df.BeanName == "Datafile"
    assert df.name == dfdata['name']

    # Same example, but use placeholders in the query string now.
    conditions = { 
        "name": "= '%(name)s'",
        "dataset.name": "= '%(dataset)s'",
        "dataset.investigation.name": "= '%(investigation)s'",
    }
    query = Query(client, "Datafile", conditions=conditions)
    print(str(query))
    print(str(query) % dfdata)
    assert str(query) % dfdata == qstr
    res = client.search(str(query) % dfdata)
    assert len(res) == 1
    df = res[0]
    assert df.BeanName == "Datafile"
    assert df.name == dfdata['name']

    # Query lots of information about one single investigation.
    includes = { "facility", "type.facility", "investigationInstruments", 
                 "investigationInstruments.instrument.facility", "shifts", 
                 "keywords", "publications", "investigationUsers", 
                 "investigationUsers.user", "investigationGroups", 
                 "investigationGroups.grouping", "parameters", 
                 "parameters.type.facility" }
    query = Query(client, "Investigation", 
                  conditions={"id": "= %d" % investigation.id}, 
                  includes=includes)
    print(str(query))
    res = client.search(query)
    assert len(res) == 1
    inv = res[0]
    assert inv.BeanName == "Investigation"
    assert inv.id == investigation.id
    assert inv.name == investigation.name
    assert inv.facility.BeanName == "Facility"
    assert inv.type.facility.BeanName == "Facility"
    assert len(inv.investigationInstruments) > 0
    assert len(inv.investigationUsers) > 0
    assert len(inv.investigationGroups) > 0

    # Query the instruments related to a given investigation.
    query = Query(client, "Instrument", 
                  order=["name"], 
                  conditions={ "investigationInstruments.investigation.id":
                               "= %d" % investigation.id }, 
                  includes={"facility", "instrumentScientists.user"})
    print(str(query))
    res = client.search(query)
    assert len(res) == 1
    instr = res[0]
    assert instr.BeanName == "Instrument"
    assert instr.facility.BeanName == "Facility"

    # The datafiles related to a given investigation in natural order.
    query = Query(client, "Datafile", order=True, 
                  conditions={ "dataset.investigation.id":
                               "= %d" % investigation.id }, 
                  includes={"dataset", "datafileFormat.facility", 
                            "parameters.type.facility"})
    print(str(query))
    res = client.search(query)
    assert len(res) == 4
    # The 'natural' order is the same as the one generated by Entity's
    # __sortkey__.
    sdf = sorted(res, key=icat.entity.Entity.__sortkey__)
    assert res == sdf

    # Same example, but skip the investigation in the order.")
    query = Query(client, "Datafile", order=['dataset.name', 'name'], 
                  conditions={ "dataset.investigation.id":
                               "= %d" % investigation.id }, 
                  includes={"dataset", "datafileFormat.facility", 
                            "parameters.type.facility"})
    print(str(query))
    res = client.search(query)
    assert len(res) == 4
    assert res == sdf

    # RelatedDatafile is the entity type with the most complicated
    # natural order.
    query = Query(client, "RelatedDatafile", order=True)
    print(str(query))
    res = client.search(query)
    assert len(res) == 0

    # There is no sensible order for DataCollection, fall back to id.
    query = Query(client, "DataCollection", order=True)
    print(str(query))
    assert "id" in query.order
    res = client.search(query)
    assert len(res) == 0

    # Datafiles ordered by format.
    # Note: this raises a QueryNullableOrderWarning, see below.
    recwarn.clear()
    query = Query(client, "Datafile", 
                  order=['datafileFormat', 'dataset', 'name'])
    w = recwarn.pop(icat.QueryNullableOrderWarning)
    assert issubclass(w.category, icat.QueryNullableOrderWarning)
    assert "datafileFormat" in str(w.message)
    print(str(query))
    res = client.search(query)
    assert len(res) == 7

    # Other relations then equal may be used in the conditions too.
    condition = {"datafileCreateTime": ">= '2012-01-01'"}
    query = Query(client, "Datafile", conditions=condition)
    print(str(query))
    res = client.search(query)
    assert len(res) == 2
    condition = {"datafileCreateTime": "< '2012-01-01'"}
    query = Query(client, "Datafile", conditions=condition)
    print(str(query))
    res = client.search(query)
    assert len(res) == 5

    # We may also add a list of conditions on a single attribute.
    condition = {"datafileCreateTime": [">= '2012-01-01'", "< '2013-01-01'"]}
    query = Query(client, "Datafile", conditions=condition)
    print(str(query))
    qstr = str(query)
    res = client.search(query)
    assert len(res) == 1

    # The last example also works by adding the conditions separately.
    query = Query(client, "Datafile")
    query.addConditions({"datafileCreateTime": ">= '2012-01-01'"})
    query.addConditions({"datafileCreateTime": "< '2013-01-01'"})
    print(str(query))
    assert str(query) == qstr
    res = client.search(query)
    assert len(res) == 1

    # Using "id in (i)" rather then "id = i" also works.
    # (This may be needed to work around ICAT Issue 149.)
    query = Query(client, "Investigation", 
                  conditions={"id": "in (%d)" % investigation.id})
    print(str(query))
    res = client.search(query)
    assert len(res) == 1
    inv = res[0]
    assert inv.BeanName == "Investigation"
    assert inv.id == investigation.id
    assert inv.name == investigation.name

    # Rule does not have a constraint, id is included in the natural order.
    query = Query(client, "Rule", order=True)
    print(str(query))
    assert "id" in query.order
    res = client.search(query)
    assert len(res) == 101

    # Ordering on nullable relations emits a warning.
    recwarn.clear()
    query = Query(client, "Rule", order=['grouping', 'what', 'id'])
    w = recwarn.pop(icat.QueryNullableOrderWarning)
    assert issubclass(w.category, icat.QueryNullableOrderWarning)
    assert "grouping" in str(w.message)
    print(str(query))
    res = client.search(query)
    assert len(res) == 44

    # The warning can be suppressed by making the condition explicit.
    recwarn.clear()
    query = Query(client, "Rule", order=['grouping', 'what', 'id'], 
                  conditions={"grouping":"IS NOT NULL"})
    assert len(recwarn.list) == 0
    print(str(query))
    res = client.search(query)
    assert len(res) == 44

    # Add a LIMIT clause to the last example.
    query.setLimit( (0,10) )
    print(str(query))
    res = client.search(query)
    assert len(res) == 10

    # LIMIT clauses are particular useful with placeholders.
    query.setLimit( ("%d","%d") )
    print(str(query))
    print(str(query) % (0,30))
    res = client.search(str(query) % (0,30))
    assert len(res) == 30
    print(str(query) % (30,30))
    res = client.search(str(query) % (30,30))
    assert len(res) == 14
