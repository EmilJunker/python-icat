"""Provide the Config class.
"""

import sys
import os
import os.path
import getpass
import argparse
import ConfigParser
import warnings
from icat.client import Client
from icat.authinfo import AuthenticatorInfo, LegacyAuthenticatorInfo
from icat.exception import ConfigError, VersionMethodError

__all__ = ['boolean', 'flag', 'Configuration', 'Config']


if sys.platform.startswith("win"):
    cfgdirs = [ os.path.join(os.environ['ProgramData'], "ICAT"),
                os.path.join(os.environ['AppData'], "ICAT"),
                os.path.join(os.environ['LocalAppData'], "ICAT"), 
                "", ]
else:
    cfgdirs = [ "/etc/icat", 
                os.path.expanduser("~/.config/icat"),
                os.path.expanduser("~/.icat"), 
                "", ]
"""Search path for the configuration file"""
cfgfile = "icat.cfg"
"""Configuration file name"""
defaultsection = None
"""Default value for `configSection`"""

# Internal hack, intentionally not documented.
_argparse_divert_syserr = True


def boolean(value):
    """Test truth value.

    Convert the string representation of a truth value, such as ``0``,
    ``1``, ``yes``, ``no``, ``true``, or ``false`` to :class:`bool`.
    This function is suitable to be passed as type to
    :meth:`icat.config.Config.add_variable`.
    """
    if isinstance(value, basestring):
        if value.lower() in ["0", "no", "n", "false", "f", "off"]:
            return False
        elif value.lower() in ["1", "yes", "y", "true", "t", "on"]:
            return True
        else:
            raise ValueError("Invalid truth value '%s'" % value)
    elif isinstance(value, bool):
        return value
    else:
        raise TypeError("invalid type %s, expect bool or str" % type(value))

flag = object()
"""Special boolean variable type that defines two command line arguments."""

def cfgpath(p):
    """Search for a file in some default directories.

    The argument `p` should be a file path name.  If `p` is absolute,
    it will be returned unchanged.  Otherwise, `p` will be resolved
    against the directories in :data:`icat.config.cfgdirs` in reversed
    order.  If a file with the resulting path is found to exist, this
    path will be returned, first match wins.  If no file exists in any
    of the directories, `p` will be returned unchanged.

    This function is suitable to be passed as `type` argument to
    :meth:`icat.config.Config.add_variable`.
    """
    if os.path.isabs(p):
        return p
    else:
        for d in reversed(cfgdirs):
            fp = os.path.abspath(os.path.join(d, p))
            if os.path.isfile(fp):
                return fp
        else:
            return p


class _argparserDisableExit:
    """Temporarily redirect stdout to devnull and disable exit from an
    ArgumentParser.  Needed during partially parsing of command line.
    """
    def __init__(self, parser):
        self._parser = parser
    def __enter__(self):
        def noexit(status=0, message=None):
            raise ConfigError("ArgumentParser exit (%d,%s)" % (status, message))
        if _argparse_divert_syserr:
            self._old_stdout = sys.stdout
            sys.stdout = open(os.devnull, "wt")
            self._old_stderr = sys.stderr
            sys.stderr = open(os.devnull, "wt")
        self._parser.exit = noexit
        return self._parser
    def __exit__(self, exctype, excinst, exctb):
        del self._parser.exit
        if _argparse_divert_syserr:
            sys.stdout.close()
            sys.stdout = self._old_stdout
            sys.stderr.close()
            sys.stderr = self._old_stderr


def post_configFile(config, configuration):
    """Postprocess configFile: read the configuration file.
    """
    configuration.configFile = config.conffile.read(configuration.configFile)

def post_configSection(config, configuration):
    """Postprocess configSection: set the configuration section.
    """
    config.conffile.setsection(configuration.configSection)

def post_auth(config, configuration):
    """Postprocess auth: enable credential keys for the selected authenticator.
    """
    try:
        keys = config.authenticatorInfo.getCredentialKeys(configuration.auth)
    except KeyError as e:
        raise ConfigError(str(e))
    for k in keys:
        config.credentialKey[k].disabled = False

def post_promptPass(config, configuration):
    """Postprocess promptPass: move the interactive source in front if set.
    """
    if configuration.promptPass:
        # promptPass was explicitly requested.  Move the interactive
        # source on first position.
        config.sources.remove(config.interactive)
        config.sources.insert(0, config.interactive)
    elif isinstance(config.confvariable['promptPass'].source, 
                    ConfigSourceDefault):
        # promptPass was not specified.  Special rule: if any of the
        # non-interactive credentials was given in the command line,
        # disregard environment and file for the interactive
        # credentials.  Move the interactive source on second position
        # right after cmdargs.
        for var in config.credentialKey.values():
            if isinstance(var.source, ConfigSourceCmdArgs):
                prompt = True
                break
        else:
            prompt = False
        if prompt:
            config.sources.remove(config.interactive)
            config.sources.insert(1, config.interactive)


