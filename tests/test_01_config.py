"""Test module icat.config
"""

import os.path
import getpass
import pytest
import icat.config
import icat.exception


# ============================= helper =============================

# The icat.config.Config constructor already creates and initializes
# an ICAT client.  Prevent this, as we don't want to connect to a real
# server in this test module.  Foist a fake client class on the
# icat.config module.  Note that we must monkeypatch icat.config
# rather then icat.client, as the former already imported the Client
# class at this point.

class Namespace(object):
    def __init__(self, **kwargs):
        for (k, v) in kwargs.items():
            setattr(self, k, v)

class FakeClient(object):
    AuthInfo = None
    def __init__(self, url, **kwargs):
        pass
    def getAuthenticatorInfo(self):
        if self.AuthInfo:
            return self.AuthInfo
        else:
            raise icat.exception.VersionMethodError("getAuthenticatorInfo")

@pytest.fixture(scope="function")
def fakeClient(monkeypatch):
    monkeypatch.setattr(icat.config, "Client", FakeClient)


# Deliberately not using the 'tmpdir' fixture provided by pytest,
# because it seem to use a predictable directory name in /tmp wich is
# insecure.

# Content of the configuration file used in the tests
configfilestr = """
[example_root]
url = https://icat.example.com/ICATService/ICAT?wsdl
auth = simple
username = root
password = secret
idsurl = https://icat.example.com/ids
ldap_uri = ldap://ldap.example.com
ldap_base = ou=People,dc=example,dc=com

[example_jdoe]
url = https://icat.example.com/ICATService/ICAT?wsdl
auth = ldap
username = jdoe
password = pass
greeting = Hello %(username)s!
num = 42
invnum = forty-two
flag1 = true
flag2 = off

[example_nbour]
url = https://icat.example.com/ICATService/ICAT?wsdl
auth = ldap
username = nbour

[example_anon]
url = https://icat.example.com/ICATService/ICAT?wsdl
auth = anon

[test21]
url = https://icat.example.com/ICATService/ICAT?wsdl
auth = simple
username = root
password = secret
promptPass = Yes
"""

class ConfigFile(object):
    def __init__(self, confdir, content):
        self.dir = confdir
        self.path = os.path.join(self.dir, "icat.cfg")
        with open(self.path, "w") as f:
            f.write(content)

@pytest.fixture(scope="module")
def tmpconfigfile(tmpdirsec):
    return ConfigFile(tmpdirsec.dir, configfilestr)

# ============================= tests ==============================

def test_config_minimal(fakeClient):
    """Minimal example.

    No login credentials, only relevant config option is the url which
    is provided as command line argument.
    """

    args = ["-w", "https://icat.example.com/ICATService/ICAT?wsdl"]
    _, conf = icat.config.Config(needlogin=False, args=args).getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'checkCert', 'configDir', 'configFile', 'configSection', 
                      'http_proxy', 'https_proxy', 'no_proxy', 'url' ]

    # Deliberately not checking configFile, configDir, http_proxy, and
    # https_proxy.  configFile contains the default location of the
    # config file which is not relevant here.  *_proxy may be set from
    # environment variables.
    assert conf.configSection is None
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"


def test_config_minimal_file(fakeClient, tmpconfigfile, monkeypatch):
    """Minimal example.

    Almost the same as test_config_minimal(), but read the url from
    a config file this time.
    """

    # Let the config file be found in the default location, but
    # manipulate the search path such that only the cwd exists.
    cfgdirs = [ os.path.join(tmpconfigfile.dir, ".icat"), ""]
    monkeypatch.setattr(icat.config, "cfgdirs", cfgdirs)
    monkeypatch.chdir(tmpconfigfile.dir)

    args = ["-s", "example_root"]
    _, conf = icat.config.Config(needlogin=False, args=args).getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'checkCert', 'configDir', 'configFile', 'configSection', 
                      'http_proxy', 'https_proxy', 'no_proxy', 'url' ]

    assert conf.configFile == ["icat.cfg"]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"


