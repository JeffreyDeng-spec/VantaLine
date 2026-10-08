#!/usr/bin/env python3
"""Only read task, crop original, or submit one immutable whole-image report."""
import argparse
import http.client
import json
import os
from pathlib import Path
import socket


class Connection(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(20)
        self.sock.connect(os.environ['VANTALINE_TASK_SOCKET'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_subparsers(dest='action',required=True)
    actions.add_parser('show')
    actions.add_parser('submit').add_argument('--file',required=True)
    image=actions.add_parser('crop')
    image.add_argument('--source',required=True);image.add_argument('--file',required=True)
    image.add_argument('--box',required=True);image.add_argument('--scale',type=float,default=1)
    args=parser.parse_args()
    if args.action=='show':
        print(Path('/input/task.json').read_text());return
    if args.action=='crop':
        from image_tools import crop
        print(json.dumps(crop(args.source,args.file,json.loads(args.box),args.scale)));return
    file=Path(args.file).resolve()
    if not file.is_relative_to('/work') or file.stat().st_size>65536:
        raise ValueError('bounded report inside /work required')
    payload=json.loads(file.read_text())
    connection=Connection('localhost')
    connection.request('POST','/',json.dumps(payload),{'Authorization':'Bearer '+os.environ['VANTALINE_TASK_TOKEN'],'Content-Type':'application/json'})
    response=connection.getresponse();body=response.read(65536)
    if response.status!=200:raise ValueError('report refused: '+str(response.status))
    print(body.decode())


if __name__=='__main__':main()
