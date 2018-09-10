# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2018, Galen Curwen-McAdams

import argparse
import redis
import pathlib
from lxml import etree
from ma_cli import data_models


def populate_db(db_host, db_port, xml_files=None, verbose=False):
    if db_port is None:
        r_ip, r_port = data_models.service_connection()
    else:
        r_ip, r_port = db_host, db_port

    if not xml_files:
        # get path in module
        xml_files = [
            pathlib.PurePath(pathlib.Path(__file__).parents[0], "reference.xml")
        ]

    # binary_r = redis.StrictRedis(host=r_ip, port=r_port)
    redis_conn = redis.StrictRedis(host=r_ip, port=r_port, decode_responses=True)
    device_script_lookup_key = "device:script_lookup"
    script_lookup_key = "scripts:{}"
    for xml_file in xml_files:
        xml = etree.parse(str(xml_file))

        for script in xml.xpath("//script"):
            script_name = script.xpath("./@name")[0]
            for call in script.xpath("//call"):
                redis_conn.hset(
                    script_lookup_key.format(script_name),
                    call.xpath("./@name")[0],
                    call.xpath("./@template")[0],
                )

        for device in xml.xpath("//device"):
            redis_conn.hset(
                device_script_lookup_key,
                device.xpath("./@name")[0],
                device.xpath("./@script")[0],
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-host", default="127.0.0.1", help="db host ip")
    parser.add_argument("--db-port", default=None, help="db port")
    parser.add_argument("--xml-file", nargs="+", default=[], help="xml files")
    parser.add_argument("--verbose", action="store_true", help="")
    args, unknown_args = parser.parse_known_args()
    args = vars(args)
    populate_db(args["db_host"], args["db_port"], args["xml_file"])