def test_config_simple_login(fakeClient, tmpconfigfile):
    """Simple login example.

    Standard usage, read everything from a config file.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_root"]
    _, conf = icat.config.Config(args=args).getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'no_proxy', 'password', 'promptPass', 
                      'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "simple"
    assert conf.username == "root"
    assert conf.password == "secret"
    assert conf.promptPass == False
    assert conf.credentials == {'username': 'root', 'password': 'secret'}


def test_config_override(fakeClient, tmpconfigfile):
    """
    Read some stuff from a config file, override some other options
    with command line arguments.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_root", 
            "-a", "db", "-u", "rbeck", "-p", "geheim"]
    _, conf = icat.config.Config(args=args).getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'no_proxy', 'password', 'promptPass', 
                      'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "db"
    assert conf.username == "rbeck"
    assert conf.password == "geheim"
    assert conf.promptPass == False
    assert conf.credentials == {'username': 'rbeck', 'password': 'geheim'}


def test_config_askpass(fakeClient, tmpconfigfile, monkeypatch):
    """
    Same as test_config_override(), but do not pass the password in
    the command line arguments.  In this case, getconfig() should
    prompt for the password.
    """

    def mockgetpass(prompt='Password: '):
        return "mockpass"
    monkeypatch.setattr(getpass, "getpass", mockgetpass)

    args = ["-c", tmpconfigfile.path, "-s", "example_root", 
            "-a", "db", "-u", "rbeck"]
    _, conf = icat.config.Config(args=args).getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'no_proxy', 'password', 'promptPass', 
                      'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "db"
    assert conf.username == "rbeck"
    assert conf.password == "mockpass"
    assert conf.promptPass == False
    assert conf.credentials == {'username': 'rbeck', 'password': 'mockpass'}


def test_config_nopass_askpass(fakeClient, tmpconfigfile, monkeypatch):
    """
    Same as test_config_askpass(), but with no password set in the
    config file.  Very early versions of icat.config had a bug to
    raise an error if no password was set at all even if interactive
    prompt for the password was explictely requested.  (Fixed in
    67e91ed.)
    """

    def mockgetpass(prompt='Password: '):
        return "mockpass"
    monkeypatch.setattr(getpass, "getpass", mockgetpass)

    args = ["-c", tmpconfigfile.path, "-s", "example_nbour", "-P"]
    _, conf = icat.config.Config(args=args).getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'no_proxy', 'password', 'promptPass', 
                      'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_nbour"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "ldap"
    assert conf.username == "nbour"
    assert conf.password == "mockpass"
    assert conf.promptPass == True
    assert conf.credentials == {'username': 'nbour', 'password': 'mockpass'}


def test_config_askpass_file(fakeClient, tmpconfigfile, monkeypatch):
    """
    Set promptPass in the configuration file.  This should force
    prompting for the password.  Issue #21.
    """

    def mockgetpass(prompt='Password: '):
        return "mockpass"
    monkeypatch.setattr(getpass, "getpass", mockgetpass)

    args = ["-c", tmpconfigfile.path, "-s", "test21"]
    _, conf = icat.config.Config(args=args).getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'no_proxy', 'password', 'promptPass', 
                      'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "test21"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "simple"
    assert conf.username == "root"
    assert conf.password == "mockpass"
    assert conf.promptPass == True
    assert conf.credentials == {'username': 'root', 'password': 'mockpass'}


