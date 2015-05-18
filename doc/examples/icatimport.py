#! /usr/bin/python
#
# Import the content of the ICAT from a file or from stdin.
#
# Use the import feature from ICAT server: make the appropriate call
# to the ICAT RESTful interface to upload content to the ICAT server.
# Try to keep the command line interface as close as possible to the
# one from icatrestore.py.
#
# Known issues and limitations:
#
#  + Depending on the version of the requests package, one may get an
#    error like:
#
#      requests.exceptions.SSLError: EOF occurred in violation of protocol
#
#    This is not yet fully understood, but it seems that some versions
#    of requests screw up the SSL parameters such that the server
#    refuses the SSL handshake.  I got the error with requests 2.7.0
#    (this is the lastest version), while requests 1.2.3 seem to work.
#

import sys
import json
import re
import logging
import requests
import icat
import icat.config
from icat.exception import translateError

logging.basicConfig(level=logging.INFO)
logging.getLogger('requests.packages.urllib3').setLevel(logging.WARNING)

config = icat.config.Config()
config.add_variable('resturl', ("--resturl",), 
                    dict(help="URL to the ICAT RESTful interface"),
                    default=True)
config.add_variable('file', ("-i", "--inputfile"), 
                    dict(help="input file name or '-' for stdin"),
                    default='-')
# The format argument makes in fact little sense, as there is no
# choice.  It's here for compatiblity with the command line interface
# of icatrestore.py only.
config.add_variable('format', ("-f", "--format"), 
                    dict(help="input file format", choices=["ICAT"]),
                    default='ICAT')
# Additional arguments that icatdump.py does not provide:
config.add_variable('duplicate', ("--duplicate",), 
                    dict(help="behavior in case of duplicate objects",
                         choices=["THROW", "IGNORE", "CHECK", "OVERWRITE"]), 
                    default='THROW')
config.add_variable('attributes', ("--attributes",), 
                    dict(help="attributes to consider in the input", 
                         choices=["ALL", "USER"]),
                    default='USER')
conf = config.getconfig()

client = icat.Client(conf.url, **conf.client_kwargs)
if client.apiversion < '4.3.99':
    raise RuntimeError("Sorry, ICAT version %s is too old, need 4.4.0 or newer."
                       % client.apiversion)
client.login(conf.auth, conf.credentials)

if conf.resturl is True:
    # As a default, derive the RESTful URL from the URL of the SOAP service.
    conf.resturl = re.sub(r'(?<=/)ICATService/.*', 'icat', conf.url)
if not conf.resturl.endswith("/"):
    conf.resturl += "/"


args = {"sessionId": client.sessionId, 
        "duplicate": conf.duplicate, 
        "attributes": conf.attributes}
if conf.file == "-":
    f = sys.stdin
else:
    f = open(conf.file, 'rb')
formfields = {
    "json": ('json', json.dumps(args), 'text/plain'),
    "data": ('data', f, 'application/octet-stream'),
}
url = conf.resturl + "port"
request = requests.post(url, data={"json":json.dumps(args)},
                        files={'file': f}, stream=True, verify=conf.checkCert)
if request.status_code != requests.codes.ok:
    try:
        raise translateError(request.json(), status=request.status_code)
    except (ValueError, TypeError):
        request.raise_for_status()
