# ESP32 FUOTA server

## Environment

All commands provided in this README are for Linux. They were used with [Linux Mint](https://linuxmint.com/) 20.3, but should work with most Linux distributions.

The server is coded in Python. It is based on `http.server.ThreadingHTTPServer`. Consequently, the minimum required version of Python is 3.7.

Install *openssl* and *curl*, if they are not installed yet.

## Overview

This repository provides a Docker image containing a test server allowing to demonstrate and test FUOTA for ESP32. The ESP32 must run the application provided by the [*esp32-fuota* repository](https://github.com/PascalBod/esp32-fuota).

Implemented functionalities:
* HTTPS server
* basic authentication with configurable username and password
* two-step update: 
  * the device first provides its identity and its application version, and the server returns the name of the  binary update file if an update of the application is available for this device
  * the device then requests the binary update file
* data management functions:
  * add an update file
  * add or modify update information for a device
  * delete update information for a device
  * get update information for all devices

It is supposed that the server handles the updates for one application only.

Note: this is NOT a production-grade server. Its aim is to demonstrate one way to set up a simple end-to-end firmware update solution for the ESP32, and to let the user better understand what has to be done when implementing an update solution, in terms of API, security, scalability, etc.

For instructions about how to check end-to-end operation, please refer to the [*esp32-fuota* repository](https://github.com/PascalBod/esp32-fuota).

## Certificate and key

The update server is identified with a certificate.

The certificate contains the domain name (or the IP address) of the server and its public key, signed by its private key.

The generation of a self-signed certificate and of the associated private key can be performed with the following command:

```bash
$ openssl req -x509 -newkey rsa:2048 -keyout ca_key.pem -out ca_cert.pem -days 365 -nodes
```

When prompted for the **Common Name**, enter the server domain name or the IP address of the server.

Thanks to the certificate, the device can check that the server it contacts is the real one. And the certificate allows to encrypt the communication between the device and the server.

## Authentication

The server uses basic authentication. Confidentiality is ensured by the use of HTTPS.

## Requests and responses

### Background

All requests must provide basic authentication.

HTTP/1.1 protocol is decribed in [RFC 2616](https://www.rfc-editor.org/rfc/rfc2616). [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) provides recent information about HTTP semantics.

[Section 3.4 of RFC 2396](https://www.rfc-editor.org/rfc/rfc2396#section-3.4) specifies a set of reserved characters within the query part of a URL. A test demonstrated that *urllib.parse* library supports the use of `:` character in a query parameter. Consequently, this character is not escaped by the ESP32 application.

Defined resources are:
* devices
* files

### Device requests

#### `GET /devices/<device_id>?app_ver=<app_version>`

This request checks whether an update is available for a given device running a given version of the application.

`<device_id>` is the identifier of the device

`<app_version>` is the version of the application being currently run by the device.

Possible response status codes are:
* 200 (OK) - Update available
* 204 (No Content) - No update available
* 400 (Bad Request) - Incorrect request syntax
* 403 (Forbidden) - No valid credentials
* 404 (Not Found) - Device is not known or update file not found

For `200` status code, update file path is returned as `text/csv`. Optional parameters of `Content-Type` header are not present.

The following curl command may be used to send this request:

```bash
$ curl -u <username>:<password> --cacert <ca_cert_pem_file_path> \
       --verbose --request GET \
       'https://<server_fqdn>:<server_port>/devices/<device_id>?app_ver=<app_version>'
```

#### `GET /files/<update_file_path>`

This request returns a given update file.

`<update_file_path>` must be the path returned by the `GET /devices/<device_id>?app_ver=<app_version>` request.

Possible response status codes are:
* 200 (OK) - Update file found and returned
* 400 (Bad Request) - Incorrect request syntax or update file not found
* 403 (Forbidden) - No valid credentials
* 404 (Not Found) - Update file not found

The following curl command may be used to send this request:

```bash
$ curl -u <username>:<password> --cacert <ca_cert_pem_file_path> \
       --verbose --request GET \
       --output <local_update_file_path> \
       'https://<server_fqdn>:<server_port>/files/<update_file_path>'
```

### Data management requests

#### `GET /devices`

This request returns device update information, for every device. The information is returned as `text/csv` data. The format of every line is:

```
"<device_id>","<app_version>","<update_file_path>"
```

Possible response status codes are:
* 200 (OK) - Device update information returned
* 400 (Bad Request) - Incorrect request syntax
* 403 (Forbidden) - No valid credentials

The following curl command may be used to send this request:

```bash
$ curl -u <username>:<password> --cacert <ca_cert_pem_file_path> \
       --verbose --request GET \
       'https://<server_fqdn>:<server_port>/devices'
```

#### `PUT /files/<update_file_path>`

This request uploads an update file to the server.

`<update_file_path>` must be the file path used in the CSV file of the `PUT /devices/<device_id>` request. It must not contain a double-quote character.

The update file has to be provided as `application/octet-stream` data.

Possible response status codes are:
* 200 (OK) - The update file is successfully uploaded
* 400 (Bad Request) - Incorrect request syntax
* 403 (Forbidden) - No valid credentials

The following curl command may be used to send this request:

```bash
$ curl -u <username>:<password> --cacert <ca_cert_pem_file_path> \
       --verbose --request PUT --data-binary @<local_update_file_path> \
       --header "Content-Type: application/octet-stream" \
       'https://<server_fqdn>:<server_port>/files/<update_file_path>'
```

#### `PUT /devices/<device_id>`

This request adds update information for a given device, or updates an existing update information for the device.

`<device_id>` is the identifier of the device.

Device update information has to be provided as `text/csv`, with the following format:

```
"<device_id>","<app_version>","<update_file_path>"
```

The *device_app* table (see below) is updated with provided information. If a row for the same device identifier already exists, it is updated. Otherwise, a new row is created.

Possible response status codes are:
* 200 (OK) - The update file is successfully uploaded
* 400 (Bad Request) - Incorrect request syntax
* 403 (Forbidden) - No valid credentials

The following curl command may be used to send this request:

```bash
$ curl -u <username>:<password> --cacert <ca_cert_pem_file_path> \
       --verbose --request PUT --data '"<device_id>","<app_version>","<update_file_path>"' \
       --header "Content-Type: text/csv" \
       'https://<server_fqdn>:<server_port>/devices/<device_id>'
```

#### `GET /devices`

This request returns the contents of the *device_app* table (see below). The contents is returned as `text/csv`. All fields are strings delimited by double-quote characters. They are separated by a comma.

The following curl command may be used to send this request:

```bash
$ curl -u <username>:<password> --cacert <ca_cert_pem_file_path> \
       --verbose --request GET \
       'https://<server_fqdn>:<server_port>/devices'
```

#### `DELETE /devices/<device_id>`

This request deletes the update information of a given device.

`<device_id>` is the identifier of the device.

Possible response status codes are:
* 200 (OK) - Device update information deleted
* 400 (Bad Request) - Incorrect request syntax
* 403 (Forbidden) - No valid credentials
* 404 (Not Found) - Device is not known

The following curl command may be used to send this request:

```bash
$ curl -u <username>:<password> --cacert <ca_cert_pem_file_path> \
       --verbose --request DELETE \
       --header "Content-Type: text/csv" \
       'https://<server_fqdn>:<server_port>/devices/<device_id>'
```

## Update information

Update information is stored in an SQLite database.

Following table is used:

* `device_app`:
  * `device_id`: text - primary key
  * `app_ver`: text
  * `update_file_path`: text

When the server receives the device identifier and the application version of a device, it checks them against the table. If they are found, the server considers that an update is available, and the update will use the binary file referenced by `update_file_path`.

## Docker image

### Overview

The provided Dockerfile allows to create a Docker image containing the server. Instructions provided below are for Docker Engine.

### Docker Engine installation

To install Docker Engine, check [this page](https://docs.docker.com/engine/).

### How to build the image

The Docker image is built with the following commands:

```bash
$ cd docker-fuota-server/docker
$ # Create a certificate and the associated private key.
$ openssl req -x509 -newkey rsa:2048 -keyout ca_key.pem -out ca_cert.pem -days 365 -nodes
$ # Create the image.
$ docker build -t fuota-server .
```

### How to create and run a container

The `run_fuota_server` script can be used to create and run a container. It publishes the port used for update requests on port 50000 of the host machine. Adapt it to your needs.

The container uses a named volume to store data that must be persisted:
* sqlite database
* update files

To create and run a container:

```bash
$ cd docker-fuota-server/docker
./run_fuota_server
```

To display log messages generated by the container:

```bash
$ # Use CTRL-C to stop.
$ docker container logs -f fuota-server
```

To list files created in the volume:

```bash
$ # First, get volume information.
$ docker volume inspect fuota-server-volume
[
    {
        "CreatedAt": "2022-10-30T05:38:56Z",
        "Driver": "local",
        "Labels": null,
        "Mountpoint": "/var/lib/docker/volumes/fuota-server-volume/_data",
        "Name": "runningupdateserver",
        "Options": null,
        "Scope": "local"
    }
]
$ # Then, list the content of the mountpoint directory.
$ ls /var/lib/docker/volumes/fuota-server-volume/_data
```