def test_config_environment(fakeClient, tmpconfigfile, monkeypatch):
    """Set some config variables from the environment.
    """

    monkeypatch.setenv("ICAT_CFG", tmpconfigfile.path)
    monkeypatch.setenv("ICAT_AUTH", "db")
    monkeypatch.setenv("http_proxy", "http://www-cache.example.org:3128/")
    monkeypatch.setenv("https_proxy", "http://www-cache.example.org:3128/")
    monkeypatch.setenv("no_proxy", "localhost, .example.org")

    args = ["-s", "example_root", "-u", "rbeck", "-p", "geheim"]
    _, conf = icat.config.Config(args=args).getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'no_proxy', 'password', 'promptPass', 
                      'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.http_proxy == "http://www-cache.example.org:3128/"
    assert conf.https_proxy == "http://www-cache.example.org:3128/"
    assert conf.no_proxy == "localhost, .example.org"
    assert conf.auth == "db"
    assert conf.username == "rbeck"
    assert conf.password == "geheim"
    assert conf.promptPass == False
    assert conf.credentials == {'username': 'rbeck', 'password': 'geheim'}


def test_config_ids(fakeClient, tmpconfigfile):
    """Simple login example.

    Ask for the idsurl configuration variable.
    """

    # We set ids="optional", the idsurl is present in section example_root.
    args = ["-c", tmpconfigfile.path, "-s", "example_root"]
    _, conf = icat.config.Config(ids="optional", args=args).getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'idsurl', 'no_proxy', 'password', 
                      'promptPass', 'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.idsurl == "https://icat.example.com/ids"
    assert conf.auth == "simple"
    assert conf.username == "root"
    assert conf.password == "secret"
    assert conf.promptPass == False
    assert conf.credentials == {'username': 'root', 'password': 'secret'}

    # In section example_jdoe, idsurl is not set, so the configuration
    # variable is present, but set to None.
    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe"]
    _, conf = icat.config.Config(ids="optional", args=args).getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'idsurl', 'no_proxy', 'password', 
                      'promptPass', 'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_jdoe"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.idsurl == None
    assert conf.auth == "ldap"
    assert conf.username == "jdoe"
    assert conf.password == "pass"
    assert conf.promptPass == False
    assert conf.credentials == {'username': 'jdoe', 'password': 'pass'}


def test_config_custom_var(fakeClient, tmpconfigfile):
    """Define custom configuration variables.
    """

    # Note that ldap_filter is not defined in the configuration file,
    # but we have a default value defined here, so this is ok.
    args = ["-c", tmpconfigfile.path, "-s", "example_root"]
    config = icat.config.Config(args=args)
    config.add_variable('ldap_uri', ("-l", "--ldap-uri"), 
                        dict(help="URL of the LDAP server"),
                        envvar='LDAP_URI')
    config.add_variable('ldap_base', ("-b", "--ldap-base"), 
                        dict(help="base DN for searching the LDAP server"),
                        envvar='LDAP_BASE')
    config.add_variable('ldap_filter', ("-f", "--ldap-filter"), 
                        dict(help="search filter to select the user entries"),
                        default='(uid=*)')
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'ldap_base', 'ldap_filter', 'ldap_uri', 
                      'no_proxy', 'password', 'promptPass', 'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "simple"
    assert conf.username == "root"
    assert conf.password == "secret"
    assert conf.promptPass == False
    assert conf.ldap_uri == "ldap://ldap.example.com"
    assert conf.ldap_base == "ou=People,dc=example,dc=com"
    assert conf.ldap_filter == "(uid=*)"
    assert conf.credentials == {'username': 'root', 'password': 'secret'}


def test_config_subst_nosubst(fakeClient, tmpconfigfile):
    """Use a format string in a configuration variable.

    But disable the substitution.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe"]
    config = icat.config.Config(args=args)
    config.add_variable('greeting', ("--greeting",), 
                        dict(help="Greeting message"),
                        subst=False)
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'greeting', 
                      'http_proxy', 'https_proxy', 'no_proxy', 'password', 
                      'promptPass', 'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_jdoe"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "ldap"
    assert conf.username == "jdoe"
    assert conf.password == "pass"
    assert conf.promptPass == False
    assert conf.greeting == "Hello %(username)s!"
    assert conf.credentials == {'username': 'jdoe', 'password': 'pass'}


def test_config_subst(fakeClient, tmpconfigfile):
    """Use a format string in a configuration variable.

    Same as above, but enable the substitution this time.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe"]
    config = icat.config.Config(args=args)
    config.add_variable('greeting', ("--greeting",), 
                        dict(help="Greeting message"),
                        subst=True)
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'greeting', 
                      'http_proxy', 'https_proxy', 'no_proxy', 'password', 
                      'promptPass', 'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_jdoe"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "ldap"
    assert conf.username == "jdoe"
    assert conf.password == "pass"
    assert conf.promptPass == False
    assert conf.greeting == "Hello jdoe!"
    assert conf.credentials == {'username': 'jdoe', 'password': 'pass'}


