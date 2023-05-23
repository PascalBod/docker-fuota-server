#!/usr/bin/python
#
# This file is part of docker-esp32-fuota.
#
# docker-esp32-fuota is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# docker-esp32-fuota is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with espidf-udp.  If not, see <https://www.gnu.org/licenses/>.
#
# Copyright 2023 Pascal Bodin
#
import base64
import csv
import http.server
import io
import os
import sqlite3
import ssl
import tempfile
from urllib.parse import urlparse
from urllib.parse import parse_qs

# Configuration values are provided by environment variables.
AUTH_USERNAME = ''
AUTH_PASSWORD = ''
SERVER_PORT = 0

# Device_app table rows.
ROW_ID = 0
ROW_VER = 1
ROW_FILE = 2

# Error codes.
AUTH_ERR = 1
MISSING_DATA = 2
MISSING_FILE = 3
DEV_NOT_FOUND = 4

class RequestError(Exception):

    def __init__(self, error: int):
        self.error = error
    
class MyServerHandler(http.server.BaseHTTPRequestHandler):

    def display_request_info(self, method: str):

        (client_host, client_port) = self.client_address
        print('----------------------------------------')
        print('{} request from {}:{}'.format(method, client_host, client_port))
        print('----------')
        print('Headers:\n{}'.format(self.headers))
        print('----------')
        print('Request: {}'.format(self.requestline), flush=True)

    def check_authentication(self):

        # Filter out non authorized requests.
        if self.headers.get('Authorization') == None:
            print('No authentication', flush = True)
            raise RequestError(AUTH_ERR)
        # At this stage, there is some authentication data.
        key = self.server.get_auth_key()
        if self.headers.get('Authorization') != 'Basic ' + key:
            print('Incorrect credentials', flush = True)
            raise RequestError(AUTH_ERR)

    def process_get_devices(self, split_path, query):

        if len(split_path) == 2:
            # /devices/<device_id>
            device_id = split_path[1]
            if query == '':
                print('No query string', flush = True)
                raise RequestError(MISSING_DATA)
            app_ver_list = parse_qs(query).get('app_ver')
            if app_ver_list == None:
                print('No app_ver', flush = True)
                raise RequestError(MISSING_DATA)
            if len(app_ver_list) != 1:
                print('Incorrect app_ver', flush = True)
                raise RequestError(MISSING_DATA)
            app_ver = app_ver_list[0]
            print('Update request for {} running {}'.format(device_id,
                                                            app_ver),
                  flush = True)
            # Get name of update file.
            con = sqlite3.connect('../data/devices.db')
            cur = con.cursor()
            q = 'select * from device_app where device_id = "{}"'.format(device_id)
            res = cur.execute(q)
            dev_data = res.fetchone()
            if dev_data == None:
                # Device not known.
                print('Device not found', flush = True)
                cur.close()
                con.close()
                raise RequestError(DEV_NOT_FOUND)
            # Device is known. Let's check its application version.
            if dev_data[ROW_VER] != app_ver:
                # No planned update.
                cur.close()
                con.close()
                self.send_response(204)  # No Content.
                self.end_headers()
                return
            # At this stage, there is an update.
            # Internal consistency check.
            local_file_path = '../data/{}'.format(dev_data[ROW_FILE])
            if not os.path.isfile(local_file_path):
                print('{} update file not found'.format(local_file_path))
                cur.close()
                con.close()
                raise RequestError(MISSING_FILE)
            # At this stage, the update file is available.
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv')
            self.send_header('Content-Length', len(dev_data[ROW_FILE]))
            self.end_headers()
            self.wfile.write(dev_data[ROW_FILE].encode('utf-8'))
            cur.close()
            con.close()
            return

        if len(split_path) == 1:
            # /devices
            con = sqlite3.connect('../data/devices.db')
            cur = con.cursor()
            q = 'select * from device_app'
            res = cur.execute(q)
            temp_file = tempfile.NamedTemporaryFile(mode='w+', delete = False)
            temp_file_name = temp_file.name
            for row in res:
                temp_file.write('"{}","{}","{}"\n'.format(row[ROW_ID], row[ROW_VER], row[ROW_FILE]))
            temp_file.close()
            cur.close()
            con.close()
            self.send_response(200)
            self.send_header('Content-type', 'text/csv')
            self.send_header('Content-disposition', 'attachment; filename="{}"'.format(temp_file_name))
            self.end_headers()
            with open(temp_file_name, 'r') as file:
                self.wfile.write(file.read().encode('utf-8'))
            os.remove(temp_file_name)
            return

        # At this stage, incorrect request.
        print('Incorrect request', flush = True)
        raise RequestError(MISSING_DATA)

    def process_get_files(self, split_path):

        if len(split_path) == 2:
            # /files/<update_file_path>
            update_file_path = '../data/{}'.format(split_path[1])
            # Internal consistency check.
            if not os.path.isfile(update_file_path):
                print('{} update file not found'.format(update_file_path), flush = True)
                raise RequestError(MISSING_FILE)
            # At this stage, we can send the update file.
            self.send_response(200)
            self.send_header('Content-type', 'application/octet-stream')
            self.send_header('Content-Disposition', 'attachment; filename="{}"'.format(update_file_path))
            self.end_headers()
            with open(update_file_path, 'rb') as file: 
                self.wfile.write(file.read())
            return

        # At this stage, incorrect request.
        print('Incorrect request', flush = True)
        raise RequestError(MISSING_DATA)

    def process_put_files(self, split_path):

        if len(split_path) != 2:
            print('Incorrect path', flush=True)
            raise RequestError(MISSING_DATA)
        local_file_path = '../data/{}'.format(split_path[1])
        # TODO: add error processing for file handling.
        update_file = open(local_file_path, 'wb')
        # Get expected length.
        expected_length = int(self.headers.get('Content-length'))
        if expected_length == None:
            print('Can\'t read expected length', flush=True)
            raise RequestError(MISSING_DATA)
        print('Expected length: {}'.format(expected_length), flush=True)
        rec_length = 0
        while True:
            # read1 ensures a call to underlying read function, so that
            # we get all bytes till the end of stream.
            rec_bytes = self.rfile.read1(4096)
            update_file.write(rec_bytes)
            rec_length += len(rec_bytes)
            if (len(rec_bytes) == 0):
                break;
            if rec_length == expected_length:
                break;
        update_file.close()
        print('End of reception', flush=True)
        self.send_response(200)
        self.end_headers()

    def process_put_devices(self, split_path):

        if len(split_path) != 2:
            print('Incorrect path', flush=True)
            raise RequestError(MISSING_DATA)
        device_id = split_path[1]
        # Get expected length of CSV data.
        expected_length = int(self.headers.get('Content-length'))
        if expected_length == None:
            print('Can\'t read expected length', flush = True)
            raise RequestError(MISSING_DATA)
        print('Expected length: {}'.format(expected_length), flush = True)
        rec_length = 0
        rec_bytes = b''
        while True:
            # read1 ensures a call to underlying read function, so that
            # we get all bytes till the end of stream.
            rec_bytes += self.rfile.read1(4096)
            rec_length += len(rec_bytes)
            if (len(rec_bytes) == 0):
                break;
            if rec_length == expected_length:
                break;
        print('End of reception', flush=True)
        # Extract CSV data.
        in_mem_file = io.StringIO(rec_bytes.decode())
        reader = csv.reader(in_mem_file)
        str_list = next(reader)
        print('Data: {}'.format(str_list), flush = True)
        if len(str_list) != 3:
            print('Incorrect data', flush = True)
            raise RequestError(MISSING_DATA)
        device_id = str_list[0]
        app_version = str_list[1]
        update_file_path = str_list[2]
        # Update device_app table.
        con = sqlite3.connect('../data/devices.db')
        cur = con.cursor()
        # TODO: add transparency for ' and " characters.
        q = 'select * from device_app where device_id = "{}"'.format(device_id)
        res = cur.execute(q)
        if (len(res.fetchall()) == 0):
            # Create the row.
            q = 'insert into device_app values("{}", "{}", "{}")'.format(device_id,
                                                                         app_version,
                                                                         update_file_path)
            cur.execute(q)
        else:
            # Update existing row.
            q = 'update device_app ' \
                    'set ' \
                        'app_ver = "{}", ' \
                        'update_file_path="{}" ' \
                    'where device_id = "{}"'.format(app_version,
                                                    update_file_path,
                                                    device_id)
            cur.execute(q)
        con.commit()
        cur.close()
        con.close()
        #
        self.send_response(200)
        self.end_headers()

    def process_delete_devices(self, split_path):

        if len(split_path) != 2:
            print('Incorrect path', flush=True)
            raise RequestError(MISSING_DATA)
        device_id = split_path[1]
        # Update device_app table.
        con = sqlite3.connect('../data/devices.db')
        cur = con.cursor()
        q = 'delete from device_app where device_id = "{}"'.format(device_id)
        res = cur.execute(q)
        if res.rowcount == 0:
            print('Device not found', flush = True)
            cur.close()
            con.close()
            raise RequestError(DEV_NOT_FOUND)
        con.commit()
        cur.close()
        con.close()
        #
        self.send_response(200)
        self.end_headers()
                    
    def do_GET(self):

        self.display_request_info('GET')

        try:

            self.check_authentication()
            # At this stage, the request is authenticated.
            parsed_path = urlparse(self.path)
            split_path = parsed_path.path.strip('/').split('/')
            # Device requests.
            if split_path[0] == 'devices':
                self.process_get_devices(split_path, parsed_path.query)
            elif split_path[0] == 'files':
                self.process_get_files(split_path)
                
        except RequestError as err:
            
            if err.error == MISSING_DATA:
                self.send_response(400) # Bad Request
            elif err.error == AUTH_ERR:
                self.send_response(403) # Forbidden
            elif err.error == DEV_NOT_FOUND:
                self.send_response(404)  # Not Found
            elif err.error == MISSING_FILE:
                self.send_response(404) # Not Found
            self.end_headers()

    def do_PUT(self):

        self.display_request_info('PUT')

        try:

            self.check_authentication()
            # At this stage, the request is authenticated.
            parsed_path = urlparse(self.path)
            split_path = parsed_path.path.strip('/').split('/')
            # Management requests.
            if split_path[0] == 'files':
                self.process_put_files(split_path)
            elif split_path[0] == 'devices':
                self.process_put_devices(split_path)
                
        except RequestError as err:
            
            if err.error == MISSING_DATA:
                self.send_response(400) # Bad Request
            elif err.error == AUTH_ERR:
                self.send_response(403) # Forbidden
            self.end_headers()

    def do_DELETE(self):

        self.display_request_info('DELETE')

        try:

            self.check_authentication()
            # At this stage, the request is authenticated.
            parsed_path = urlparse(self.path)
            split_path = parsed_path.path.strip('/').split('/')
            # Management requests.
            if split_path[0] == 'devices':
                self.process_delete_devices(split_path)
                
        except RequestError as err:
            
            if err.error == MISSING_DATA:
                self.send_response(400) # Bad Request
            elif err.error == AUTH_ERR:
                self.send_response(403) # Forbidden
            elif err.error == DEV_NOT_FOUND:
                self.send_response(404)  # Not Found
            self.end_headers()
    