class ConfigVariable(object):
    """Describe a configuration variable.
    """
    def __init__(self, name, envvar, optional, default, convert, subst):
        self.name = name
        self.envvar = envvar
        self.optional = optional
        self.default = default
        self.convert = convert
        self.subst = subst
        self.key = None
        self.interactive = False
        self.postprocess = None
        self.disabled = False
        self.source = None
    def get(self, value):
        if self.convert and value is not None:
            try:
                return self.convert(value)
            except (TypeError, ValueError):
                typename = getattr(self.convert, "__name__", str(self.convert))
                raise ConfigError("%s: invalid %s value: %r" 
                                  % (self.name, typename, value))
        else:
            return value


class ConfigSource(object):
    """A configuration source.

    This is the base class for all configuration sources, such as
    command line arguments, configuration files, and environment
    variables.
    """
    def get(self, variable):
        raise NotImplementedError


class ConfigSourceCmdArgs(ConfigSource):
    """Get configuration from command line arguments.
    """
    def __init__(self, argparser, args, partial):
        super(ConfigSourceCmdArgs, self).__init__()
        if partial:
            (self.args, rest) = argparser.parse_known_args(args)
        else:
            self.args = argparser.parse_args(args)

    def get(self, variable):
        return variable.get(getattr(self.args, variable.name, None))


class ConfigSourceEnvironment(ConfigSource):
    """Get configuration from environment variables.
    """
    def get(self, variable):
        if variable.envvar:
            return variable.get(os.environ.get(variable.envvar, None))
        else:
            return None


class ConfigSourceFile(ConfigSource):
    """Get configuration from a configuration file.
    """
    def __init__(self, defaultFiles):
        super(ConfigSourceFile, self).__init__()
        self.confparser = ConfigParser.RawConfigParser()
        self.defaultFiles = defaultFiles
        self.section = None

    def read(self, filename):
        if filename:
            readfile = self.confparser.read(filename)
            if not readfile:
                raise ConfigError("Could not read config file '%s'." % filename)
        elif filename is None:
            readfile = self.confparser.read(self.defaultFiles)
        else:
            readfile = filename
        return readfile

    def setsection(self, section):
        if section and not self.confparser.has_section(section):
            raise ConfigError("Could not read config section '%s'." % section)
        self.section = section
        return section

    def get(self, variable):
        value = None
        if self.section:
            try:
                value = self.confparser.get(self.section, variable.name)
            except ConfigParser.NoOptionError:
                pass
        return variable.get(value)


class ConfigSourceInteractive(ConfigSource):
    """Prompt the user for a value.
    """
    def get(self, variable):
        if not variable.interactive:
            return None
        else:
            prompt = "%s: " % variable.key.capitalize()
            return variable.get(getpass.getpass(prompt))


class ConfigSourceDefault(ConfigSource):
    """Handle the case that some variable is not set from any other source.
    """
    def get(self, variable):
        value = variable.default
        if value is None and not variable.optional:
            raise ConfigError("Config option '%s' not given." % variable.name)
        return variable.get(value)


class Configuration(object):
    """Provide a name space to store the configuration.

    :meth:`icat.config.Config.getconfig` returns a Configuration
    object having the configuration values stored in the respective
    attributes.
    """
    def __init__(self, config):
        super(Configuration, self).__init__()
        self._config = config

    def __getattr__(self, attr):
        if attr == "configDir":
            warnings.warn("The 'configDir' configuration variable is "
                          "deprecated and will be removed in python-icat 1.0.", 
                          DeprecationWarning, stacklevel=2)
            if getattr(self, "configFile", None):
                f = self.configFile[-1]
                return os.path.dirname(os.path.abspath(f))
            else:
                return None
        else:
            raise AttributeError("%s object has no attribute %s" % 
                                 (type(self).__name__, attr))

    def __str__(self):
        typename = type(self).__name__
        arg_strings = []
        vars = [var.name for var in self._config.confvariables] \
            + self._config.ReservedVariables
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for f in vars:
                if hasattr(self, f):
                    arg_strings.append('%s=%r' % (f, getattr(self, f)))
        return '%s(%s)' % (typename, ', '.join(arg_strings))

    def as_dict(self):
        """Return the configuration as a dict."""
        vars = [var.name for var in self._config.confvariables] \
            + self._config.ReservedVariables
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = { f:getattr(self, f) for f in vars if hasattr(self, f) }
        return d