def test_config_subst_cmdline(fakeClient, tmpconfigfile):
    """Use a format string in a configuration variable.

    Same as above, but set the referenced variable from the command
    line.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe", 
            "-u", "jonny", "-p", "pass"]
    config = icat.config.Config(args=args)
    config.add_variable('greeting', ("--greeting",), 
                        dict(help="Greeting message"),
                        subst=True)
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'greeting', 
                      'http_proxy', 'https_proxy', 'no_proxy', 'password', 
                      'promptPass', 'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_jdoe"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "ldap"
    assert conf.username == "jonny"
    assert conf.password == "pass"
    assert conf.promptPass == False
    assert conf.greeting == "Hello jonny!"
    assert conf.credentials == {'username': 'jonny', 'password': 'pass'}


def test_config_subst_confdir(fakeClient, tmpconfigfile):
    """Substitute configDir in the default of a variable.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe"]
    config = icat.config.Config(needlogin=False, args=args)
    config.add_variable('extracfg', ("--extracfg",), 
                        dict(help="Extra config file"),
                        default="%(configDir)s/extra.xml", subst=True)
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'checkCert', 'configDir', 'configFile', 'configSection', 
                      'extracfg', 'http_proxy', 'https_proxy', 'no_proxy', 
                      'url' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_jdoe"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert os.path.dirname(conf.extracfg) == tmpconfigfile.dir


def test_config_type_int(fakeClient, tmpconfigfile):
    """Read an integer variable from the configuration file.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe"]
    config = icat.config.Config(needlogin=False, args=args)
    config.add_variable('num', ("--num",), 
                        dict(help="Integer variable"), type=int)
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'checkCert', 'configDir', 'configFile', 'configSection', 
                      'http_proxy', 'https_proxy', 'no_proxy', 'num', 'url' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_jdoe"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.num == 42


def test_config_type_int_err(fakeClient, tmpconfigfile):
    """Read an integer variable from the configuration file.

    Same as last one, but have an invalid value this time.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe"]
    config = icat.config.Config(needlogin=False, args=args)
    config.add_variable('invnum', ("--invnum",), 
                        dict(help="Integer variable"), type=int)
    with pytest.raises(icat.exception.ConfigError) as err:
        _, conf = config.getconfig()
    assert 'invalid int value' in str(err.value)


