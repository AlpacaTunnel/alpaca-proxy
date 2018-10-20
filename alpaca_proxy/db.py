#!/usr/bin/env python3

# Store Nano block history and proxy clients bill.

# Author: twitter.com/alpacatunnel

import sqlite3

from .log import print_log


class DB():
    ROLE_SERVER = 'server'
    ROLE_CLIENT = 'client'

    def __init__(self, file_name):
        self.file_name = file_name
        self.conn = sqlite3.connect(file_name)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        """
        Table `nano_account`: store the accounts of the server and all clients.
        role: 'server' or 'client'.
        The server may have different accounts.
        TODO: each client uses a unique server account.

        Table `block_chain`: store the history of current account.

        Table `proxy_bill`: store client account and their balance. (All Nano unit is raw.)
        Server account may change, but Nano paid to all server accounts will be counted.
        total_pay = all pay from a client to all server accounts.
        total_pay = total_spend + balance
        The server should update and check the bill every hour, or every 100MB, or every 1000 requests.
        """

        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS `nano_account` (
            `id`                INTEGER,
            `account`           TEXT,
            `role`              TEXT,
            `frontier`          TEXT,
            PRIMARY KEY (`id`),
            CONSTRAINT `unique_xrb_account_1` UNIQUE (`account`)
        );
        ''')

        # source/destination are for legacy blocks(receive/send)
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS `block_chain` (
            `id`                INTEGER,
            `owner_account`     INTEGER,
            `account`           TEXT,
            `hash`              TEXT,
            `previous`          TEXT,
            `type`              TEXT,
            `subtype`           TEXT,
            `amount`            TEXT,
            `balance`           TEXT,
            `link`              TEXT,
            `representative`    TEXT,
            `signature`         TEXT,
            `work`              TEXT,
            `source`            TEXT,
            `destination`       TEXT,
            `next`              TEXT,
            PRIMARY KEY (`id`),
            CONSTRAINT `unique_block_hash_1` UNIQUE (`hash`),
            FOREIGN KEY (`owner_account`) REFERENCES `nano_account` (`id`)
        );
        ''')

        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS `proxy_bill` (
            `id`                INTEGER,
            `client_account`    INTEGER,
            `total_pay`         TEXT,
            `total_spend`       TEXT,
            `balance`           TEXT,
            `total_bytes`       TEXT,
            `total_requests`    TEXT,
            PRIMARY KEY (`id`),
            FOREIGN KEY (`client_account`) REFERENCES `nano_account` (`id`),
            CONSTRAINT `unique_bill_account_1` UNIQUE (`client_account`)
        );
        ''')

        self.conn.commit()

    def get_account(self, account):
        self.cursor.execute('SELECT * from `nano_account` WHERE `account` = ?', (account, ))
        return self.cursor.fetchone()  # None or dict

    def get_server_accounts(self):
        self.cursor.execute('''SELECT * from `nano_account` WHERE `role` = "{}"'''.format(self.ROLE_SERVER))
        accounts = []
        for account in self.cursor.fetchall():
            accounts.append(account['account'])
        return accounts

    def update_account(self, account, role, frontier=None):
        """
        Insert if new, else update.
        """
        # if account not exist, insert; if exist, ignore.
        self.cursor.execute('''
            INSERT OR IGNORE INTO `nano_account`
            (`account`, `role`, `frontier`)
            VALUES (?, ?, ?)''',
            (account, role, frontier)
        )

        # if account exist, update
        self.cursor.execute('''
            UPDATE `nano_account`
            SET `frontier` = ?, `role` = ?
            WHERE account = ?''',
            (frontier, role, account)
        )

        self.conn.commit()
        print_log('Updated account {}: {} / {}'.format(role, account, frontier))

    def get_client_accounts(self):
        """
        Get all accounts with "receive" subtype in the block_chain history.
        Whoever sent money to the server is a client.
        """
        self.cursor.execute('''
            SELECT * from `block_chain`
            WHERE `subtype` = "receive"'''
        )

        clients = set()
        for block in self.cursor.fetchall():
            clients.add(block['account'])

        # exclude server accounts, since servers may send to each other.
        servers = self.get_server_accounts()
        return list(clients - set(servers))

    def get_block(self, hash):
        self.cursor.execute('SELECT * from `block_chain` WHERE `hash` = ?', (hash, ))
        return self.cursor.fetchone()  # None or dict

    def get_receive_blocks(self, server_account, client_account):
        """
        Get all blocks send from client to server.
        """
        server_id = self.get_account(server_account)['id']
        self.cursor.execute('''
            SELECT * from `block_chain`
            WHERE `subtype` = "receive" AND `owner_account` = ? AND `account` = ?''',
            (server_id, client_account)
        )
        return self.cursor.fetchall()  # list

    def update_block(self, account, block_dict):
        """
        Insert if new, else update.
        """
        block_type = block_dict.get('type')
        if block_type != 'state':
            print_log('Warning: none state block in history.')

        owner_account = self.get_account(account)['id']

        # if hash not exist, insert; if exist, ignore.
        self.cursor.execute('''
            INSERT OR IGNORE INTO `block_chain`
            (`owner_account`, `account`, `hash`, `previous`, `type`, `subtype`, `amount`, `balance`,
            `link`, `representative`, `signature`, `work`, `source`, `destination`, `next`)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                owner_account,
                block_dict.get('account'),
                block_dict.get('hash'),
                block_dict.get('previous'),
                block_dict.get('type'),
                block_dict.get('subtype'),
                block_dict.get('amount'),
                block_dict.get('balance'),
                block_dict.get('link'),
                block_dict.get('representative'),
                block_dict.get('signature'),
                block_dict.get('work'),
                block_dict.get('source'),
                block_dict.get('destination'),
                block_dict.get('next')
            )
        )

        # if hash exist, update
        self.cursor.execute('''
            UPDATE `block_chain`
            SET `owner_account` = ?, `account` = ?, `previous` = ?, `type` = ?, `subtype` = ?,
            `amount` = ?, `balance` = ?, `link` = ?, `representative` = ?, `signature` = ?,
            `work` = ?, `source` = ?, `destination` = ?, `next` = ?
            WHERE `hash` = ?''',
            (
                owner_account,
                block_dict.get('account'),
                block_dict.get('previous'),
                block_dict.get('type'),
                block_dict.get('subtype'),
                block_dict.get('amount'),
                block_dict.get('balance'),
                block_dict.get('link'),
                block_dict.get('representative'),
                block_dict.get('signature'),
                block_dict.get('work'),
                block_dict.get('source'),
                block_dict.get('destination'),
                block_dict.get('next'),
                block_dict.get('hash'),
            )
        )

        self.conn.commit()
        print_log('Updated account block: {} / {}'.format(account, block_dict['hash']))

    def _update_bill(self, account, key, value):
        client_account = self.get_account(account)['id']
        # if not exist, insert; if exist, ignore.
        self.cursor.execute('''
            INSERT OR IGNORE INTO `proxy_bill`
            (`client_account`, `{}`)
            VALUES (?, ?)'''.format(key),
            (client_account, value)
        )

        # if client_account exist, update
        self.cursor.execute('''
            UPDATE `proxy_bill`
            SET `{}` = ?
            WHERE client_account = ?'''.format(key),
            (value, client_account)
        )

        self.conn.commit()
        print_log('Updated client_account {}: {} / {}'.format(key, account, value))

    def update_total_pay(self, account, total_pay):
        self._update_bill(account, 'total_pay', total_pay)

    def update_total_spend(self, account, total_spend):
        self._update_bill(account, 'total_spend', total_spend)

    def update_total_bytes(self, account, total_bytes):
        self._update_bill(account, 'total_bytes', total_bytes)

    def update_total_requests(self, account, total_requests):
        self._update_bill(account, 'total_requests', total_requests)

    def update_bill_balance(self, account, balance):
        self._update_bill(account, 'balance', balance)


def test_main():
    db = DB('/tmp/test.db')
    db.get_account('xrb_1ipx847tk8o46pwxt5qjdbncjqcbwcc1rrmqnkztrfjy5k7z4imsrata9est')


if __name__ == '__main__':
    test_main()
