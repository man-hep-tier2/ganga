from __future__ import absolute_import

import datetime
import os
import re
import subprocess
from getpass import getpass
from glob import glob

import Ganga.Utility.logging
from Ganga.Utility.Shell import Shell

from .ICredentialInfo import ICredentialInfo, cache
from .ICredentialRequirement import ICredentialRequirement
from .exceptions import CredentialRenewalError

logger = Ganga.Utility.logging.getLogger()

info_pattern = re.compile(r"^User's \(AFS ID \d*\) tokens for (?P<id>\w*@\S*) \[Expires (?P<expires>.*)\]$", re.MULTILINE)


class AfsTokenInfo(ICredentialInfo):
    """
    A wrapper around an AFS token

    For now it is very CERN-specific (or at least only follows the CERN use-case)
    """

    def __init__(self, requirements, check_file=False, create=False):
        self.shell = Shell()

        super(AfsTokenInfo, self).__init__(requirements, check_file, create)

    def create(self):
        """
        Creates a new AFS token

        Raises:
            CredentialRenewalError: If the renewal process returns a non-zero value
        """

        command = 'kinit'

        process = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdoutdata, stderrdata = process.communicate(getpass('Kerberos password: '))

        if process.returncode == 0:
            logger.info('AFS token %s created. Valid for %s', self.location, self.time_left())
        else:
            raise CredentialRenewalError(stderrdata)

    def renew(self):
        """
        Renews the AFS token

        Raises:
            CredentialRenewalError: If the renewal process returns a non-zero value
        """

        status, output, message = self.shell.cmd1('kinit -R')

        if status != 0:
            logger.debug('kinit -R failed, creating as new')
            self.create()

    def destroy(self):
        self.shell.cmd1('unlog')

        if self.location:
            os.remove(self.location)

    @property
    @cache
    def info(self):
        status, output, message = self.shell.cmd1('tokens')
        return output

    @cache
    def expiry_time(self):
        info = self.info
        matches = re.finditer(info_pattern, info)

        if not matches:
            return datetime.timedelta()

        expires = [match.group('expires') for match in matches if match.group('id') == 'afs@cern.ch'][0]
        expires = datetime.datetime.strptime(expires, '%b %d %H:%M')
        now = datetime.datetime.now()
        expires = expires.replace(year=now.year)

        # If the expiration date is in the past then assume it should be in the future
        if expires < now:
            expires = expires.replace(year=now.year+1)

        return expires

    def default_location(self):
        krb_env_var = os.getenv('KRB5CCNAME', '')
        if krb_env_var.startswith('FILE:'):
            krb_env_var = krb_env_var[5:]

        default_name_prefix = '/tmp/krb5cc_{uid}'.format(uid=os.getuid())
        matches = glob(default_name_prefix+'*')  # Check for partial matches on disk
        if len(matches) == 1:  # If one then use it
            filename_guess = matches[0]
        else: # Otherwise use the default
            filename_guess = default_name_prefix
        return krb_env_var or filename_guess


class AfsToken(ICredentialRequirement):
    """
    An object specifying the requirements of an AFS token
    """
    _schema = ICredentialRequirement._schema.inherit_copy()

    _category = 'CredentialRequirement'

    info_class = AfsTokenInfo

    def encoded(self):
        return ''