def test_config_type_boolean(fakeClient, tmpconfigfile):
    """Test a boolean configuration variable.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe"]
    config = icat.config.Config(needlogin=False, args=args)
    config.add_variable('flag1', ("--flag1",), 
                        dict(help="Flag 1", action='store_const', const=True), 
                        type=icat.config.boolean)
    config.add_variable('flag2', ("--flag2",), 
                        dict(help="Flag 2", action='store_const', const=True), 
                        type=icat.config.boolean)
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'checkCert', 'configDir', 'configFile', 'configSection', 
                      'flag1', 'flag2', 'http_proxy', 'https_proxy', 
                      'no_proxy', 'url' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_jdoe"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.flag1 == True
    assert conf.flag2 == False

    # Now override flag2 from the command line
    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe", "--flag2"]
    config = icat.config.Config(needlogin=False, args=args)
    config.add_variable('flag1', ("--flag1",), 
                        dict(help="Flag 1", action='store_const', const=True), 
                        type=icat.config.boolean)
    config.add_variable('flag2', ("--flag2",), 
                        dict(help="Flag 2", action='store_const', const=True), 
                        type=icat.config.boolean)
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'checkCert', 'configDir', 'configFile', 'configSection', 
                      'flag1', 'flag2', 'http_proxy', 'https_proxy', 
                      'no_proxy', 'url' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_jdoe"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.flag1 == True
    assert conf.flag2 == True


def test_config_type_flag(fakeClient, tmpconfigfile):
    """Test the special configuration variable type flag.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe"]
    config = icat.config.Config(needlogin=False, args=args)
    config.add_variable('flag1', ("--flag1",), 
                        dict(help="Flag 1"), type=icat.config.flag)
    config.add_variable('flag2', ("--flag2",), 
                        dict(help="Flag 2"), type=icat.config.flag)
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'checkCert', 'configDir', 'configFile', 'configSection', 
                      'flag1', 'flag2', 'http_proxy', 'https_proxy', 
                      'no_proxy', 'url' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_jdoe"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.flag1 == True
    assert conf.flag2 == False

    # Now override the flags from the command line
    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe", 
            "--no-flag1", "--flag2"]
    config = icat.config.Config(needlogin=False, args=args)
    config.add_variable('flag1', ("--flag1",), 
                        dict(help="Flag 1"), type=icat.config.flag)
    config.add_variable('flag2', ("--flag2",), 
                        dict(help="Flag 2"), type=icat.config.flag)
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'checkCert', 'configDir', 'configFile', 'configSection', 
                      'flag1', 'flag2', 'http_proxy', 'https_proxy', 
                      'no_proxy', 'url' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_jdoe"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.flag1 == False
    assert conf.flag2 == True


def test_config_positional(fakeClient, tmpconfigfile):
    """Test adding a positional argument on the command line.

    (There used to be a bug in adding positional arguments, fixed in
    7d10764.)
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_jdoe", "test.dat"]
    config = icat.config.Config(args=args)
    config.add_variable('datafile', ("datafile",), 
                        dict(metavar="input.dat", 
                             help="name of the input datafile"))
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'datafile', 
                      'http_proxy', 'https_proxy', 'no_proxy', 'password', 
                      'promptPass', 'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_jdoe"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "ldap"
    assert conf.username == "jdoe"
    assert conf.password == "pass"
    assert conf.promptPass == False
    assert conf.credentials == {'username': 'jdoe', 'password': 'pass'}
    assert conf.datafile == "test.dat"


def test_config_disable(fakeClient, tmpconfigfile):
    """Configuration variables may be disabled.

    Note that this feature is used internally in config and not
    intended to be used in client code.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_root"]
    config = icat.config.Config(args=args)
    config.confvariable['promptPass'].disabled = True
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'no_proxy', 'password', 'url', 
                      'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "simple"
    assert conf.username == "root"
    assert conf.password == "secret"
    assert conf.credentials == {'username': 'root', 'password': 'secret'}


def test_config_authinfo_simple(fakeClient, monkeypatch, tmpconfigfile):
    """Simple login example.

    Talking to a server that supports getAuthenticatorInfo.
    """

    userkey = Namespace(name='username')
    passkey = Namespace(name='password', hide=True)
    authInfo = [
        Namespace(mnemonic="simple", admin=True, 
                  keys=[userkey, passkey]),
        Namespace(mnemonic="db", 
                  keys=[userkey, passkey]),
        Namespace(mnemonic="anon"),
    ]
    monkeypatch.setattr(FakeClient, "AuthInfo", authInfo)

    args = ["-c", tmpconfigfile.path, "-s", "example_root"]
    config = icat.config.Config(args=args)
    assert list(config.authenticatorInfo) == authInfo
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'no_proxy', 'password', 'promptPass', 
                      'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "simple"
    assert conf.username == "root"
    assert conf.password == "secret"
    assert conf.promptPass == False
    assert conf.credentials == {'username': 'root', 'password': 'secret'}


