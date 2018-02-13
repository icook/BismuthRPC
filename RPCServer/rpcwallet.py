#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Wallet class for Bismuth RJson-RPC Server

@EggPool

Thanks to @rvanduiven
"""

#import sys
import os
import json
import re
import zipfile
import datetime
import io

from rpckeys import Key

__version__ = "0.0.3"


class Wallet:
    """
    Handles a .wallet directory, with accounts, addresses, keys and wallet encryption/backup.
    Content is stored as json, within several dir to limit the files in each directory
    """
    # Warning: make sure this is thread safe as it will be called from multiple threads. Use queues and locks when needed.
    # TODO
    
    __slots__ = ('path', 'verbose', 'encrypted', 'locked', 'passphrase', 'IV','index', 'key', 'address_to_account')
    # TODO: those properties should be converted to _protected later on.
    
    def __init__(self, path='.wallet', verbose=False):
        self.path = path
        self.verbose = verbose
        self.encrypted = False
        self.locked = False
        self.passphrase = ''
        self.index = None
        self.address_to_account = {}
        self.IV = 16 * '\x00'
        if not os.path.exists(path):
            if self.verbose:
                print(path,"does not exist, creating")
                os.mkdir(path)
        # Since keys will be used everywhere, let's have our instance ready to run.
        self.key = Key(verbose=verbose)
        self.load()
        if self.verbose:
            print(self.index)
        #self.reindex()


    def load(self):
        """
        Loads the current wallet state or init if the dir is empty.
        """
        # At this point the dir exists.
        index_fname = self.path+'/index.json'
        rindex_fname = self.path+'/rindex.json'
        if not os.path.exists(index_fname):
            if self.verbose:
                print(index_fname,"does not exist, creating default")
                # Default index file
                self.index = {'version': __version__, 'encrypted':False}
                with open(index_fname, 'w') as outfile:  
                    json.dump(self.index, outfile)
                # Inverted index
                self.address_to_account = {}
                self._save_rindex()
        else:
            with open(index_fname) as json_file:  
                self.index = json.load(json_file)
            try:
                with open(rindex_fname) as json_file:  
                    self.address_to_account = json.load(json_file)
            except:
                self.address_to_account = {}


    def _parse_accounts(self):
        """
        A generator that yields the accounts of the current wallet
        """
        # Walk all files, search for keys and parse them
        for root, dirs, files in os.walk(self.path):
            for afile in files:
                # check if this is a json file
                ext = os.path.splitext(afile)[-1].lower()
                if ext != ".json":
                    continue
                # Avoid the indexes
                if afile.lower() in ('index.json','rindex.json') :
                    continue
                # io is used here to avoid cross platform issues with UTF-8 BOM.
                with io.open(os.path.join(root,afile), 'r', encoding='utf-8-sig') as json_file:
                    try:
                        json_contents = json_file.read()
                        res = json.loads(json_contents)
                        account = os.path.splitext(afile)[0]
                        if 'default' == account:
                            account = ''
                        yield (account, res)
                    except Exception as e:
                        if self.verbose:
                            print("Possible error {} on file {}".format(e, afile))
                
                
    def reindex(self):
        """
        Regenerates the inverted index self.address_to_account (rindex.json)
        """
        if self.verbose:
            print("Reindexing wallet - can take some time")
        self.address_to_account = {}
        for account_name, account_details in self._parse_accounts():
            try:
                for address in account_details['addresses']:
                    self.address_to_account[address[0]] = account_name
            except:
                pass
        self._save_rindex()
        return True


    def _save_rindex(self):
        """
        Sync our reverse index to file
        """
        rindex_fname = self.path+'/rindex.json'
        # TODO: Lock
        with open(rindex_fname, 'w') as outfile:  
            json.dump(self.address_to_account, outfile)


    def _check_account_name(self, account=''):
        """
        Raise an exception if account name does not comply
        An account is 2-128 characters long, and may only contains the Base64 Character set. 
        """
        if account == '':
            # empty if default account
            return True
        if len(account) < 2 or len(account) > 128:
            raise InvalidAccountName
        # Only b64 charset
        if re.search('[^a-zA-Z0-9\+\/]', account) :
            raise InvalidAccountName

                
    def _get_account(self, account=''):
        """
        Returns a dict with the given account info.
        """
        self._check_account_name(account)
        if '' == account or 'default' == account:
            fname = self.path+'/default.json'
            path = self.path
        else:
            adir = account[:2]
            path = self.path+'/'+adir
            fname = path+'/'+account+'.json'
        if not os.path.isfile(fname):
            if self.verbose:
                print(fname,"does not exist, creating default")
            # Default account file
            self.key.generate() # This takes some time.
            res = {'encrypted':False, 'addresses':[self.key.as_list]}
            # and save account
            if not os.path.exists(path):
                os.mkdir(path)
            with open(fname, 'w') as outfile:
                json.dump(res, outfile)
            # update reverse index
            self.address_to_account[self.key.address] = account
            self._save_rindex()
        else:
            with open(fname) as json_file:  
                res = json.load(json_file)
        return res

        
    def _save_account(self, account_dict, account=''):
        """
        Saves account info back to disk
        """
        # TODO: lock
        self._check_account_name(account)
        if '' == account:
            fname = self.path+'/default.json'
            path = self.path
        else:
            adir = account[:2]
            path = self.path+'/'+adir
            fname = path+'/'+account+'.json'
        if not os.path.exists(path):
            os.mkdir(path)
        with open(fname, 'w') as outfile:  
            json.dump(account_dict, outfile)            
            
        return True


    def get_account_address(self, anaccount=''):
        """
        returns the default address of the given account
        """
        account = self._get_account(anaccount) # This will handle address creation if doesn't exists yet.
        addresses = account['addresses'][0]
        # Addresses is on fact [address,privkey,pubkey]
        # with privkey encrypted if wallet is.
        return addresses[0]


    def get_account(self, address):
        """
        returns the name of the account associated with the given address.
        """
        try:
            return self.address_to_account[address]
        except:
            raise UnknownnAddress


    def list_accounts(self, minconf=1):
        """
        Returns dict that has account names as keys, account balances as values.
        """
        # TODO: add account balance
        try:
            accounts = {account_name: -1 for account_name, _ in self._parse_accounts()}
            return accounts
        except:
            raise UnknownnAddress

    def _get_keys_for_address(self, address):
        """Finds the account of the address, then it's keys"""
        print("_get_keys_for_address", address)
        try:
            print("add 2 account", self.address_to_account[address])
            account = self._get_account(self.address_to_account[address])
            print("account", account)
            for keys in account['addresses']:
                # keys is [address, encrypted, privkey, pubkey]
                if keys[0] == address:
                    return keys
            raise UnknownnAddress
        except:
            raise UnknownnAddress


    def dump_privkey(self, address):
        """
        returns the private key corresponding to an address. (But does not remove it from the wallet.)
        """
        keys = self._get_keys_for_address(address)
        return keys[2]


    def get_new_address(self, anaccount=''):
        """
        returns a new address for the given account
        """
        account_dict = self._get_account(anaccount) # This will handle address creation if doesn't exists yet.
        self.key.generate() # This takes some time.
        
        account_dict['addresses'].append(self.key.as_list)
        self._save_account(account_dict, account=anaccount)
        # update reverse index
        self.address_to_account[self.key.address] = anaccount
        self._save_rindex()
        return self.key.address

        
    def get_addresses_by_account(self, anaccount=''):
        """
        returns the list of addresses of the given account
        """
        account = self._get_account(anaccount)
        return [address[0] for address in account['addresses']]
        
        
    def backup_wallet(self, afilename='bwallet.zip'):
        """
        Saves the whole wallet directory in a zip or tgz archive
        """
        # Test possible path existence
        backup_path = os.path.dirname(os.path.abspath(afilename))
        if not os.path.exists(backup_path):
            raise InvalidPath
        # Open a zipfile for writing - afilename is the full path and filename of where to save.
        wallet_zip = zipfile.ZipFile(afilename, 'w', zipfile.ZIP_DEFLATED)
        # Walk all files and dirs and add to zipfile - self.path is wallet directory 
        for root, dirs, files in os.walk(self.path):
            for file in files:
                wallet_zip.write(os.path.join(root, file))
        wallet_zip.close()
        return True
        
        
    def dump_wallet(self, afilename='dump.txt', version='n/a'):
        """
        Sends back a list of all privkeys for the wallet.
        """
        # Test possible path existence
        dump_path = os.path.dirname(os.path.abspath(afilename))
        if not os.path.exists(dump_path):
            raise InvalidPath
        if not os.path.exists(afilename):
            if self.verbose:
                print(afilename, "does not exist, creating")
        with open(afilename, 'w') as outfile:
            # Write basic output
            outfile.write("# Wallet dump created by bismuthd {} \n".format(version))
            outfile.write("# * Created on {} \n".format(datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')))
            if self.encrypted:
                outfile.write('# * Wallet is Encrypted\n')
            else:
                outfile.write('# * Wallet is Unencrypted\n')
            """ @TODO add block information like:
                # * Best block at time of backup was 227221 (0000000026ede4c10594af8087748507fb06dcd30b8f4f48b9cc463cabc9d767),
                #   mined on 2014-04-29T21:15:07Z
            """
            for account_name, account_details in self._parse_accounts():
                try:
                    for address in account_details['addresses']:
                        """
                            Output format:
                            privkey1 RESERVED account=account1 addr=address1
                            - RESERVED is for timestamp later
                        """
                        outfile.write("{} RESERVED account={} addr={}\n".format(address[2].replace('\n','').replace('\r',''), account_name, address[0]))
                except:
                    # Silently ignore
                    pass
        # needed for bitcoind compatibility
        return None


"""
Custom exceptions
"""


class InvalidAccountName(Exception):
    code = -33001
    message = 'Invalid Account Name - 2 to 128 chars from b64 charset only.'
    data = None


class InvalidPath(Exception):
    code = -33002
    message = 'Path does not exist'
    data = None


class UnknownnAddress(Exception):
    code = -33003
    message = 'Unknown Address'
    data = None


if __name__ == "__main__":
    print("I'm a module, can't run!")