class Config(object):
    """Set configuration variables.

    Allow configuration variables to be set via command line
    arguments, environment variables, configuration files, and default
    values, in this order.  The first value found will be taken.
    Command line arguments and configuration files are read using the
    standard Python library modules :mod:`argparse` and
    :mod:`ConfigParser` respectively, see the documentation of these
    modules for details on how to setup custom arguments or for the
    format of the configuration files.

    The constructor sets up some predefined configuration variables.

    :param defaultvars: if set to :const:`False`, no default
        configuration variables other then `configFile` and
        `configSection` will be defined.  The arguments `needlogin`
        and `ids` will be ignored in this case.
    :type defaultvars: :class:`bool`
    :param needlogin: if set to :const:`False`, the configuration
        variables `auth`, `username`, `password`, `promptPass`, and
        `credentials` will be left out.
    :type needlogin: :class:`bool`
    :param ids: the configuration variable `idsurl` will not be set up
        at all, or be set up as a mandatory, or as an optional
        variable, if this is set to :const:`False`, to "mandatory", or
        to "optional" respectively.
    :type ids: :class:`bool` or :class:`str`
    :param args: list of command line arguments or :const:`None`.  If
        not set, the command line arguments will be taken from
        :data:`sys.argv`.
    :type args: :class:`list` of :class:`str`
    """

    ReservedVariables = ['configDir', 'credentials']
    """Reserved names of configuration variables."""

    def __init__(self, defaultvars=True, needlogin=True, ids="optional", 
                 args=None):
        """Initialize the object.
        """
        super(Config, self).__init__()
        self.defaultFiles = [os.path.join(d, cfgfile) for d in cfgdirs]
        self.defaultvars = defaultvars
        self.confvariables = []
        self.confvariable = {}
        self.args = args
        self.argparser = argparse.ArgumentParser()
        self._add_fundamental_variables()
        if self.defaultvars:
            self.needlogin = needlogin
            self.ids = ids
            self._add_basic_variables()
            self.client_kwargs, self.client = self._setup_client()
            if self.needlogin:
                self._add_cred_variables()
        else:
            self.needlogin = None
            self.ids = None
            self.client_kwargs = None
            self.client = None


    def add_variable(self, name, arg_opts=(), arg_kws=None,
                     envvar=None, optional=False, default=None, type=None, 
                     subst=False):

        """Defines a new configuration variable.

        Note that the value of some configuration variable may
        influence the evaluation of other variables.  For instance,
        if `configFile` and `configSection` are set, the values for
        other configuration variables are searched in this
        configuration file.  Thus, the evaluation order of the
        configuration variables is important.  The variables are
        evaluated in the order that this method is called to define
        the respective variable.

        Call :meth:`argparse.ArgumentParser.add_argument` to add a new
        command line argument if `arg_opts` is set.

        :param name: the name of the variable.  This will be used as
            the name of the attribute of
            :class:`icat.config.Configuration` returned by
            :meth:`icat.config.Config.getconfig` and as the name of
            the option to be looked for in the configuration file.
            The name must be unique and not in
            :attr:`icat.config.Config.ReservedVariables`.  If
            `arg_opts` corresponds to a positional argument, the name
            must be equal to this argument name.
        :type name: :class:`str`
        :param arg_opts: command line flags associated with this
            variable.  This will be passed as `name or flags` to
            :meth:`argparse.ArgumentParser.add_argument`.
        :type arg_opts: :class:`tuple` of :class:`str`
        :param arg_kws: keyword arguments to be passed to
            :meth:`argparse.ArgumentParser.add_argument`.
        :type arg_kws: :class:`dict`
        :param envvar: name of the environment variable or
            :const:`None`.  If set, the value for the variable may be
            set from the respective environment variable.
        :type envvar: :class:`str`
        :param optional: flag wether the configuration variable is
            optional.  If set to :const:`False` and `default` is
            :const:`None` the variable is mandatory.
        :type optional: :class:`bool`
        :param default: default value.
        :param type: type to which the value should be converted.
            This must be a callable that accepts one string argument
            and returns the desired value.  The builtins :func:`int`
            and :func:`float` are fine.  If set to :const:`None`, the
            string value is taken as is.  If applicable, the default
            value will also be passed through this conversion.  The
            special value :data:`icat.config.flag` may also be used to
            indicate a variant of :func:`icat.config.boolean`.
        :type type: callable
        :param subst: flag wether substitution of other configuration
            variables using the ``%`` interpolation operator shall be
            performed.  If set to :const:`True`, the value may contain
            conversion specifications such as ``%(othervar)s``.  This
            will then be substituted by the value of `othervar`.  The
            referenced variable must have been defined earlier.
        :type subst: :class:`bool`
        :raise ValueError: if the name is not valid.
        :see: the documentation of the :mod:`argparse` standard
            library module for details on `arg_opts` and `arg_kws`.
        """
        if name in self.ReservedVariables or name[0] == '_':
            raise ValueError("Config variable name '%s' is reserved." % name)
        if name in self.confvariable:
            raise ValueError("Config variable '%s' is already defined." % name)
        if arg_kws is None:
            arg_kws = dict()
        else:
            arg_kws = dict(arg_kws)
        if type == flag:
            # flag is a variant of boolean that defines two command
            # line arguments, a positive and a negative one.
            if '-' not in self.argparser.prefix_chars:
                raise ValueError("flag type requires '-' to be in the "
                                 "argparser's prefix_chars.")
            if len(arg_opts) != 1 or not arg_opts[0].startswith('--'):
                raise ValueError("invalid argument options for flag type.")
            arg = arg_opts[0][2:]
            arg_kws['dest'] = name
            arg_kws['action'] = 'store_const'
            if default:
                arg_kws['const'] = False
                self.argparser.add_argument("--no-"+arg, **arg_kws)
                arg_kws['const'] = True
                arg_kws['help'] = argparse.SUPPRESS
                self.argparser.add_argument("--"+arg, **arg_kws)
            else:
                arg_kws['const'] = True
                self.argparser.add_argument("--"+arg, **arg_kws)
                arg_kws['const'] = False
                arg_kws['help'] = argparse.SUPPRESS
                self.argparser.add_argument("--no-"+arg, **arg_kws)
            type = boolean
        elif arg_opts:
            prefix = self.argparser.prefix_chars
            if len(arg_opts) == 1 and arg_opts[0][0] not in prefix:
                # positional argument
                if arg_opts[0] != name:
                    raise ValueError("Config variable name '%s' must be equal "
                                     "to argument name for positional "
                                     "argument." % name)
            else:
                # optional argument
                arg_kws['dest'] = name
            self.argparser.add_argument(*arg_opts, **arg_kws)
        var = ConfigVariable(name, envvar, optional, default, type, subst)
        self.confvariable[name] = var
        self.confvariables.append(var)
        return var

    def getconfig(self):
        """Get the configuration.

        Parse the command line arguments, evaluate environment
        variables, read the configuration file, and apply default
        values (in this order) to get the value for each defined
        configuration variable.  The first defined value found will be
        taken.

        :return: a tuple with two items, a client initialized to
            connect to an ICAT server according to the configuration
            and an object having the configuration values set as
            attributes.  The client will be :const:`None` if the
            `defaultvars` constructor argument was :const:`False`.
        :rtype: :class:`tuple` of :class:`icat.client.Client` and
            :class:`icat.config.Configuration`
        :raise ConfigError: if `configFile` is defined but the file by
            this name can not be read, if `configSection` is defined
            but no section by this name could be found in the
            configuration file, if an invalid value is given to a
            variable, or if a mandatory variable is not defined.
        """
        config = self._getconfig()

        if self.needlogin:
            config.credentials = { 
                k: getattr(config, self.credentialKey[k].name)
                for k in self.authenticatorInfo.getCredentialKeys(config.auth)
            }

        return (self.client, config)

    def _add_fundamental_variables(self):
        """The fundamental variables that are always needed.
        """
        var = self.add_variable('configFile', ("-c", "--configfile"), 
                                dict(help="config file"),
                                envvar='ICAT_CFG', optional=True)
        var.postprocess = post_configFile
        var = self.add_variable('configSection', ("-s", "--configsection"), 
                                dict(help="section in the config file", 
                                     metavar='SECTION'), 
                                envvar='ICAT_CFG_SECTION', optional=True, 
                                default=defaultsection)
        var.postprocess = post_configSection

    def _add_basic_variables(self):
        """The basic variables needed to setup the client.
        """
        self.add_variable('url', ("-w", "--url"), 
                          dict(help="URL to the web service description"),
                          envvar='ICAT_SERVICE')
        if self.ids:
            if self.ids == "mandatory":
                idsopt = False
            elif self.ids == "optional":
                idsopt = True
            else:
                raise ValueError("invalid value '%s' for argument ids." 
                                 % self.ids) 
            self.add_variable('idsurl', ("--idsurl",), 
                              dict(help="URL to the ICAT Data Service"),
                              envvar='ICAT_DATA_SERVICE', optional=idsopt)
        self.add_variable('checkCert', ("--check-certificate",), 
                          dict(help="don't verify the server certificate"), 
                          type=flag, default=True)
        self.add_variable('http_proxy', ("--http-proxy",), 
                          dict(help="proxy to use for http requests"),
                          envvar='http_proxy', optional=True)
        self.add_variable('https_proxy', ("--https-proxy",), 
                          dict(help="proxy to use for https requests"),
                          envvar='https_proxy', optional=True)
        self.add_variable('no_proxy', ("--no-proxy",), 
                          dict(help="list of exclusions for proxy use"),
                          envvar='no_proxy', optional=True)

    def _add_cred_variables(self):
        """The variables that define the credentials needed for login.
        """
        self.credentialKey = {}
        authInfo = None
        if self.client:
            try:
                authInfo = self.client.getAuthenticatorInfo()
            except VersionMethodError:
                pass
        authArgOpts = dict(help="authentication plugin")
        if authInfo:
            self.authenticatorInfo = AuthenticatorInfo(authInfo)
            authArgOpts['choices'] = self.authenticatorInfo.getAuthNames()
        else:
            self.authenticatorInfo = LegacyAuthenticatorInfo()

        var = self.add_variable('auth', ("-a", "--auth"), authArgOpts,
                                envvar='ICAT_AUTH')
        var.postprocess = post_auth
        for key in self.authenticatorInfo.getCredentialKeys(None, hide=False):
            self._add_credential_key(key)
        hidden = self.authenticatorInfo.getCredentialKeys(None, hide=True)
        if hidden:
            var = self.add_variable('promptPass', ("-P", "--prompt-pass"), 
                                    dict(help="prompt for the password", 
                                         action='store_const', const=True), 
                                    type=boolean, default=False)
            var.postprocess = post_promptPass
        for key in hidden:
            self._add_credential_key(key, hide=True)

    def _add_credential_key(self, key, hide=False):
        if key == 'username' and not hide:
            var = self.add_variable('username', ("-u", "--user"), 
                                    dict(help="username"),
                                    envvar='ICAT_USER')
        elif key == 'password' and hide:
            var = self.add_variable('password', ("-p", "--pass"), 
                                    dict(help="password"))
        else:
            var = self.add_variable('cred_' + key, ("--cred_" + key,), 
                                    dict(help=key))
        var.key = key
        if hide:
            var.interactive = True
        var.disabled = True
        self.credentialKey[key] = var

    def _setup_client(self):
        """Initialize the client.
        """
        try:
            with _argparserDisableExit(self.argparser):
                config = self._getconfig(partial=True)
        except ConfigError:
            return None, None
        client_kwargs = {}
        if self.ids:
            client_kwargs['idsurl'] = config.idsurl
        client_kwargs['checkCert'] = config.checkCert
        if config.http_proxy or config.https_proxy:
            proxy={}
            if config.http_proxy:
                proxy['http'] = config.http_proxy
                os.environ['http_proxy'] = config.http_proxy
            if config.https_proxy:
                proxy['https'] = config.https_proxy
                os.environ['https_proxy'] = config.https_proxy
            client_kwargs['proxy'] = proxy
        if config.no_proxy:
            os.environ['no_proxy'] = config.no_proxy
        return client_kwargs, Client(config.url, **client_kwargs)

    def _getconfig(self, partial=False):
        """Get the configuration.
        """
        self.cmdargs = ConfigSourceCmdArgs(self.argparser, self.args, partial)
        self.environ = ConfigSourceEnvironment()
        self.conffile = ConfigSourceFile(self.defaultFiles)
        self.interactive = ConfigSourceInteractive()
        self.defaults = ConfigSourceDefault()
        self.sources = [ self.cmdargs, self.environ, self.conffile, 
                         self.interactive, self.defaults ]
        # this code relies on the fact, that the first two variables in
        # self.confvariables are 'configFile' and 'configSection' in that
        # order.
        config = Configuration(self)
        for var in self.confvariables:
            if var.disabled:
                continue
            for source in self.sources:
                value = source.get(var)
                if value is not None:
                    var.source = source
                    break
            if value is not None and var.subst:
                value = value % config.as_dict()
            setattr(config, var.name, value)
            if var.postprocess:
                var.postprocess(self, config)
        return config