def test_config_authinfo_anon(fakeClient, monkeypatch, tmpconfigfile):
    """Anon login example.

    Same as last test, but selecting the anon authenticator this time.
    """

    userkey = Namespace(name='username')
    passkey = Namespace(name='password', hide=True)
    authInfo = [
        Namespace(mnemonic="simple", admin=True, 
                  keys=[userkey, passkey]),
        Namespace(mnemonic="db", 
                  keys=[userkey, passkey]),
        Namespace(mnemonic="anon"),
    ]
    monkeypatch.setattr(FakeClient, "AuthInfo", authInfo)

    args = ["-c", tmpconfigfile.path, "-s", "example_root", "-a", "anon"]
    config = icat.config.Config(args=args)
    assert list(config.authenticatorInfo) == authInfo
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'no_proxy', 'promptPass', 'url' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "anon"
    assert conf.promptPass == False
    assert conf.credentials == {}


def test_config_authinfo_anon_only(fakeClient, monkeypatch, tmpconfigfile):
    """
    Talk to a server that supports getAuthenticatorInfo and has only
    the anon authenticator.
    """

    authInfo = [
        Namespace(mnemonic="anon"),
    ]
    monkeypatch.setattr(FakeClient, "AuthInfo", authInfo)

    args = ["-c", tmpconfigfile.path, "-s", "example_anon"]
    config = icat.config.Config(args=args)
    assert list(config.authenticatorInfo) == authInfo
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'no_proxy', 'url' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_anon"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "anon"
    assert conf.credentials == {}


def test_config_authinfo_strange(fakeClient, monkeypatch, tmpconfigfile):
    """
    Talk to a server that requests strange credential keys.  Note the
    prefix "cred_" in the name of configuration variable and the
    command line option.
    """

    secretkey = Namespace(name='secret', hide=True)
    authInfo = [
        Namespace(mnemonic="quirks", 
                  keys=[secretkey]),
    ]
    monkeypatch.setattr(FakeClient, "AuthInfo", authInfo)

    args = ["-c", tmpconfigfile.path, "-s", "example_root", 
            "-a", "quirks", "--cred_secret", "geheim"]
    config = icat.config.Config(args=args)
    assert list(config.authenticatorInfo) == authInfo
    _, conf = config.getconfig()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'cred_secret', 'credentials', 
                      'http_proxy', 'https_proxy', 'no_proxy', 'promptPass', 
                      'url' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "quirks"
    assert conf.promptPass == False
    assert conf.cred_secret == "geheim"
    assert conf.credentials == {'secret': 'geheim'}


def test_config_authinfo_no_authinfo(fakeClient, monkeypatch, tmpconfigfile):
    """
    Talk to an old server that does not support getAuthenticatorInfo.
    """

    args = ["-c", tmpconfigfile.path, "-s", "example_root"]
    config = icat.config.Config(args=args)
    client, conf = config.getconfig()

    with pytest.raises(icat.exception.VersionMethodError) as err:
        authInfo = client.getAuthenticatorInfo()

    attrs = [ a for a in sorted(conf.__dict__.keys()) if a[0] != '_' ]
    assert attrs == [ 'auth', 'checkCert', 'configDir', 'configFile', 
                      'configSection', 'credentials', 'http_proxy', 
                      'https_proxy', 'no_proxy', 'password', 'promptPass', 
                      'url', 'username' ]

    assert conf.configFile == [tmpconfigfile.path]
    assert conf.configDir == tmpconfigfile.dir
    assert conf.configSection == "example_root"
    assert conf.url == "https://icat.example.com/ICATService/ICAT?wsdl"
    assert conf.auth == "simple"
    assert conf.username == "root"
    assert conf.password == "secret"
    assert conf.promptPass == False
    assert conf.credentials == {'username': 'root', 'password': 'secret'}