class MyHTTPServer(http.server.ThreadingHTTPServer):

    key = ''

    def __init__(self, address, handlerClass=MyServerHandler):
        super().__init__(address, handlerClass)

    def set_auth(self, username, password):
        self.key = base64.b64encode(
            bytes('%s:%s' % (username, password), 'utf-8')).decode('ascii')

    def get_auth_key(self):
        return self.key    

# Create the database if it does not exist yet.
con = sqlite3.connect('../data/devices.db')
# Create the table if it does not exist yet.
cur = con.cursor()
q = 'create table if not exists ' \
    'device_app(device_id text primary key asc, ' \
               'app_ver text, ' \
               'update_file_path text)'
cur.execute(q)
cur.close()
con.close()
# Read configuration from environment.
if 'US_AUTH_USERNAME' in os.environ:
    AUTH_USERNAME = os.environ['US_AUTH_USERNAME']
if 'US_AUTH_PASSWORD' in os.environ:
    AUTH_PASSWORD = os.environ['US_AUTH_PASSWORD']
if 'US_SERVER_PORT' in os.environ:
    SERVER_PORT = int(os.environ['US_SERVER_PORT'])
# Create and start HTTP server.
server = MyHTTPServer(('0.0.0.0', SERVER_PORT))
server.set_auth(AUTH_USERNAME, AUTH_PASSWORD)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('ca_cert.pem', 'ca_key.pem')
server.socket = context.wrap_socket (server.socket, server_side=True)
server.serve_forever()
